import sys
from unittest.mock import patch

import pytest

from src.job_agent.agent_runner import AgentRunner, InvalidQueryError
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager
from src.job_agent.main import main


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return AgentRunner(audit_logger=AuditLogger(trace_dir=str(tmp_path / "t")),
                       checkpoint_manager=CheckpointManager(checkpoint_dir=str(tmp_path / "c"), run_id="r"))


@pytest.mark.parametrize("query", ["", " ", "\t\n  "])
def test_runner_rejects_blank_query_without_searching(runner, query):
    with patch("src.job_agent.agent_runner.search_freehire") as search:
        with pytest.raises(InvalidQueryError):
            runner.run(query)
    search.assert_not_called()


def test_runner_accepts_normal_query(runner):
    with patch("src.job_agent.agent_runner.search_freehire", return_value=[]) as search:
        result = runner.run("python engineer")
    search.assert_called_once()
    assert result["jobs_found"] == []


def test_cli_rejects_blank_query(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["job-agent", " "])
    with patch("src.job_agent.agent_runner.search_freehire") as search:
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 2
    assert "empty" in capsys.readouterr().err
    search.assert_not_called()
