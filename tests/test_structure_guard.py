import json
from unittest.mock import MagicMock

from src.job_agent import format_rules as fr
from src.job_agent.application_generator import generate_application
from src.job_agent.models import Job
from tests.test_grounding_guard import CLEAN, INVENTED, events, make_runner, run_with_llm  # noqa: F401

NO_BULLETS = {"cover_letter": "Dear Acme,\n\nI led 30 engineers.\n\nBest,\nMe"}
EMPTY_BULLETS = {"tailored_cv_bullets": [], "cover_letter": "Dear Acme,\n\nI led 30 engineers.\n\nBest,\nMe"}


# ── shared limits ──

def test_prompt_targets_sit_inside_the_hard_limits():
    assert fr.MIN_WORDS < fr.PROMPT_MIN_WORDS < fr.PROMPT_MAX_WORDS < fr.MAX_WORDS
    assert fr.PROMPT_BULLET_CHARS < fr.MAX_BULLET_CHARS


def test_prompt_states_the_limits_the_eval_enforces():
    llm = MagicMock()
    llm.chat.return_value = json.dumps(CLEAN)
    generate_application(Job(id="j", title="Engineer", company="Acme", description="x"), llm, MagicMock())
    prompt = llm.chat.call_args[0][0][-1]["content"]
    assert f"{fr.PROMPT_MIN_WORDS}-{fr.PROMPT_MAX_WORDS} words" in prompt
    assert f"at most {fr.PROMPT_BULLET_CHARS} characters" in prompt
    assert f"{fr.MIN_BULLETS}-{fr.MAX_BULLETS} bullet points" in prompt
    # "concise" contradicted a 220-word floor and the model undershot (Day 21 run: mean 173 words).
    assert "concise" not in prompt.lower()


def test_eval_uses_the_shared_limits():
    from evals import scoring
    assert (scoring.MAX_BULLET_CHARS, scoring.MIN_WORDS, scoring.MAX_WORDS) == (fr.MAX_BULLET_CHARS, fr.MIN_WORDS, fr.MAX_WORDS)


# ── defects ──

def test_defects_detected():
    ok = ["a", "b", "c"]
    assert fr.application_defects(ok, "Dear Acme,\n\nHello.") == []
    assert fr.application_defects([], "letter") == ["no CV bullets"]
    assert fr.application_defects(["", "  "], "letter") == ["no CV bullets"]
    assert fr.application_defects(None, "letter") == ["no CV bullets"]
    assert "empty cover letter" in fr.application_defects(ok, "  ")
    assert "cover letter is raw JSON or a code fence" in fr.application_defects(ok, '{"cover_letter": "x"}')
    assert "cover letter is raw JSON or a code fence" in fr.application_defects(ok, "```json\n{}")
    assert "cover letter is a failure placeholder" in fr.application_defects(ok, "Cover letter generation failed.")


def test_long_but_complete_application_is_not_a_defect():
    assert fr.application_defects(["x" * 500] * 5, "word " * 900) == []


# ── runtime guard ──

def test_missing_bullets_trigger_one_regeneration(make_runner):
    runner, logger = make_runner()
    output, prompts = run_with_llm(runner, [NO_BULLETS, CLEAN])
    assert len(prompts) == 2 and "REVISION REQUIRED" in prompts[1] and "no CV bullets" in prompts[1]
    app = output["applications"][0]
    assert len(app.cv_bullets) == 3 and app.warnings == []
    assert len(events(logger, "structure_retry")) == 1 and not events(logger, "structure_flagged")


def test_persistent_missing_bullets_are_flagged_not_dropped(make_runner):
    runner, logger = make_runner()
    output, prompts = run_with_llm(runner, [EMPTY_BULLETS, EMPTY_BULLETS])
    assert len(prompts) == 2  # exactly one retry
    app = output["applications"][0]
    assert output["status"] == "completed" and app.cover_letter
    assert any("No CV bullets" in w for w in app.warnings)
    assert len(events(logger, "structure_flagged")) == 1


def test_structure_retry_failure_keeps_the_first_draft_with_a_warning(make_runner):
    runner, logger = make_runner()
    output, _ = run_with_llm(runner, [NO_BULLETS, RuntimeError("boom")])
    app = output["applications"][0]
    assert output["status"] == "completed" and any("Regeneration failed" in w for w in app.warnings)


def test_unparseable_json_falls_back_to_raw_text_and_is_regenerated(make_runner):
    runner, logger = make_runner()
    calls = []

    def run():
        from unittest.mock import patch
        def fake_chat(self, messages, **kwargs):
            calls.append(1)
            return "not json at all {" if len(calls) == 1 else json.dumps(CLEAN)
        with patch("src.job_agent.agent_runner.search_freehire", return_value=[{"id": "j1", "title": "Platform Engineer", "company": "Acme", "description": "x" * 700}]), \
             patch("src.job_agent.llm_client.LLMClient.chat", fake_chat):
            return runner.run("platform")
    output = run()
    assert len(calls) == 2 and output["applications"][0].cv_bullets and output["applications"][0].warnings == []


def test_structure_and_grounding_guards_compose_with_at_most_three_calls(make_runner):
    runner, logger = make_runner()
    output, prompts = run_with_llm(runner, [NO_BULLETS, INVENTED, CLEAN])
    assert len(prompts) == 3
    app = output["applications"][0]
    assert app.warnings == [] and len(app.cv_bullets) == 3


def test_grounding_retry_that_loses_its_bullets_is_flagged(make_runner):
    runner, _ = make_runner()
    output, prompts = run_with_llm(runner, [INVENTED, EMPTY_BULLETS])
    assert len(prompts) == 2  # no third call: only a warning
    assert any("No CV bullets" in w for w in output["applications"][0].warnings)


def test_clean_draft_uses_one_call(make_runner):
    runner, logger = make_runner()
    _, prompts = run_with_llm(runner, [CLEAN])
    assert len(prompts) == 1 and not events(logger, "structure_retry")
