from unittest.mock import MagicMock, patch

import pytest

from src.job_agent.audit_logger import AuditLogger
from src.job_agent.tools import (FREEHIRE_BASE_URL, FreeHireIgnoredParamError,
                                 search_freehire)


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def logger(tmp_path):
    return AuditLogger(trace_dir=str(tmp_path))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("FREEHIRE_SEARCH_URL", "FREEHIRE_QUERY_PARAM", "FREEHIRE_LIMIT_PARAM",
              "FREEHIRE_DESCRIPTION_FORMAT"):
        monkeypatch.delenv(k, raising=False)


def test_defaults_to_agent_endpoint(logger):
    assert FREEHIRE_BASE_URL.endswith("/agent/jobs/search")
    with patch("src.job_agent.tools.requests.get", return_value=_response({"data": [{"id": "1"}], "meta": {}})) as get:
        jobs = search_freehire("python engineer", limit=3, audit_logger=logger)
    assert jobs == [{"id": "1"}]
    args, kwargs = get.call_args
    assert args[0] == FREEHIRE_BASE_URL
    assert kwargs["params"]["q"] == "python engineer" and kwargs["params"]["limit"] == 3
    assert kwargs["params"]["regions"] == "uk"


def test_env_overrides_url_and_param_names(logger, monkeypatch):
    monkeypatch.setenv("FREEHIRE_SEARCH_URL", "https://example.test/search")
    monkeypatch.setenv("FREEHIRE_QUERY_PARAM", "keywords")
    monkeypatch.setenv("FREEHIRE_LIMIT_PARAM", "n")
    with patch("src.job_agent.tools.requests.get", return_value=_response({"data": [], "meta": {}})) as get:
        search_freehire("x", limit=2, audit_logger=logger)
    args, kwargs = get.call_args
    assert args[0] == "https://example.test/search"
    assert kwargs["params"]["keywords"] == "x" and kwargs["params"]["n"] == 2
    assert "q" not in kwargs["params"]


def test_ignored_query_param_raises_and_is_not_retried(logger):
    payload = {"data": [{"id": "1"}], "meta": {"ignored_params": [{"param": "q"}]}}
    with patch("src.job_agent.tools.requests.get", return_value=_response(payload)) as get:
        with pytest.raises(FreeHireIgnoredParamError):
            search_freehire("python", audit_logger=logger)
    assert get.call_count == 1


def test_other_ignored_params_are_logged_but_allowed(logger):
    payload = {"data": [{"id": "1"}], "meta": {"total": 5, "ignored_params": [{"param": "location"}]}}
    with patch("src.job_agent.tools.requests.get", return_value=_response(payload)):
        assert search_freehire("python", audit_logger=logger) == [{"id": "1"}]
    trace = logger.trace_file.read_text()
    assert '"search_meta"' in trace and "location" in trace
