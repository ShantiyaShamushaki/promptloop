from __future__ import annotations

import pytest

from app.errors import InputError
from app.input_loader import load_input, row_label


def _write(tmp_path, text: str):
    path = tmp_path / "inputs.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_valid_csv(tmp_path):
    path = _write(
        tmp_path,
        "company,industry,country\nNVIDIA,Semiconductors,USA\nToyota,Automotive,Japan\n",
    )
    data = load_input(path)
    assert data.columns == ["company", "industry", "country"]
    assert len(data) == 2
    assert data.rows[0]["company"] == "NVIDIA"


def test_missing_file(tmp_path):
    with pytest.raises(InputError):
        load_input(tmp_path / "missing.csv")


def test_empty_file(tmp_path):
    path = _write(tmp_path, "")
    with pytest.raises(InputError):
        load_input(path)


def test_duplicate_columns(tmp_path):
    path = _write(tmp_path, "company,company\nA,B\n")
    with pytest.raises(InputError):
        load_input(path)


def test_row_length_mismatch(tmp_path):
    path = _write(tmp_path, "company,country\nNVIDIA\n")
    with pytest.raises(InputError):
        load_input(path)


def test_header_only_is_valid_and_empty(tmp_path):
    path = _write(tmp_path, "company,country\n")
    data = load_input(path)
    assert len(data) == 0


def test_whitespace_and_blank_lines_are_handled(tmp_path):
    path = _write(
        tmp_path,
        "company, country\n  NVIDIA , USA \n\nToyota,Japan\n",
    )
    data = load_input(path)
    assert data.columns == ["company", "country"]
    assert data.rows[0] == {"company": "NVIDIA", "country": "USA"}
    assert data.rows[1] == {"company": "Toyota", "country": "Japan"}


def test_row_label_uses_first_column():
    row = {"company": "NVIDIA", "country": "USA"}
    assert row_label(row, ["company", "country"], 1) == "NVIDIA"


def test_row_label_falls_back_to_index():
    assert row_label({"company": ""}, ["company"], 3) == "row3"
