"""
Day 15: End-to-end recovery demo test.

This test simulates a real-world failure scenario:
1. Agent starts processing 5 jobs
2. Job 3 fails (simulated via exception)
3. Agent continues and completes remaining jobs
4. Verify final state with partial completion

Run with: pytest tests/test_recovery_demo.py -v -s
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import patch, MagicMock

from src.job_agent.agent_runner import AgentRunner
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager
from src.job_agent.models import Application


def test_full_recovery_cycle(tmp_path, monkeypatch):
    """
    Full recovery cycle test with partial completion.

    Phase 1: Agent processes jobs 1-2, job 3 fails, jobs 4-5 succeed.
    Phase 2: Resume from checkpoint (should skip already-processed jobs).
    Phase 3: Verify final state has 4 successful applications and 1 failure.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    audit_dir = tmp_path / "traces"
    checkpoint_dir = tmp_path / "checkpoints"
    run_id = "recovery_demo"

    # ── PHASE 1: Initial run with one failure ──
    print("\n" + "=" * 60)
    print("PHASE 1: Initial run (job 3 will fail)")
    print("=" * 60)

    audit1 = AuditLogger(trace_dir=str(audit_dir))
    cp_manager1 = CheckpointManager(
        checkpoint_dir=str(checkpoint_dir),
        run_id=run_id
    )

    call_count = 0

    def mock_generate_application_phase1(job, llm_client, audit_logger, **kwargs):
        nonlocal call_count
        call_count += 1
        print(f"  [Phase 1] Processing job {call_count}: {job.id}")

        if call_count == 3:
            print(f"  [Phase 1] ❌ Job {job.id} fails")
            raise ValueError("Simulated job failure")

        return Application(
            job_id=job.id,
            cover_letter=f"Cover letter for {job.title}",
            cv_bullets=[f"Tailored bullet for {job.title}"]
        )

    all_jobs = [
        {"id": f"job_{i}", "title": f"Role {i}", "company": f"Company {i}"}
        for i in range(1, 6)
    ]

    with patch("src.job_agent.agent_runner.generate_application",
               side_effect=mock_generate_application_phase1):
        with patch("src.job_agent.agent_runner.search_freehire",
                   return_value=all_jobs):

            runner1 = AgentRunner(
                audit_logger=audit1,
                checkpoint_manager=cp_manager1,
                model="gpt-4o-mini",
                max_jobs=5
            )

            result1 = runner1.run(query="python engineer london")

    # Verify partial completion after phase 1
    print(f"\n  [Phase 1] Final status: {result1['status']}")
    print(f"  [Phase 1] Successful applications: {len(result1['applications'])}")
    print(f"  [Phase 1] Failed jobs: {len(result1['failed_jobs'])}")

    assert result1["status"] == "partial"
    assert len(result1["applications"]) == 4, "Should have 4 successful applications"
    assert len(result1["failed_jobs"]) == 1, "Should have 1 failed job"
    assert result1["failed_jobs"][0].job_id == "job_3"

    # Verify checkpoint was saved
    checkpoints = cp_manager1.list_checkpoints()
    print(f"\n  [Phase 1] Checkpoints saved: {len(checkpoints)}")
    assert len(checkpoints) >= 2, "Should have at least search_complete + completion checkpoints"

    last_state = cp_manager1.load_latest_checkpoint()
    print(f"  [Phase 1] Last checkpoint status: {last_state['status']}")
    print(f"  [Phase 1] Jobs processed: {len(last_state['jobs_processed'])}")
    assert len(last_state["jobs_processed"]) == 5, "All 5 jobs should be marked as processed"

    # ── PHASE 2: Resume from checkpoint ──
    print("\n" + "=" * 60)
    print("PHASE 2: Resume from checkpoint (should skip all jobs)")
    print("=" * 60)

    audit2 = AuditLogger(trace_dir=str(audit_dir))
    cp_manager2 = CheckpointManager(
        checkpoint_dir=str(checkpoint_dir),
        run_id=run_id  # Same run_id = same checkpoint file
    )

    def mock_generate_application_phase2(job, llm_client, audit_logger, **kwargs):
        # This should never be called since all jobs are already processed
        raise AssertionError(f"Should not process job {job.id} - already in checkpoint")

    with patch("src.job_agent.agent_runner.generate_application",
               side_effect=mock_generate_application_phase2):
        with patch("src.job_agent.agent_runner.search_freehire",
                   return_value=all_jobs):

            runner2 = AgentRunner(
                audit_logger=audit2,
                checkpoint_manager=cp_manager2,
                model="gpt-4o-mini",
                max_jobs=5
            )

            result2 = runner2.run(
                query="python engineer london",
                resume=True
            )

    # ── PHASE 3: Verify final state ──
    print("\n" + "=" * 60)
    print("PHASE 3: Verify final state after resume")
    print("=" * 60)

    print(f"  [Phase 3] Final status: {result2['status']}")
    print(f"  [Phase 3] Total applications: {len(result2['applications'])}")
    print(f"  [Phase 3] Failed jobs: {len(result2['failed_jobs'])}")

    # Resume should preserve the partial state
    assert result2["status"] == "partial"
    assert len(result2["applications"]) == 4, "Should still have 4 successful applications"
    assert len(result2["failed_jobs"]) == 1, "Should still have 1 failed job"
    assert result2["failed_jobs"][0].job_id == "job_3"

    # Verify checkpoint reflects the same state
    final_state = cp_manager2.load_latest_checkpoint()
    assert final_state["status"] == "partial"
    assert len(final_state["jobs_processed"]) == 5

    print("\n" + "=" * 60)
    print("✅ RECOVERY DEMO PASSED")
    print("=" * 60)
    print(f"  - Job 3 failed during initial run")
    print(f"  - Agent continued and completed jobs 4-5")
    print(f"  - Final state: 4/5 jobs successful, 1 failed")
    print(f"  - Resume preserved the partial state")
    print(f"  - Checkpoint file: {cp_manager2.get_checkpoint_path()}")
    print(f"  - Audit trail: {audit_dir}")
    print("=" * 60 + "\n")


def test_recovery_preserves_partial_failures(tmp_path, monkeypatch):
    """
    Verify that when we resume, previously-failed jobs stay failed
    (not retried) and new jobs can still succeed.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    audit_dir = tmp_path / "traces"
    checkpoint_dir = tmp_path / "checkpoints"
    run_id = "partial_failure_recovery"

    # ── Phase 1: Process 3 jobs, 1 fails ──
    audit1 = AuditLogger(trace_dir=str(audit_dir))
    cp_manager1 = CheckpointManager(
        checkpoint_dir=str(checkpoint_dir),
        run_id=run_id
    )

    call_count = 0

    def mock_phase1(job, llm_client, audit_logger, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ValueError("Job 2 fails permanently")
        return Application(
            job_id=job.id,
            cover_letter=f"Cover for {job.title}",
            cv_bullets=[f"Bullet for {job.title}"]
        )

    with patch("src.job_agent.agent_runner.generate_application",
               side_effect=mock_phase1):
        with patch("src.job_agent.agent_runner.search_freehire",
                   return_value=[
                       {"id": "j1", "title": "Job 1", "company": "C1"},
                       {"id": "j2", "title": "Job 2", "company": "C2"},
                       {"id": "j3", "title": "Job 3", "company": "C3"},
                   ]):

            runner1 = AgentRunner(
                audit_logger=audit1,
                checkpoint_manager=cp_manager1,
                model="gpt-4o-mini",
                max_jobs=3
            )

            result1 = runner1.run(query="test query")

    # Verify partial completion
    assert result1["status"] == "partial"
    assert len(result1["applications"]) == 2
    assert len(result1["failed_jobs"]) == 1
    assert result1["failed_jobs"][0].job_id == "j2"

    # ── Phase 2: Resume (should not retry failed job) ──
    audit2 = AuditLogger(trace_dir=str(audit_dir))
    cp_manager2 = CheckpointManager(
        checkpoint_dir=str(checkpoint_dir),
        run_id=run_id
    )

    def mock_phase2(job, llm_client, audit_logger, **kwargs):
        # Should not be called for j2 (already failed)
        assert job.id != "j2", f"Should not retry failed job {job.id}"
        return Application(
            job_id=job.id,
            cover_letter=f"Cover for {job.title}",
            cv_bullets=[f"Bullet for {job.title}"]
        )

    with patch("src.job_agent.agent_runner.generate_application",
               side_effect=mock_phase2):
        with patch("src.job_agent.agent_runner.search_freehire",
                   return_value=[
                       {"id": "j1", "title": "Job 1", "company": "C1"},
                       {"id": "j2", "title": "Job 2", "company": "C2"},
                       {"id": "j3", "title": "Job 3", "company": "C3"},
                   ]):

            runner2 = AgentRunner(
                audit_logger=audit2,
                checkpoint_manager=cp_manager2,
                model="gpt-4o-mini",
                max_jobs=3
            )

            result2 = runner2.run(query="test query", resume=True)

    # Verify failed job is preserved, not retried
    assert result2["status"] == "partial"
    assert len(result2["applications"]) == 2
    assert len(result2["failed_jobs"]) == 1
    assert result2["failed_jobs"][0].job_id == "j2"