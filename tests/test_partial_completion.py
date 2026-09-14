"""
Day 13: Tests for partial completion functionality.
Run with: pytest tests/test_partial_completion.py -v
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import MagicMock, patch
from src.job_agent.agent_runner import AgentRunner
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager
from src.job_agent.models import Job, Application, FailedJob


def test_partial_completion_with_failures(tmp_path, monkeypatch):
    """Test that agent continues processing after failures."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))
    cp_manager = CheckpointManager(checkpoint_dir=str(tmp_path / "checkpoints"), run_id="test")
    
    # Mock LLM client to succeed for first 2 jobs, fail for third
    call_count = 0
    def mock_generate_application(job, llm_client, audit_logger):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return Application(
                job_id=job.id,
                cover_letter=f"Cover for {job.title}",
                cv_bullets=[f"Bullet for {job.title}"]
            )
        else:
            raise ValueError("Simulated failure")
    
    with patch("src.job_agent.agent_runner.generate_application", side_effect=mock_generate_application):
        with patch("src.job_agent.agent_runner.search_freehire") as mock_search:
            # Return 3 jobs
            mock_search.return_value = [
                {"id": "j1", "title": "Job 1", "company": "Company 1"},
                {"id": "j2", "title": "Job 2", "company": "Company 2"},
                {"id": "j3", "title": "Job 3", "company": "Company 3"},
            ]
            
            runner = AgentRunner(
                audit_logger=audit,
                checkpoint_manager=cp_manager,
                model="gpt-4o-mini",
                max_jobs=3
            )
            
            result = runner.run(query="test query")
    
    # Verify partial completion
    assert result["status"] == "partial"
    assert len(result["applications"]) == 2
    assert len(result["failed_jobs"]) == 1
    assert result["failed_jobs"][0].job_id == "j3"
    assert result["failed_jobs"][0].error_category == "UNKNOWN"


def test_full_completion_no_failures(tmp_path, monkeypatch):
    """Test that status is 'completed' when all jobs succeed."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))
    cp_manager = CheckpointManager(checkpoint_dir=str(tmp_path / "checkpoints"), run_id="test")
    
    def mock_generate_application(job, llm_client, audit_logger):
        return Application(
            job_id=job.id,
            cover_letter=f"Cover for {job.title}",
            cv_bullets=[f"Bullet for {job.title}"]
        )
    
    with patch("src.job_agent.agent_runner.generate_application", side_effect=mock_generate_application):
        with patch("src.job_agent.agent_runner.search_freehire") as mock_search:
            mock_search.return_value = [
                {"id": "j1", "title": "Job 1", "company": "Company 1"},
                {"id": "j2", "title": "Job 2", "company": "Company 2"},
            ]
            
            runner = AgentRunner(
                audit_logger=audit,
                checkpoint_manager=cp_manager,
                model="gpt-4o-mini",
                max_jobs=2
            )
            
            result = runner.run(query="test query")
    
    assert result["status"] == "completed"
    assert len(result["applications"]) == 2
    assert len(result["failed_jobs"]) == 0


def test_total_failure(tmp_path, monkeypatch):
    """Test that status is 'failed' when all jobs fail."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))
    cp_manager = CheckpointManager(checkpoint_dir=str(tmp_path / "checkpoints"), run_id="test")
    
    def mock_generate_application(job, llm_client, audit_logger):
        raise ValueError("All jobs fail")
    
    with patch("src.job_agent.agent_runner.generate_application", side_effect=mock_generate_application):
        with patch("src.job_agent.agent_runner.search_freehire") as mock_search:
            mock_search.return_value = [
                {"id": "j1", "title": "Job 1", "company": "Company 1"},
            ]
            
            runner = AgentRunner(
                audit_logger=audit,
                checkpoint_manager=cp_manager,
                model="gpt-4o-mini",
                max_jobs=1
            )
            
            result = runner.run(query="test query")
    
    assert result["status"] == "failed"
    assert len(result["applications"]) == 0
    assert len(result["failed_jobs"]) == 1


def test_checkpoint_includes_failures(tmp_path, monkeypatch):
    """Test that checkpoint captures failed jobs."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    
    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))
    cp_manager = CheckpointManager(checkpoint_dir=str(tmp_path / "checkpoints"), run_id="test")
    
    call_count = 0
    def mock_generate_application(job, llm_client, audit_logger):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("First job fails")
        return Application(
            job_id=job.id,
            cover_letter=f"Cover for {job.title}",
            cv_bullets=[f"Bullet for {job.title}"]
        )
    
    with patch("src.job_agent.agent_runner.generate_application", side_effect=mock_generate_application):
        with patch("src.job_agent.agent_runner.search_freehire") as mock_search:
            mock_search.return_value = [
                {"id": "j1", "title": "Job 1", "company": "Company 1"},
                {"id": "j2", "title": "Job 2", "company": "Company 2"},
            ]
            
            runner = AgentRunner(
                audit_logger=audit,
                checkpoint_manager=cp_manager,
                model="gpt-4o-mini",
                max_jobs=2
            )
            
            result = runner.run(query="test query")
    
    # Load checkpoint and verify it includes failures
    state = cp_manager.load_latest_checkpoint()
    assert len(state["failed_jobs"]) == 1
    assert state["failed_jobs"][0]["job_id"] == "j1"