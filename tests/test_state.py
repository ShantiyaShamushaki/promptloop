from __future__ import annotations

from app.state import COMPLETED, FAILED, PENDING, StateManager


def _manager(tmp_path, total=3):
    state = StateManager(tmp_path / "manifest.json")
    state.initialize(total, "inputs/inputs.csv", "inputs/prompt.md")
    return state


def test_initialize_marks_all_rows_pending(tmp_path):
    state = _manager(tmp_path)
    assert state.status(1) == PENDING
    assert state.should_process(1) is True


def test_mark_completed_and_skip(tmp_path):
    state = _manager(tmp_path)
    state.mark_completed(1, "responses/0001_NVIDIA.md")
    assert state.is_completed(1) is True
    assert state.should_process(1) is False
    assert state.row(1).output == "responses/0001_NVIDIA.md"


def test_failed_row_rerun_policy(tmp_path):
    state = _manager(tmp_path)
    state.mark_failed(2, "timeout")
    assert state.should_process(2, rerun_failed=True) is True
    assert state.should_process(2, rerun_failed=False) is False


def test_attempts_increment(tmp_path):
    state = _manager(tmp_path)
    state.mark_in_progress(1)
    state.mark_failed(1, "boom")
    state.mark_in_progress(1)
    assert state.row(1).attempts == 2


def test_summary_counts(tmp_path):
    state = _manager(tmp_path)
    state.mark_completed(1, "responses/0001.md")
    state.mark_failed(2, "timeout")
    summary = state.summary()
    assert summary[COMPLETED] == 1
    assert summary[FAILED] == 1
    assert summary[PENDING] == 1


def test_save_and_load_roundtrip(tmp_path):
    state = _manager(tmp_path)
    state.mark_completed(1, "responses/0001.md")

    reloaded = StateManager(tmp_path / "manifest.json")
    reloaded.load()
    assert reloaded.is_completed(1) is True
    assert reloaded.data["total_rows"] == 3
