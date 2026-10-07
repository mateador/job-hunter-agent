import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.job_agent.agent_runner import AgentRunner
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager
from src.job_agent.llm_client import LLMClient
from src.job_agent.pricing import estimate_cost, load_pricing, normalise_model, price_for
from src.job_agent.report_generator import generate_report
from src.job_agent.routing import ModelRouter
from src.job_agent.usage import LLMUsage, UsageTracker

PRICES = {"models": {"m-cheap": {"input": 1.0, "cached_input": 0.5, "output": 2.0},
                     "m-strong": {"input": 10.0, "cached_input": 5.0, "output": 20.0}},
          "as_of": "2026-01-01", "source_url": "https://example.test", "verified": True}


@pytest.fixture(autouse=True)
def fake_prices():
    with patch("src.job_agent.pricing.load_pricing", return_value=PRICES):
        yield


# ── pricing ──

def test_cost_formula_with_and_without_cache():
    assert estimate_cost("m-cheap", 1000, 500) == pytest.approx((1000 * 1.0 + 500 * 2.0) / 1e6)
    assert estimate_cost("m-cheap", 1000, 500, cached_tokens=400) == pytest.approx(
        (600 * 1.0 + 400 * 0.5 + 500 * 2.0) / 1e6)


def test_cached_tokens_are_clamped_to_prompt_size():
    assert estimate_cost("m-cheap", 100, 0, cached_tokens=999) == pytest.approx(100 * 0.5 / 1e6)


def test_dated_snapshot_ids_resolve_to_the_base_model():
    assert normalise_model("m-cheap-2024-07-18") == "m-cheap"
    assert price_for("m-cheap-2024-07-18") == PRICES["models"]["m-cheap"]


def test_unknown_model_is_unpriced_not_guessed():
    assert price_for("mystery") is None
    assert estimate_cost("mystery", 1000, 1000) is None
    assert estimate_cost(None, 1, 1) is None


def test_shipped_price_table_is_well_formed():
    load_pricing.__wrapped__  # the cached loader exists
    with patch("src.job_agent.pricing.load_pricing", load_pricing.__wrapped__):
        table = load_pricing.__wrapped__()
    assert isinstance(table["verified"], bool) and table["as_of"] and table["source_url"].startswith("https://")
    assert "gpt-4o-mini" in table["models"]  # the project default must be priced
    for name, p in table["models"].items():
        assert set(p) == {"input", "cached_input", "output"}, name
        assert all(v > 0 for v in p.values()), name
        assert p["cached_input"] <= p["input"], name


# ── tracker ──

def test_summary_by_purpose_and_model_and_unpriced():
    t = UsageTracker()
    t.record(LLMUsage(model="m-cheap", purpose="application", prompt_tokens=1000, completion_tokens=500))
    t.record(LLMUsage(model="m-strong", purpose="grounding_retry", prompt_tokens=1000, completion_tokens=500))
    t.record(LLMUsage(model="mystery", purpose="application", prompt_tokens=10, completion_tokens=10))
    s = t.summary()
    assert s["calls"] == 3 and s["total_tokens"] == 3020
    assert s["unpriced_calls"] == 1
    assert s["cost_usd"] == pytest.approx(0.002 + 0.02)  # the unpriced call adds nothing
    assert s["by_purpose"]["application"]["calls"] == 2 and s["by_purpose"]["grounding_retry"]["calls"] == 1
    assert s["by_model"]["m-strong"]["cost_usd"] == pytest.approx(0.02)
    assert s["synthetic"] is False


def test_empty_tracker_summary():
    s = UsageTracker().summary()
    assert s["calls"] == 0 and s["cost_usd"] == 0 and s["by_purpose"] == {}


# ── router ──

def test_router_uses_retry_model_only_for_retries():
    r = ModelRouter("m-cheap", "m-strong")
    assert r.model_for("application") == "m-cheap" and r.model_for(None) == "m-cheap"
    assert r.model_for("grounding_retry") == "m-strong"
    assert ModelRouter("m-cheap").model_for("grounding_retry") == "m-cheap"


# ── client ──

def response(content="hi", prompt=1000, completion=500, cached=0, model="m-cheap-2024-07-18", usage=True):
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                              prompt_tokens_details=SimpleNamespace(cached_tokens=cached)) if usage else None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("src.job_agent.llm_client.OpenAI") as openai_cls:
        c = LLMClient(AuditLogger(trace_dir=str(tmp_path)), model="m-cheap",
                      router=ModelRouter("m-cheap", "m-strong"))
        c.create = openai_cls.return_value.chat.completions.create
        yield c


def trace(client, event_type):
    return [e for e in map(json.loads, client.audit_logger.trace_file.read_text().splitlines())
            if e["event_type"] == event_type]


def test_chat_records_usage_and_logs_event(client):
    client.create.return_value = response(cached=400)
    with client.tagged(job_id="j1", purpose="application"):
        assert client.chat([{"role": "user", "content": "x"}]) == "hi"
    rec = client.usage.records[0]
    assert (rec.model, rec.purpose, rec.job_id) == ("m-cheap-2024-07-18", "application", "j1")
    assert (rec.prompt_tokens, rec.completion_tokens, rec.cached_tokens) == (1000, 500, 400)
    assert rec.cost_usd == pytest.approx((600 * 1.0 + 400 * 0.5 + 500 * 2.0) / 1e6)
    event = trace(client, "llm_usage")[0]
    assert event["prompt_tokens"] == 1000 and event["purpose"] == "application"


def test_missing_usage_is_tolerated(client):
    client.create.return_value = response(usage=False)
    assert client.chat([{"role": "user", "content": "x"}]) == "hi"
    assert client.usage.records == []


def test_router_picks_the_model_sent_to_the_api(client):
    client.create.return_value = response()
    with client.tagged(purpose="application"):
        client.chat([{"role": "user", "content": "x"}])
    with client.tagged(purpose="grounding_retry"):
        client.chat([{"role": "user", "content": "x"}])
    client.chat([{"role": "user", "content": "x"}])
    assert [c.kwargs["model"] for c in client.create.call_args_list] == ["m-cheap", "m-strong", "m-cheap"]


def test_tags_nest_and_restore(client):
    with client.tagged(job_id="a", purpose="application"):
        with client.tagged(purpose="grounding_retry"):
            assert client._tags == {"job_id": "a", "purpose": "grounding_retry"}
        assert client._tags == {"job_id": "a", "purpose": "application"}
    assert client._tags == {}


# ── runner end to end ──

CV = "Led 30 engineers. Eighteen years of delivery."
JOB = {"id": "j1", "title": "Platform Engineer", "company": "Acme", "description": "Build platforms. " * 60}
CLEAN = {"tailored_cv_bullets": ["Led 30 engineers", "b", "c"], "cover_letter": "Dear Acme,\n\nI led 30 engineers.\n\nBest"}
INVENTED = {"tailored_cv_bullets": ["Cut costs by 40%", "b", "c"], "cover_letter": "Dear Acme,\n\nCut costs by 40%.\n\nBest"}


def test_runner_reports_usage_and_routes_retries_to_retry_model(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    replies = iter([INVENTED, CLEAN])
    with patch("src.job_agent.llm_client.OpenAI") as openai_cls, \
         patch("src.job_agent.agent_runner.search_freehire", return_value=[dict(JOB)]):
        create = openai_cls.return_value.chat.completions.create
        create.side_effect = lambda **kw: response(content=json.dumps(next(replies)), model=kw["model"])
        runner = AgentRunner(AuditLogger(trace_dir=str(tmp_path / "t")),
                             CheckpointManager(checkpoint_dir=str(tmp_path / "c"), run_id="r"),
                             model="m-cheap", retry_model="m-strong", max_jobs=1, cv_text=CV)
        output = runner.run("platform")
    assert [c.kwargs["model"] for c in create.call_args_list] == ["m-cheap", "m-strong"]
    usage = output["usage"]
    assert usage["calls"] == 2 and set(usage["by_purpose"]) == {"application", "grounding_retry"}
    assert set(usage["by_model"]) == {"m-cheap", "m-strong"}
    assert usage["cost_usd"] == pytest.approx(0.002 + 0.02)
    assert output["applications"][0].warnings == []


def test_report_includes_usage_line(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = generate_report({"query": "q", "jobs_found": [], "applications": [], "failed_jobs": [],
                            "status": "completed", "checkpoint_file": "cp",
                            "usage": {"calls": 2, "total_tokens": 3000, "cost_usd": 0.0123, "unpriced_calls": 0}})
    text = open(path).read()
    assert "2 calls, 3,000 tokens" in text and "$0.0123" in text and "not billing" in text
