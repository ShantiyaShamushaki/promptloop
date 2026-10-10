"""Read and validate the CSV input file."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from app.errors import InputError


@dataclass
class InputData:
    columns: list[str]
    rows: list[dict[str, str]]
    source: Path

    def __len__(self) -> int:
        return len(self.rows)


def load_input(path: str | Path) -> InputData:
    """Load a CSV file into columns and row dictionaries.

    Raises InputError for missing/empty files, duplicate or empty column
    names, and rows whose value count does not match the header.
    """
    csv_path = Path(path)

    if not csv_path.exists():
        raise InputError(f"CSV file not found: {csv_path}")
    if not csv_path.is_file():
        raise InputError(f"CSV path is not a file: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            raw_header = next(reader)
        except StopIteration:
            raise InputError(f"CSV file is empty: {csv_path}") from None

        columns = [cell.strip() for cell in raw_header]
        if not any(columns):
            raise InputError(f"CSV header row is empty: {csv_path}")

        duplicates = _duplicates(columns)
        if duplicates:
            joined = ", ".join(duplicates)
            raise InputError(f"Duplicate CSV column name(s): {joined}")

        empty_columns = [index + 1 for index, name in enumerate(columns) if not name]
        if empty_columns:
            joined = ", ".join(str(index) for index in empty_columns)
            raise InputError(f"Empty CSV column name at position(s): {joined}")

        rows = _read_rows(reader, columns, csv_path)

    return InputData(columns=columns, rows=rows, source=csv_path)


def _read_rows(
    reader: csv.reader, columns: list[str], csv_path: Path
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(reader, start=2):
        if not raw or all(cell.strip() == "" for cell in raw):
            continue
        if len(raw) != len(columns):
            raise InputError(
                f"CSV row {line_number} has {len(raw)} value(s), "
                f"expected {len(columns)} (file: {csv_path})"
            )
        row = {column: value.strip() for column, value in zip(columns, raw)}
        rows.append(row)
    return rows


def _duplicates(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    for name in columns:
        seen[name] = seen.get(name, 0) + 1
    return [name for name, count in seen.items() if count > 1]


def row_label(row: dict[str, str], columns: list[str], index: int) -> str:
    """Return a human readable label for a row, based on the first column."""
    if columns:
        value = row.get(columns[0], "").strip()
        if value:
            return value
    return f"row{index}"
