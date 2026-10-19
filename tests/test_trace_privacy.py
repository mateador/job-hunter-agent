"""The audit trail must not contain prompts: they carry the candidate's CV."""
from unittest.mock import patch

import openai

from evals.stress import faults
from src.job_agent.audit_logger import MAX_LOGGED_CHARS, redact_for_log

MARKER = "ZEBRA-CV-MARKER " + "led a payments migration " * 20
POSTING_MARKER = "QUOKKA-POSTING-MARKER"


def test_long_strings_and_chat_messages_are_fingerprinted():
    out = redact_for_log({
        "messages": [{"role": "system", "content": "short"}, {"role": "user", "content": "x" * 5000}],
        "query": "python engineer london", "limit": 5, "flag": True, "nested": {"text": "y" * 500},
    })
    assert out["query"] == "python engineer london" and out["limit"] == 5 and out["flag"] is True
    assert out["messages"][0] == {"role": "system", "content": {"chars": 5, "sha256": out["messages"][0]["content"]["sha256"]}}
    assert out["messages"][1]["content"]["chars"] == 5000
    assert len(out["messages"][1]["content"]["sha256"]) == 12
    assert out["nested"]["text"]["chars"] == 500
    assert "x" * 50 not in str(out) and "y" * 50 not in str(out)


def test_equal_text_gets_equal_fingerprints_and_different_text_does_not():
    a, b, c = (redact_for_log("p" * 300), redact_for_log("p" * 300), redact_for_log("q" * 300))
    assert a == b and a != c


def test_short_values_are_kept_exactly():
    assert redact_for_log("a" * MAX_LOGGED_CHARS) == "a" * MAX_LOGGED_CHARS


def _trace_text(tmp_path_env, llm, jobs_list=None):
    runner = tmp_path_env.runner(llm)
    runner.cv_text = MARKER
    listing = jobs_list or faults.jobs(2)
    for j in listing:
        j["description"] = POSTING_MARKER + " " + j["description"]
    with tmp_path_env.sleeper(), patch("src.job_agent.agent_runner.search_freehire", return_value=listing):
        runner.run("q")
    return runner.audit_logger.trace_file.read_text()


def test_trace_of_a_normal_run_contains_neither_the_cv_nor_the_posting_text(tmp_path):
    text = _trace_text(faults.Env(tmp_path, "p1"), faults.FakeLLM())
    assert "ZEBRA-CV-MARKER" not in text and "payments migration" not in text
    assert POSTING_MARKER not in text
    assert '"event_type": "attempt"' in text  # the attempts are still logged


def test_trace_after_retries_and_modified_kwargs_stays_clean(tmp_path):
    llm = faults.FakeLLM([faults.api_error(openai.RateLimitError, 429),
                          faults.api_error(openai.BadRequestError, 400, "context_length_exceeded")])
    text = _trace_text(faults.Env(tmp_path, "p2"), llm)
    assert '"status": "modified"' in text
    assert "ZEBRA-CV-MARKER" not in text and POSTING_MARKER not in text
