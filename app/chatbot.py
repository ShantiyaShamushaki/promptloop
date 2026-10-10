"""Interact with the chatbot web UI through Playwright.

All UI-specific details (selectors, timing) live here. Selectors are
configurable via :class:`ChatbotConfig` or environment variables so a change
in the target service does not leak into the rest of the program.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

from app.errors import ChatbotError


@dataclass
class ChatbotConfig:
    url: str = "https://chatgpt.com/"
    input_selector: str = "#prompt-textarea"
    send_button_selector: str = '[data-testid="send-button"]'
    stop_button_selector: str = '[data-testid="stop-button"]'
    response_selector: str = '[data-message-author-role="assistant"]'
    response_timeout_ms: int = 120_000
    ready_timeout_ms: int = 60_000
    settle_ms: int = 1_500
    poll_interval_ms: int = 500

    @classmethod
    def from_env(cls) -> "ChatbotConfig":
        config = cls()
        config.url = os.getenv("PROMPTLOOP_URL", config.url)
        config.input_selector = os.getenv(
            "PROMPTLOOP_INPUT_SELECTOR", config.input_selector
        )
        config.send_button_selector = os.getenv(
            "PROMPTLOOP_SEND_SELECTOR", config.send_button_selector
        )
        config.stop_button_selector = os.getenv(
            "PROMPTLOOP_STOP_SELECTOR", config.stop_button_selector
        )
        config.response_selector = os.getenv(
            "PROMPTLOOP_RESPONSE_SELECTOR", config.response_selector
        )
        timeout = os.getenv("PROMPTLOOP_RESPONSE_TIMEOUT_MS")
        if timeout and timeout.isdigit():
            config.response_timeout_ms = int(timeout)
        return config


class Chatbot:
    """Sends prompts and extracts responses for a single chatbot UI."""

    def __init__(self, page: Any, config: ChatbotConfig | None = None) -> None:
        self.page = page
        self.config = config or ChatbotConfig.from_env()
        self._previous_count = 0

    async def open(self) -> None:
        try:
            await self.page.goto(self.config.url, wait_until="domcontentloaded")
        except Exception as exc:
            raise ChatbotError(f"Could not open chatbot page: {exc}") from exc

    def _response_locator(self) -> Any:
        return self.page.locator(self.config.response_selector)

    async def response_count(self) -> int:
        return await self._response_locator().count()

    async def wait_until_ready(self) -> None:
        """Wait until the message input is present and usable."""
        try:
            await self.page.locator(self.config.input_selector).wait_for(
                state="visible", timeout=self.config.ready_timeout_ms
            )
        except Exception as exc:
            raise ChatbotError(
                f"Message input not found ({self.config.input_selector}). "
                "Is the chat page open and are you logged in?"
            ) from exc

    async def send_prompt(self, text: str) -> None:
        """Type and send a prompt. Records the assistant message count first."""
        if not text.strip():
            raise ChatbotError("Refusing to send an empty prompt")

        self._previous_count = await self.response_count()
        box = self.page.locator(self.config.input_selector)
        try:
            await box.wait_for(state="visible", timeout=self.config.ready_timeout_ms)
            await box.click()
            await box.fill(text)
        except Exception as exc:
            raise ChatbotError(f"Could not fill the message box: {exc}") from exc

        send = self.page.locator(self.config.send_button_selector)
        try:
            await send.wait_for(state="visible", timeout=self.config.ready_timeout_ms)
            await send.click()
        except Exception as exc:
            raise ChatbotError(f"Could not send the prompt: {exc}") from exc

    async def wait_and_extract(
        self,
        *,
        expected_previous_count: int | None = None,
        timeout_ms: int | None = None,
    ) -> str:
        """Wait for a new response to appear, settle, and return its text."""
        previous = (
            expected_previous_count
            if expected_previous_count is not None
            else self._previous_count
        )
        timeout = timeout_ms or self.config.response_timeout_ms
        deadline = time.monotonic() + timeout / 1000

        locator = self._response_locator()
        try:
            await self._wait_for_count(locator, previous + 1, deadline)
        except ChatbotError:
            raise
        except Exception as exc:
            raise ChatbotError(f"Response did not appear within timeout: {exc}") from exc

        await self._wait_for_stop_button(deadline)
        text = await self._wait_for_stable_text(locator, deadline)

        if not text.strip():
            raise ChatbotError("Extracted response text is empty")
        self._previous_count = await self.response_count()
        return text

    async def _wait_for_count(self, locator: Any, expected: int, deadline: float) -> None:
        while time.monotonic() < deadline:
            if await locator.count() >= expected:
                return
            await asyncio.sleep(self.config.poll_interval_ms / 1000)
        raise ChatbotError(
            "Chatbot did not start generating a response within the timeout"
        )

    async def _wait_for_stop_button(self, deadline: float) -> None:
        stop = self.page.locator(self.config.stop_button_selector)
        try:
            if await stop.count() == 0:
                return
            await stop.first.wait_for(state="hidden", timeout=max(1, int((deadline - time.monotonic()) * 1000)))
        except Exception:
            return

    async def _wait_for_stable_text(self, locator: Any, deadline: float) -> str:
        settle_seconds = self.config.settle_ms / 1000
        interval = self.config.poll_interval_ms / 1000
        last_text: str | None = None
        stable_since: float | None = None

        while time.monotonic() < deadline:
            try:
                current = await locator.last.inner_text()
            except Exception:
                current = last_text or ""
            if current == last_text and current:
                if stable_since is not None and time.monotonic() - stable_since >= settle_seconds:
                    return current
            else:
                last_text = current
                stable_since = time.monotonic()
            await asyncio.sleep(interval)

        if last_text:
            return last_text
        raise ChatbotError("Timed out waiting for a stable response")
