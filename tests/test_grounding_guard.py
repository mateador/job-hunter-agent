import json
from unittest.mock import patch

import pytest

from src.job_agent.agent_runner import AgentRunner
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager
from src.job_agent.models import Application, CompanyResearch
from src.job_agent.report_generator import generate_report

CV = "Alexandre. Led 30 engineers across 5 projects. Eighteen years in delivery."
JOB = {"id": "j1", "title": "Platform Engineer", "company": "Acme",
       "description": "Build platforms. " * 60 + "Salary 60,000."}

CLEAN = {"tailored_cv_bullets": ["Led 30 engineers", "Delivered 5 projects", "Eighteen years of delivery"],
         "cover_letter": "Dear Acme,\n\nI led 30 engineers.\n\nBest,\nMe"}
INVENTED = {"tailored_cv_bullets": ["Cut deployment time by 40%", "Led 30 engineers", "Reduced errors by 25%"],
            "cover_letter": "Dear Acme,\n\nI cut errors by 25%.\n\nBest,\nMe"}


@pytest.fixture
def make_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def build(cv_text=CV):
        logger = AuditLogger(trace_dir=str(tmp_path / "t"))
        runner = AgentRunner(audit_logger=logger,
                             checkpoint_manager=CheckpointManager(checkpoint_dir=str(tmp_path / "c"), run_id="r"),
                             max_jobs=1, cv_text=cv_text)
        return runner, logger
    return build


def run_with_llm(runner, responses):
    """Run the agent with a scripted LLM. `responses` is a list of dicts or exceptions, one per call."""
    prompts = []

    def fake_chat(self, messages, **kwargs):
        prompts.append(messages[-1]["content"])
        r = responses[min(len(prompts) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return json.dumps(r)

    with patch("src.job_agent.agent_runner.search_freehire", return_value=[dict(JOB)]), \
         patch("src.job_agent.llm_client.LLMClient.chat", fake_chat):
        output = runner.run("platform")
    return output, prompts


def events(logger, event_type):
    return [json.loads(line) for line in logger.trace_file.read_text().splitlines()
            if json.loads(line)["event_type"] == event_type]


def test_clean_draft_is_accepted_without_retry(make_runner):
    runner, logger = make_runner()
    output, prompts = run_with_llm(runner, [CLEAN])
    assert len(prompts) == 1
    assert output["applications"][0].warnings == []
    assert not events(logger, "grounding_retry")


def test_invented_figures_trigger_one_regeneration_that_fixes_it(make_runner):
    runner, logger = make_runner()
    output, prompts = run_with_llm(runner, [INVENTED, CLEAN])
    assert len(prompts) == 2
    assert "REVISION REQUIRED" not in prompts[0] and "REVISION REQUIRED" in prompts[1]
    assert "25" in prompts[1] and "40" in prompts[1]  # the offending figures are named
    app = output["applications"][0]
    assert app.warnings == [] and "40%" not in " ".join(app.cv_bullets)
    assert len(events(logger, "grounding_retry")) == 1
    assert not events(logger, "grounding_flagged")
    assert output["status"] == "completed"


def test_persistent_invention_is_flagged_not_dropped(make_runner):
    runner, logger = make_runner()
    output, prompts = run_with_llm(runner, [INVENTED, INVENTED])
    assert len(prompts) == 2  # one retry only
    app = output["applications"][0]
    assert output["status"] == "completed" and not output["failed_jobs"]
    assert len(app.warnings) == 1 and "25" in app.warnings[0] and "40" in app.warnings[0]
    assert events(logger, "grounding_flagged")[0]["numbers"] == ["25", "40"]


def test_failed_regeneration_keeps_first_draft_with_warning(make_runner):
    runner, logger = make_runner()
    output, prompts = run_with_llm(runner, [INVENTED, RuntimeError("boom")])
    app = output["applications"][0]
    assert output["status"] == "completed"
    assert app.cv_bullets == INVENTED["tailored_cv_bullets"]
    assert "Regeneration failed" in app.warnings[0]


def test_no_cv_means_no_guard(make_runner):
    runner, _ = make_runner(cv_text=None)
    output, prompts = run_with_llm(runner, [INVENTED])
    assert len(prompts) == 1 and output["applications"][0].warnings == []


def test_cv_without_figures_means_no_guard(make_runner):
    runner, _ = make_runner(cv_text="A senior engineer with broad experience and no figures.")
    output, prompts = run_with_llm(runner, [INVENTED])
    assert len(prompts) == 1 and output["applications"][0].warnings == []


def test_figures_from_posting_and_research_are_allowed(make_runner):
    runner, _ = make_runner()
    research = CompanyResearch(company_name="Acme", summary="Acme was founded in 1999.", sources=[])
    resp = {"tailored_cv_bullets": ["Led 30 engineers", "Salary band 60,000", "Acme since 1999"],
            "cover_letter": "Dear Acme,\n\nBest,\nMe"}
    with patch("src.job_agent.agent_runner.search_freehire", return_value=[{**JOB, "description": "Short posting. Salary 60,000."}]), \
         patch("src.job_agent.agent_runner.research_company", return_value=research), \
         patch("src.job_agent.llm_client.LLMClient.chat", lambda self, m, **k: json.dumps(resp)):
        output = runner.run("platform")
    assert output["applications"][0].warnings == []


def test_warning_is_shown_in_the_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = Application(job_id="j1", cover_letter="Letter", cv_bullets=["b"], warnings=["Figures not found: 40"])
    from src.job_agent.models import Job
    path = generate_report({"query": "q", "jobs_found": [Job(id="j1", title="T", company="C")],
                            "applications": [app], "failed_jobs": [], "status": "completed",
                            "checkpoint_file": "cp.jsonl"})
    text = open(path).read()
    assert "Review needed" in text and "Figures not found: 40" in text


def test_old_checkpoints_without_warnings_still_load():
    app = Application(**{"job_id": "j1", "cover_letter": "x", "cv_bullets": []})
    assert app.warnings == []
