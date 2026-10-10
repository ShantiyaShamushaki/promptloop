"""PromptLoop entry point: wire the components together and run the loop."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dotenv import load_dotenv
import sys
from pathlib import Path

from app import __version__
from app.browser import BrowserSession
from app.chatbot import Chatbot, ChatbotConfig
from app.errors import (
    BrowserError,
    ChatbotError,
    InputError,
    PromptLoopError,
    ResultStoreError,
    StateError,
    TemplateError,
)
from app.input_loader import load_input, row_label
from app.result_store import ResultStore
from app.state import COMPLETED, StateManager
from app.template_engine import render, validate_template

log = logging.getLogger("promptloop")
load_dotenv()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="promptloop",
        description="Run a Markdown prompt template over every row of a CSV "
        "through a chatbot web UI.",
    )
    parser.add_argument("--csv", required=True, help="Path to the input CSV file")
    parser.add_argument("--template", required=True, help="Path to the Markdown template")
    parser.add_argument("--output", default="output", help="Output folder (default: output)")
    parser.add_argument("--resume", action="store_true", help="Resume a previous run")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N rows")
    parser.add_argument(
        "--profile",
        default=".browser-profile",
        help="Persistent Chromium profile folder (default: .browser-profile)",
    )
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Use a temporary browser session instead of a persistent profile",
    )
    parser.add_argument("--headless", action="store_true", help="Run Chromium headless")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Seconds to wait for each response (default: 120)",
    )
    parser.add_argument(
        "--no-rerun-failed",
        action="store_true",
        help="Skip rows that previously failed when resuming",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess rows already marked completed",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument(
        "--version", action="version", version=f"promptloop {__version__}"
    )
    return parser.parse_args(argv)


def _setup_logging(output_dir: Path, verbose: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    log.setLevel(level)
    log.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(stream)

    file_handler = logging.FileHandler(output_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)


async def _ask_ready() -> None:
    await asyncio.to_thread(
        input,
        "Please log in to the chatbot in the browser.\n"
        "Complete any required verification manually.\n"
        "When the chat page is ready, type 'y' and press Enter: ",
    )


async def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    _setup_logging(output_dir, args.verbose)

    log.info("PromptLoop")
    log.info("==========")
    log.info("")
    log.info("Loading input files...")

    data = load_input(args.csv)
    template_path = Path(args.template)
    if not template_path.exists():
        raise InputError(f"Template file not found: {template_path}")
    template = template_path.read_text(encoding="utf-8")

    log.info("CSV rows: %d", len(data))
    log.info("CSV columns: %s", ", ".join(data.columns))

    validation = validate_template(template, data.columns)
    if not validation.ok:
        log.error("Template validation failed.")
        for column in validation.missing_columns:
            log.error("Missing CSV column: %s", column)
        return 2
    log.info("Template validation: passed")
    if validation.unused_columns:
        log.warning(
            "Warning: CSV column(s) not used in template: %s",
            ", ".join(validation.unused_columns),
        )

    manifest_path = output_dir / "manifest.json"
    state = StateManager(manifest_path)
    if args.resume:
        if not state.exists():
            raise StateError(f"--resume given but no state file at {manifest_path}")
        state.load()
        if state.data.get("total_rows") != len(data):
            raise StateError(
                "State file does not match the input file "
                f"({state.data.get('total_rows')} vs {len(data)} rows). "
                "Start a fresh run or use the original input."
            )
        log.info("Resuming previous run: %s", state.data.get("run_id"))
    else:
        if state.exists():
            raise StateError(
                f"State file already exists at {manifest_path}. "
                "Use --resume to continue it, or choose another --output folder."
            )
        state.initialize(len(data), args.csv, args.template)

    store = ResultStore(output_dir)
    chatbot_config = ChatbotConfig.from_env()
    chatbot_config.response_timeout_ms = args.timeout * 1000
    profile = None if args.no_profile else args.profile

    log.info("")
    log.info("Opening browser...")
    summary = {}
    try:
        async with BrowserSession(
            headless=args.headless, profile_dir=profile
        ) as session:
            page = await session.new_page()
            chatbot = Chatbot(page, chatbot_config)
            await chatbot.open()
            await _ask_ready()
            await chatbot.wait_until_ready()
            summary = await _process_rows(args, data, template, state, store, chatbot)
    except BrowserError as exc:
        log.error("%s", exc)
        return 1

    _print_summary(state, summary, output_dir)
    failed = state.summary().get("failed", 0)
    return 1 if failed else 0


async def _process_rows(
    args: argparse.Namespace,
    data,
    template: str,
    state: StateManager,
    store: ResultStore,
    chatbot: Chatbot,
) -> dict[str, int]:
    processed = 0
    rerun_failed = not args.no_rerun_failed

    for index, row in enumerate(data.rows, start=1):
        if args.limit is not None and processed >= args.limit:
            break
        if not _should_run(state, index, args.force, rerun_failed):
            log.info("[%d/%d] Skipping (already completed)", index, len(data))
            continue

        label = row_label(row, data.columns, index)
        log.info("")
        log.info("[%d/%d] Processing %s...", index, len(data), label)
        log.info("Waiting for response...")

        prompt = render(template, row)
        state.mark_in_progress(index)
        overwrite = state.row(index).attempts > 1 or args.force
        processed += 1

        try:
            await chatbot.send_prompt(prompt)
            response = await chatbot.wait_and_extract()
        except ChatbotError as exc:
            state.mark_failed(index, str(exc))
            log.error("Row %d failed: %s", index, exc)
            log.error("Stopping before sending the next prompt.")
            break

        try:
            path = store.save(
                index=index,
                label=label,
                prompt=prompt,
                response=response,
                input_row=row,
                overwrite=overwrite,
            )
        except ResultStoreError as exc:
            state.mark_failed(index, str(exc))
            log.error("Row %d failed: %s", index, exc)
            break

        state.mark_completed(index, store.relative(path))
        log.info("Response saved: %s", path.as_posix())

    return state.summary()


def _should_run(
    state: StateManager, index: int, force: bool, rerun_failed: bool
) -> bool:
    status = state.status(index)
    if status == COMPLETED:
        return force
    if status == "failed":
        return rerun_failed
    return True


def _print_summary(state: StateManager, summary: dict[str, int], output_dir: Path) -> None:
    log.info("")
    log.info("Run completed.")
    log.info("Successful: %d", summary.get("completed", 0))
    log.info("Failed: %d", summary.get("failed", 0))
    remaining = summary.get("pending", 0) + summary.get("in_progress", 0)
    log.info("Remaining: %d", remaining)
    log.info("Output: %s", (output_dir / "responses").as_posix())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted. Progress was saved; rerun with --resume.", file=sys.stderr)
        return 130
    except (InputError, TemplateError, StateError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except PromptLoopError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
