"""
Day 11: Tests for checkpoint functionality.
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import pytest
from src.job_agent.checkpoint import CheckpointManager


def test_save_and_load_checkpoint(tmp_path):
    """Test saving and loading a checkpoint."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test_run")
    
    state = {
        "search_query": "python engineer",
        "jobs_found": [{"id": "job_1"}, {"id": "job_2"}],
        "jobs_processed": ["job_1"],
        "applications_generated": [{"job_id": "job_1", "cover_letter": "test"}],
        "agent_messages": [{"role": "user", "content": "test"}],
        "status": "in_progress"
    }
    
    # Save checkpoint
    checkpoint_id = manager.save_checkpoint(state)
    assert checkpoint_id == 1
    
    # Load checkpoint
    loaded_state = manager.load_latest_checkpoint()
    assert loaded_state is not None
    assert loaded_state["search_query"] == "python engineer"
    assert len(loaded_state["jobs_found"]) == 2
    assert loaded_state["jobs_processed"] == ["job_1"]
    assert loaded_state["status"] == "in_progress"


def test_multiple_checkpoints(tmp_path):
    """Test that multiple checkpoints are saved and latest is loaded."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test_run")
    
    # Save first checkpoint
    state1 = {"status": "step_1", "counter": 1}
    manager.save_checkpoint(state1)
    
    # Save second checkpoint
    state2 = {"status": "step_2", "counter": 2}
    manager.save_checkpoint(state2)
    
    # Save third checkpoint
    state3 = {"status": "step_3", "counter": 3}
    manager.save_checkpoint(state3)
    
    # Load should return the latest (third) checkpoint
    loaded = manager.load_latest_checkpoint()
    assert loaded["status"] == "step_3"
    assert loaded["counter"] == 3
    
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
    
    manager.save_checkpoint({"status": "step_1"})
    manager.save_checkpoint({"status": "step_2"})
    manager.save_checkpoint({"status": "step_3"})
    
    checkpoints = manager.list_checkpoints()
    assert len(checkpoints) == 3
    assert checkpoints[0]["checkpoint_id"] == 1
    assert checkpoints[1]["checkpoint_id"] == 2
    assert checkpoints[2]["checkpoint_id"] == 3


def test_checkpoint_file_structure(tmp_path):
    """Test that checkpoint file is valid JSONL."""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path), run_id="test_run")
    
    state = {"test": "data"}
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