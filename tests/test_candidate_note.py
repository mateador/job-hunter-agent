"""The prompt must not contain personal details; an optional candidate note carries them instead."""
from types import SimpleNamespace

import pytest

from src.job_agent.agent_runner import AgentRunner, ResumeError
from src.job_agent.application_generator import generate_application
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager
from src.job_agent.models import Job

GOOD = ('{"tailored_cv_bullets": ["a", "b", "c"], "cover_letter": "Dear team, hello."}')


class CapturingClient:
    def __init__(self):
        self.prompts = []

    def chat(self, messages, **kwargs):
        self.prompts.append(messages[-1]["content"])
        return GOOD


def _prompt(tmp_path, **kwargs):
    client = CapturingClient()
    job = Job(id="j1", title="Engineer", company="Acme", description="desc")
    generate_application(job=job, llm_client=client, audit_logger=AuditLogger(trace_dir=str(tmp_path)), **kwargs)
    return client.prompts[0]


def test_the_default_prompt_contains_no_personal_details(tmp_path):
    prompt = _prompt(tmp_path, cv_text="Some CV text.")
    for personal in ("Cambridge", "Skilled Worker", "Dependant", "sponsorship"):
        assert personal not in prompt


def test_a_candidate_note_reaches_the_prompt(tmp_path):
    prompt = _prompt(tmp_path, cv_text="Some CV text.", candidate_note="Based in Lisbon; EU citizen.")
    assert "Candidate context" in prompt and "Based in Lisbon; EU citizen." in prompt


def test_a_blank_note_adds_nothing(tmp_path):
    assert "Candidate context" not in _prompt(tmp_path, cv_text="x", candidate_note="   ")


def test_resume_requires_the_note_again_when_the_run_used_one(tmp_path, monkeypatch):
    from unittest.mock import patch
    from src.job_agent.models import Application
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    listing = [{"id": f"j{i}", "title": f"Job {i}", "company": f"C{i}"} for i in (1, 2)]

    def make(note):
        return AgentRunner(
            audit_logger=AuditLogger(trace_dir=str(tmp_path / "t")),
            checkpoint_manager=CheckpointManager(checkpoint_dir=str(tmp_path / "c"), run_id="r"),
            max_jobs=2, candidate_note=note)

    def flaky(job, llm_client, audit_logger, **kwargs):
        if job.id == "j2":
            raise ValueError("transient")
        return Application(job_id=job.id, cover_letter="letter", cv_bullets=["b"])

    with patch("src.job_agent.agent_runner.search_freehire", return_value=listing), \
            patch("src.job_agent.agent_runner.generate_application", side_effect=flaky):
        assert make("Based in Lisbon").run("q")["status"] == "partial"
    with pytest.raises(ResumeError, match="candidate note"):
        make(None).run("", resume=True)


def test_the_runner_passes_the_note_to_the_generator(tmp_path, monkeypatch):
    from unittest.mock import patch
    from src.job_agent.models import Application
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    seen = {}

    def spy(job, llm_client, audit_logger, **kwargs):
        seen.update(kwargs)
        return Application(job_id=job.id, cover_letter="l", cv_bullets=["b"])

    runner = AgentRunner(audit_logger=AuditLogger(trace_dir=str(tmp_path / "t")),
                         checkpoint_manager=CheckpointManager(checkpoint_dir=str(tmp_path / "c"), run_id="r"),
                         max_jobs=1, candidate_note="Based in Lisbon")
    with patch("src.job_agent.agent_runner.search_freehire", return_value=[{"id": "j1", "title": "T", "company": "C"}]), \
            patch("src.job_agent.agent_runner.generate_application", side_effect=spy):
        runner.run("q")
    assert seen["candidate_note"] == "Based in Lisbon"
