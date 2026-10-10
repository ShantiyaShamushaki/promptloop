"""Save chatbot responses as standalone Markdown files."""

from __future__ import annotations

import re
from pathlib import Path

from app.errors import ResultStoreError

_SANITIZE_PATTERN = re.compile(r"[^\w\-.]+", re.UNICODE)
_MAX_LABEL_LENGTH = 60


def sanitize_label(label: str) -> str:
    """Return a filesystem-safe version of a row label."""
    cleaned = _SANITIZE_PATTERN.sub("_", label.strip())
    cleaned = cleaned.strip("._-")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    if not cleaned:
        return "row"
    return cleaned[:_MAX_LABEL_LENGTH]


def build_filename(index: int, label: str) -> str:
    return f"{index:04d}_{sanitize_label(label)}.md"


def build_document(
    *,
    label: str,
    index: int,
    status: str,
    prompt: str,
    response: str,
    error: str | None = None,
    input_row: dict[str, str] | None = None,
) -> str:
    lines = [
        f"# {label}",
        "",
        f"- Input row: {index}",
        f"- Status: {status}",
    ]
    if input_row:
        lines.append("- Input values:")
        for key, value in input_row.items():
            lines.append(f"  - {key}: {value}")
    if error:
        lines.append(f"- Error: {error}")
    lines += [
        "",
        "## Prompt",
        "",
        prompt,
        "",
        "## Response",
        "",
        response,
        "",
    ]
    return "\n".join(lines)


class ResultStore:
    """Writes response files under ``<output>/responses``."""

    def __init__(self, output_dir: str | Path, overwrite: bool = False) -> None:
        self.output_dir = Path(output_dir)
        self.responses_dir = self.output_dir / "responses"
        self.overwrite = overwrite
        self.responses_dir.mkdir(parents=True, exist_ok=True)

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.output_dir).as_posix()
        except ValueError:
            return path.as_posix()

    def save(
        self,
        *,
        index: int,
        label: str,
        prompt: str,
        response: str,
        status: str = "completed",
        error: str | None = None,
        input_row: dict[str, str] | None = None,
        overwrite: bool | None = None,
    ) -> Path:
        filename = build_filename(index, label)
        path = self.responses_dir / filename
        allow_overwrite = self.overwrite if overwrite is None else overwrite
        if path.exists() and not allow_overwrite:
            raise ResultStoreError(f"Output file already exists: {path}")
        document = build_document(
            label=label,
            index=index,
            status=status,
            prompt=prompt,
            response=response,
            error=error,
            input_row=input_row,
        )
        try:
            path.write_text(document, encoding="utf-8")
        except OSError as exc:
            raise ResultStoreError(f"Could not write response file {path}: {exc}") from exc
        return path
