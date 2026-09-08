"""
Day 10: Tests for timeout enforcement.
Run with: pytest tests/test_timeouts.py -v
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import patch, MagicMock
import requests
import openai

from src.job_agent.failures import classify_exception, FailureCategory, RetryPolicy
from src.job_agent.config import LLM_TIMEOUT, FREEHIRE_TIMEOUT, DUCKDUCKGO_TIMEOUT


def test_timeout_exceptions_are_classified_as_timeout():
    """Verify that timeout exceptions map to TIMEOUT → RETRY_SAME."""
    
    # requests.Timeout
    record = classify_exception(requests.Timeout("Connection timed out"))
    assert record.category == FailureCategory.TIMEOUT
    assert record.retry_policy == RetryPolicy.RETRY_SAME
    
    # openai.APITimeoutError
    record = classify_exception(openai.APITimeoutError(request=MagicMock()))
    assert record.category == FailureCategory.TIMEOUT
    assert record.retry_policy == RetryPolicy.RETRY_SAME
    
    # Generic TimeoutError
    record = classify_exception(TimeoutError("Operation timed out"))
    assert record.category == FailureCategory.TIMEOUT
    assert record.retry_policy == RetryPolicy.RETRY_SAME


def test_timeout_config_values_are_reasonable():
    """Verify timeout values are set to reasonable defaults."""
    assert LLM_TIMEOUT >= 30.0, "LLM timeout should be at least 30s"
    assert FREEHIRE_TIMEOUT >= 10.0, "FreeHire timeout should be at least 10s"
    assert DUCKDUCKGO_TIMEOUT >= 5.0, "DuckDuckGo timeout should be at least 5s"
    assert LLM_TIMEOUT > FREEHIRE_TIMEOUT, "LLM timeout should be longer than FreeHire"


@patch("src.job_agent.tools.requests.get")
def test_freehire_uses_config_timeout(mock_get):
    """Verify FreeHire tool uses FREEHIRE_TIMEOUT from config."""
    from src.job_agent.tools import search_freehire
    from src.job_agent.audit_logger import AuditLogger
    
    mock_response = MagicMock()
    mock_response.json.return_value = {"jobs": []}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response
    
    audit = AuditLogger(trace_dir="/tmp/test_traces")
    search_freehire("python", audit_logger=audit)
    
    # Verify timeout was passed to requests.get
    call_kwargs = mock_get.call_args[1]
    assert "timeout" in call_kwargs
    assert call_kwargs["timeout"] == FREEHIRE_TIMEOUT


@patch("src.job_agent.tools.DDGS")
def test_duckduckgo_uses_config_timeout(mock_ddgs):
    """Verify DuckDuckGo tool uses DUCKDUCKGO_TIMEOUT from config."""
    from src.job_agent.tools import search_duckduckgo
    from src.job_agent.audit_logger import AuditLogger
    
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = []
    mock_ddgs.return_value.__enter__.return_value = mock_ddgs_instance
    
    audit = AuditLogger(trace_dir="/tmp/test_traces")
    search_duckduckgo("python jobs", audit_logger=audit)
    
    # Verify timeout was passed to DDGS constructor
    mock_ddgs.assert_called_once()
    call_kwargs = mock_ddgs.call_args[1]
    assert "timeout" in call_kwargs
    assert call_kwargs["timeout"] == DUCKDUCKGO_TIMEOUT