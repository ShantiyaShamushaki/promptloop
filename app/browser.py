"""Manage the Playwright/Chromium browser lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import subprocess
import asyncio
from app.errors import BrowserError


class BrowserSession:
    """An async context manager wrapping a Chromium browser and context.

    If ``profile_dir`` is provided a persistent context is used so the user's
    login is kept between runs. Otherwise a temporary context is created.
    """

    def __init__(
        self,
        *,
        headless: bool = False,
        profile_dir: str | Path | None = None,
        slow_mo_ms: int = 0,
        timeout_ms: int = 30_000,
        chrome_path: str | None = None,
    ) -> None:
        self.headless = headless
        self.profile_dir = Path(profile_dir) if profile_dir else Path(os.getenv("LOCALAPPDATA", "")) / "PromptLoop" / "ChromeProfile"
        self.chrome_path = chrome_path or os.getenv("PROMPTLOOP_CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        self.slow_mo_ms = slow_mo_ms
        self.timeout_ms = timeout_ms
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._chrome_process: subprocess.Popen | None = None
    
    async def start(self) -> Any:
        from playwright.async_api import async_playwright
        print(self.chrome_path)
        try:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            chrome_args = [
                self.chrome_path,
                "--remote-debugging-port=9222",
                f"--user-data-dir={self.profile_dir}",
            ]
            if self.headless:
                chrome_args.append("--headless=new")
            self._chrome_process = subprocess.Popen(chrome_args)
            await asyncio.sleep(2)
            
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                "http://127.0.0.1:9222"
            )
            if not self._browser.contexts:
                raise RuntimeError("No Chrome context found")

            self._context = self._browser.contexts[0]
            self._context.set_default_timeout(self.timeout_ms)
        
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message:
                raise BrowserError(
                    "Chromium is not installed. Run: python -m playwright install chromium"
                ) from exc
            raise BrowserError(f"Could not open Chromium: {message}") from exc
        return self._context

    @property
    def context(self) -> Any:
        if self._context is None:
            raise BrowserError("Browser is not started")
        return self._context

    async def new_page(self) -> Any:
        return await self.context.new_page()

    async def close(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            if self._chrome_process is not None:
                try:
                    self._chrome_process.terminate()
                    self._chrome_process.wait(timeout=3) # کمی منتظر ماندن برای بسته شدن نرم
                except Exception:
                    self._chrome_process.kill()
                    
            self._context = None
            self._browser = None
            self._playwright = None
            self._chrome_process = None

    async def __aenter__(self) -> "BrowserSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()
