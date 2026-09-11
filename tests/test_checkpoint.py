"""
Day 11 + Day 12: Tests for checkpoint functionality.
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import pytest
from src.job_agent.checkpoint import CheckpointManager


# ── Helper ──

def _valid_state(**overrides):
    """Build a valid checkpoint state that passes Day 12 validation."""
    base = {
        "search_query": "python engineer",
        "jobs_found": [{"id": "j1"}, {"id": "j2"}, {"id": "j3"}],
        "jobs_processed": [],
        "applications_generated": [],
        "agent_messages": [{"role": "user", "content": "search"}],
        "status": "in_progress",
    }
    base.update(overrides)
    return base


def test_save_and_load_checkpoint(tmp_path):
    """Test saving and loading a checkpoint."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test_run")

    state = _valid_state(
        jobs_processed=["j1"],
        applications_generated=[{"job_id": "j1", "cover_letter": "test", "cv_bullets": []}]
    )

    # Save checkpoint
    checkpoint_id = manager.save_checkpoint(state)
    assert checkpoint_id == 1

    # Load checkpoint
    loaded_state = manager.load_latest_checkpoint()
    assert loaded_state is not None
    assert loaded_state["search_query"] == "python engineer"
    assert len(loaded_state["jobs_found"]) == 3
    assert loaded_state["jobs_processed"] == ["j1"]
    assert loaded_state["status"] == "in_progress"


def test_multiple_checkpoints(tmp_path):
    """Test that multiple checkpoints are saved and latest is loaded."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test_run")

    # Save first checkpoint
    manager.save_checkpoint(_valid_state(jobs_processed=[]))

    # Save second checkpoint
    manager.save_checkpoint(_valid_state(jobs_processed=["j1"]))

    # Save third checkpoint
    manager.save_checkpoint(_valid_state(jobs_processed=["j1", "j2"], status="completed"))

    # Load should return the latest (third) checkpoint
    loaded = manager.load_latest_checkpoint()
    assert loaded["jobs_processed"] == ["j1", "j2"]
    assert loaded["status"] == "completed"

    # Verify checkpoint counter incremented
    assert manager.checkpoint_counter == 3


def test_load_nonexistent_checkpoint(tmp_path):
    """Test loading when no checkpoint file exists."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="nonexistent")
    loaded = manager.load_latest_checkpoint()
    assert loaded is None


def test_list_checkpoints(tmp_path):
    """Test listing all checkpoints for a run."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test_run")

    manager.save_checkpoint(_valid_state())
    manager.save_checkpoint(_valid_state())
    manager.save_checkpoint(_valid_state())

    checkpoints = manager.list_checkpoints()
    assert len(checkpoints) == 3
    assert checkpoints[0]["checkpoint_id"] == 1
    assert checkpoints[1]["checkpoint_id"] == 2
    assert checkpoints[2]["checkpoint_id"] == 3


def test_checkpoint_file_structure(tmp_path):
    """Test that checkpoint file is valid JSONL."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test_run")

    state = _valid_state()
    manager.save_checkpoint(state)

    checkpoint_file = manager.get_checkpoint_path()
    assert checkpoint_file.exists()

    with open(checkpoint_file, "r") as f:
        line = f.readline()
        checkpoint = json.loads(line)

    assert "timestamp" in checkpoint
    assert "checkpoint_id" in checkpoint
    assert "run_id" in checkpoint
    assert "state" in checkpoint
    assert checkpoint["state"] == state