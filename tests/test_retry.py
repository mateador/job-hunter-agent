"""
Day 9: Concrete tests for retry mechanism.
Run with: pytest tests/test_retry.py -v
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.job_agent.retry import execute_with_retry, MAX_ATTEMPTS
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.failures import RetryPolicy


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_failure_record(policy: RetryPolicy, category: str = "UNKNOWN"):
    """Build a mock FailureRecord with the attributes retry.py accesses."""
    record = MagicMock()
    record.retry_policy = policy
    record.category = category
    record.model_dump.return_value = {
        "category": category,
        "retry_policy": policy.value,
    }
    return record


def _read_trace(trace_dir: Path) -> list[dict]:
    """Read all JSONL events from the most recent trace file."""
    trace_files = sorted(trace_dir.glob("trace_*.jsonl"))
    assert trace_files, "No trace file was created"
    with open(trace_files[-1]) as f:
        return [json.loads(line) for line in f if line.strip()]


# ─────────────────────────────────────────────
# TEST 1: RETRY_SAME — fails twice, succeeds on attempt 3
# ─────────────────────────────────────────────

@patch("src.job_agent.retry.time.sleep")  # skip real delays
@patch("src.job_agent.retry.classify_exception")
def test_retry_same_succeeds_on_third_attempt(
    mock_classify, mock_sleep, tmp_path
):
    """
    Simulates a TIMEOUT that triggers RETRY_SAME.
    The callable fails twice, then returns a real result.
    We verify:
      - The result is returned successfully
      - sleep was called with exponential delays (1s, 2s)
      - The audit trail has the correct attempt sequence
    """
    # Every exception from this callable is classified as RETRY_SAME
    mock_classify.return_value = _make_failure_record(
        RetryPolicy.RETRY_SAME, "TIMEOUT"
    )

    # Callable: fail, fail, succeed
    call_count = 0
    def flaky_call(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("simulated timeout")
        return {"jobs": ["job_1", "job_2"]}

    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))

    result = execute_with_retry(
        func=flaky_call,
        args=(),
        kwargs={"query": "python engineer"},
        audit_logger=audit,
        tool_name="search_freehire",
    )

    # ── Assert result ──
    assert result == {"jobs": ["job_1", "job_2"]}
    assert call_count == 3

    # ── Assert backoff delays ──
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1.0)   # attempt 1 → 2: 1 * 2^0
    mock_sleep.assert_any_call(2.0)   # attempt 2 → 3: 1 * 2^1

    # ── Assert audit trail ──
    events = _read_trace(tmp_path / "traces")
    attempt_events = [e for e in events if e["event_type"] == "attempt"]

    # 3 starts + 2 failures + 1 success = 6 attempt events
    starts   = [e for e in attempt_events if e["status"] == "start"]
    failures = [e for e in attempt_events if e["status"] == "failure"]
    successes = [e for e in attempt_events if e["status"] == "success"]

    assert len(starts) == 3
    assert len(failures) == 2
    assert len(successes) == 1
    assert [e["attempt_number"] for e in starts] == [1, 2, 3]


# ─────────────────────────────────────────────
# TEST 2: RETRY_MODIFIED — fails once, retries with adjusted kwargs
# ─────────────────────────────────────────────

@patch("src.job_agent.retry.time.sleep")
@patch("src.job_agent.retry.classify_exception")
def test_retry_modified_adjusts_kwargs_and_succeeds(
    mock_classify, mock_sleep, tmp_path
):
    """
    Simulates CONTEXT_OVERFLOW → RETRY_MODIFIED.
    The callable fails on attempt 1. The modify_kwargs_fn halves
    the 'limit' parameter. The callable succeeds on attempt 2.
    We verify:
      - kwargs were actually modified before the second call
      - A 'modified' event was logged
      - Only one retry happened (not three)
    """
    mock_classify.return_value = _make_failure_record(
        RetryPolicy.RETRY_MODIFIED, "CONTEXT_OVERFLOW"
    )

    received_kwargs = []

    def overflow_call(**kwargs):
        received_kwargs.append(dict(kwargs))
        if len(received_kwargs) == 1:
            raise ValueError("context_length_exceeded: max tokens")
        return "shortened response"

    def halve_limit(kwargs_dict, attempt):
        kwargs_dict["limit"] = max(1, kwargs_dict.get("limit", 10) // 2)
        return kwargs_dict

    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))

    result = execute_with_retry(
        func=overflow_call,
        args=(),
        kwargs={"messages": ["long context"], "limit": 10},
        audit_logger=audit,
        tool_name="llm_chat",
        modify_kwargs_fn=halve_limit,
    )

    # ── Assert result ──
    assert result == "shortened response"
    assert len(received_kwargs) == 2

    # ── Assert kwargs were modified ──
    assert received_kwargs[0]["limit"] == 10   # first call: original
    assert received_kwargs[1]["limit"] == 5    # second call: halved

    # ── Assert only 1 retry (not 3) ──
    assert mock_sleep.call_count == 1

    # ── Assert audit trail has a 'modified' event ──
    events = _read_trace(tmp_path / "traces")
    attempt_events = [e for e in events if e["event_type"] == "attempt"]
    modified = [e for e in attempt_events if e["status"] == "modified"]
    assert len(modified) == 1
    assert modified[0]["details"]["new_kwargs"]["limit"] == 5


# ─────────────────────────────────────────────
# TEST 3: NOT_RETRYABLE — fails immediately, no retry
# ─────────────────────────────────────────────

@patch("src.job_agent.retry.time.sleep")
@patch("src.job_agent.retry.classify_exception")
def test_not_retryable_fails_immediately(
    mock_classify, mock_sleep, tmp_path
):
    """
    Simulates AUTH_ERROR → NOT_RETRYABLE.
    The callable fails once. We verify:
      - The exception propagates immediately
      - sleep was NEVER called (no backoff)
      - The audit trail has exactly 1 start + 1 failure
    """
    mock_classify.return_value = _make_failure_record(
        RetryPolicy.NOT_RETRYABLE, "AUTH_ERROR"
    )

    call_count = 0
    def auth_fail_call(**kwargs):
        nonlocal call_count
        call_count += 1
        raise PermissionError("401 Unauthorized: invalid API key")

    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))

    with pytest.raises(PermissionError, match="401 Unauthorized"):
        execute_with_retry(
            func=auth_fail_call,
            args=(),
            kwargs={},
            audit_logger=audit,
            tool_name="llm_chat",
        )

    # ── Assert no retry happened ──
    assert call_count == 1
    mock_sleep.assert_not_called()

    # ── Assert audit trail ──
    events = _read_trace(tmp_path / "traces")
    attempt_events = [e for e in events if e["event_type"] == "attempt"]
    starts   = [e for e in attempt_events if e["status"] == "start"]
    failures = [e for e in attempt_events if e["status"] == "failure"]
    assert len(starts) == 1
    assert len(failures) == 1
    assert failures[0]["details"]["failure_record"]["category"] == "AUTH_ERROR"


# ─────────────────────────────────────────────
# TEST 4 (Bonus): RETRY_SAME exhausts all 3 attempts and raises
# ─────────────────────────────────────────────

@patch("src.job_agent.retry.time.sleep")
@patch("src.job_agent.retry.classify_exception")
def test_retry_same_exhausts_max_attempts(
    mock_classify, mock_sleep, tmp_path
):
    """
    The callable always fails. After 3 attempts the exception
    propagates. Verifies the hard ceiling works.
    """
    mock_classify.return_value = _make_failure_record(
        RetryPolicy.RETRY_SAME, "DEAD_API"
    )

    def always_fail(**kwargs):
        raise ConnectionError("503 Service Unavailable")

    audit = AuditLogger(trace_dir=str(tmp_path / "traces"))

    with pytest.raises(ConnectionError, match="503"):
        execute_with_retry(
            func=always_fail,
            args=(),
            kwargs={},
            audit_logger=audit,
            tool_name="search_freehire",
        )

    assert mock_sleep.call_count == 2  # slept after attempt 1 and 2, not after 3
    events = _read_trace(tmp_path / "traces")
    starts = [e for e in events if e.get("status") == "start"]
    assert len(starts) == MAX_ATTEMPTS  # exactly 3