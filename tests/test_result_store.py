from __future__ import annotations

import pytest

from app.errors import ResultStoreError
from app.result_store import ResultStore, build_filename, sanitize_label


def test_sanitize_label_strips_unsafe_characters():
    assert sanitize_label("ASML/Netherlands: 2024") == "ASML_Netherlands_2024"
    assert sanitize_label("   ") == "row"


def test_build_filename_zero_pads_index():
    assert build_filename(1, "NVIDIA") == "0001_NVIDIA.md"
    assert build_filename(12, "Toyota") == "0012_Toyota.md"


def test_save_writes_response_file(tmp_path):
    store = ResultStore(tmp_path / "output")
    path = store.save(
        index=1,
        label="NVIDIA",
        prompt="Analyze NVIDIA",
        response="NVIDIA is a company.",
        input_row={"company": "NVIDIA"},
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "# NVIDIA" in content
    assert "Analyze NVIDIA" in content
    assert "NVIDIA is a company." in content
    assert store.relative(path) == "responses/0001_NVIDIA.md"


def test_save_prevents_overwrite_by_default(tmp_path):
    store = ResultStore(tmp_path / "output")
    store.save(index=1, label="NVIDIA", prompt="p", response="r")
    with pytest.raises(ResultStoreError):
        store.save(index=1, label="NVIDIA", prompt="p", response="r")


def test_save_allows_overwrite_when_requested(tmp_path):
    store = ResultStore(tmp_path / "output")
    store.save(index=1, label="NVIDIA", prompt="p", response="old")
    path = store.save(index=1, label="NVIDIA", prompt="p", response="new", overwrite=True)
    assert "new" in path.read_text(encoding="utf-8")
