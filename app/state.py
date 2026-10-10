"""Record and restore run state through a JSON manifest."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.errors import StateError

PENDING = "pending"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RowState:
    index: int
    status: str
    output: str | None = None
    error: str | None = None
    attempts: int = 0
    updated_at: str | None = None


class StateManager:
    """Owns the manifest.json file: status per row and run metadata."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] | None = None

    def exists(self) -> bool:
        return self.path.exists()

    def initialize(
        self,
        total_rows: int,
        input_file: str | Path,
        template_file: str | Path,
        run_id: str | None = None,
    ) -> None:
        timestamp = _now()
        self.data = {
            "run_id": run_id or timestamp,
            "input_file": str(input_file),
            "template_file": str(template_file),
            "started_at": timestamp,
            "updated_at": timestamp,
            "total_rows": total_rows,
            "rows": {
                str(index): {
                    "status": PENDING,
                    "output": None,
                    "error": None,
                    "attempts": 0,
                    "updated_at": timestamp,
                }
                for index in range(1, total_rows + 1)
            },
        }
        self.save()

    def load(self) -> None:
        if not self.path.exists():
            raise StateError(f"State file not found: {self.path}")
        try:
            raw = self.path.read_text(encoding="utf-8")
            self.data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"Could not read state file {self.path}: {exc}") from exc
        if not isinstance(self.data, dict) or "rows" not in self.data:
            raise StateError(f"State file is malformed: {self.path}")

    def save(self) -> None:
        if self.data is None:
            raise StateError("Cannot save state before it is initialized")
        self.data["updated_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp, self.path)
        except OSError as exc:
            raise StateError(f"Could not write state file {self.path}: {exc}") from exc

    def row(self, index: int) -> RowState:
        rows = self._rows()
        entry = rows.get(str(index))
        if entry is None:
            raise StateError(f"Unknown row index in state: {index}")
        return RowState(
            index=index,
            status=entry.get("status", PENDING),
            output=entry.get("output"),
            error=entry.get("error"),
            attempts=entry.get("attempts", 0),
            updated_at=entry.get("updated_at"),
        )

    def status(self, index: int) -> str:
        return self.row(index).status

    def is_completed(self, index: int) -> bool:
        return self.status(index) == COMPLETED

    def should_process(self, index: int, rerun_failed: bool = True) -> bool:
        status = self.status(index)
        if status == COMPLETED:
            return False
        if status == FAILED and not rerun_failed:
            return False
        return True

    def mark_in_progress(self, index: int) -> None:
        self._update(index, status=IN_PROGRESS, increment_attempts=True, clear_error=True)

    def mark_completed(self, index: int, output: str | None) -> None:
        self._update(index, status=COMPLETED, output=output, clear_error=True)

    def mark_failed(self, index: int, error: str | None) -> None:
        self._update(index, status=FAILED, error=error)

    def summary(self) -> dict[str, int]:
        counts = {PENDING: 0, IN_PROGRESS: 0, COMPLETED: 0, FAILED: 0}
        for entry in self._rows().values():
            status = entry.get("status", PENDING)
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _update(
        self,
        index: int,
        *,
        status: str,
        output: str | None = None,
        error: str | None = None,
        increment_attempts: bool = False,
        clear_error: bool = False,
    ) -> None:
        rows = self._rows()
        key = str(index)
        if key not in rows:
            raise StateError(f"Unknown row index in state: {index}")
        entry = rows[key]
        entry["status"] = status
        if output is not None:
            entry["output"] = output
        if error is not None:
            entry["error"] = error
        if clear_error:
            entry["error"] = None
        if increment_attempts:
            entry["attempts"] = entry.get("attempts", 0) + 1
        entry["updated_at"] = _now()
        self.save()

    def _rows(self) -> dict[str, Any]:
        if self.data is None:
            raise StateError("State is not loaded or initialized")
        return self.data["rows"]
