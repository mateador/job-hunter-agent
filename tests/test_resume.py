"""
Day 12: Tests for robust resume functionality.
Run with: pytest tests/test_resume.py -v
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import pytest
from src.job_agent.checkpoint import (
    CheckpointManager,
    CheckpointError,
    CorruptedCheckpointError,
    REQUIRED_STATE_KEYS,
)

# ── Helpers ──

def _valid_state(**overrides):
    """Build a valid checkpoint state with optional overrides."""
    base = {
        "search_query": "python engineer",
        "jobs_found": [{"id": "j1"}, {"id": "j2"}, {"id": "j3"}],
        "jobs_processed": ["j1"],
        "applications_generated": [{"job_id": "j1", "cover_letter": "hi", "cv_bullets": []}],
        "agent_messages": [{"role": "user", "content": "search"}],
        "status": "in_progress",
    }
    base.update(overrides)
    return base


def _write_raw_checkpoint(path: Path, checkpoint: dict):
    """Append a raw checkpoint dict as a JSONL line."""
    with open(path, "a") as f:
        f.write(json.dumps(checkpoint) + "\n")


# ── Test: load specific checkpoint by ID ──

def test_load_specific_checkpoint(tmp_path):
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test")

    manager.save_checkpoint(_valid_state(status="search_complete"))
    manager.save_checkpoint(_valid_state(jobs_processed=["j1", "j2"]))
    manager.save_checkpoint(_valid_state(jobs_processed=["j1", "j2", "j3"], status="completed"))

    # Load checkpoint 2 specifically
    state = manager.load_checkpoint(2)
    assert state["jobs_processed"] == ["j1", "j2"]
    assert manager.checkpoint_counter == 2


def test_load_nonexistent_checkpoint_id(tmp_path):
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test")
    manager.save_checkpoint(_valid_state())

    with pytest.raises(CheckpointError, match="not found"):
        manager.load_checkpoint(99)


# ── Test: state validation ──

def test_validate_state_missing_keys():
    bad_state = {"search_query": "test"}  # missing most keys
    with pytest.raises(CorruptedCheckpointError, match="Missing required"):
        CheckpointManager.validate_state(bad_state)


def test_validate_state_invalid_status():
    bad_state = _valid_state(status="banana")
    with pytest.raises(CorruptedCheckpointError, match="Invalid status"):
        CheckpointManager.validate_state(bad_state)


def test_validate_state_wrong_types():
    bad_state = _valid_state(jobs_found="not a list")
    with pytest.raises(CorruptedCheckpointError, match="jobs_found must be a list"):
        CheckpointManager.validate_state(bad_state)


def test_validate_state_valid():
    # Should not raise
    CheckpointManager.validate_state(_valid_state())


# ── Test: corrupted checkpoint handling ──

def test_corrupted_line_is_skipped(tmp_path):
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test")
    cp_file = manager.get_checkpoint_path()

    # Write a corrupted line followed by a valid one
    with open(cp_file, "w") as f:
        f.write("THIS IS NOT JSON\n")
        f.write(json.dumps({
            "timestamp": "2026-01-01T00:00:00",
            "checkpoint_id": 1,
            "run_id": "test",
            "state": _valid_state()
        }) + "\n")

    # Should skip the bad line and load the valid one
    state = manager.load_latest_checkpoint()
    assert state is not None
    assert state["status"] == "in_progress"


def test_all_corrupted_raises(tmp_path):
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test")
    cp_file = manager.get_checkpoint_path()

    with open(cp_file, "w") as f:
        f.write("GARBAGE\n")
        f.write("MORE GARBAGE\n")

    with pytest.raises(CorruptedCheckpointError, match="No valid checkpoints"):
        manager.load_latest_checkpoint()


# ── Test: find interrupted runs ──

def test_find_interrupted_runs(tmp_path):
    # Run 1: completed
    m1 = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="run_completed")
    m1.save_checkpoint(_valid_state(status="completed"))

    # Run 2: interrupted mid-processing
    m2 = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="run_interrupted")
    m2.save_checkpoint(_valid_state(status="in_progress", jobs_processed=["j1"]))

    # Run 3: crashed after search
    m3 = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="run_crashed")
    m3.save_checkpoint(_valid_state(status="search_complete", jobs_processed=[]))

    scanner = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="scan")
    interrupted = scanner.find_interrupted_runs()

    run_ids = {r["run_id"] for r in interrupted}
    assert "run_interrupted" in run_ids
    assert "run_crashed" in run_ids
    assert "run_completed" not in run_ids

    # Check progress reporting
    interrupted_run = next(r for r in interrupted if r["run_id"] == "run_interrupted")
    assert interrupted_run["progress"] == "1/3 jobs processed"


# ── Test: query mismatch detection (agent_runner level) ──

def test_resume_query_mismatch(tmp_path, monkeypatch):
    """
    Verify that resuming with a different query raises ResumeError.
    We test this at the agent_runner level by mocking dependencies.
    """
    from unittest.mock import MagicMock
    
    # Set a dummy API key so LLMClient.__init__ doesn't raise
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    
    from src.job_agent.agent_runner import AgentRunner, ResumeError

    audit = MagicMock()
    cp_manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="mismatch_test")
    cp_manager.save_checkpoint(_valid_state(search_query="original query"))

    runner = AgentRunner(
        audit_logger=audit,
        checkpoint_manager=cp_manager,
        model="gpt-4o-mini",
        max_jobs=5
    )

    with pytest.raises(ResumeError, match="Query mismatch"):
        runner.run(query="different query", resume=True)