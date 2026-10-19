"""Offline fault injection: the real AgentRunner against faulty transports. Free, no network, no CV.

Usage:
    python -m evals.stress.faults              # run all scenarios, write evals/results/stress_faults_<ts>.md/.json
    python -m evals.stress.faults --only B7a,B7b

The OpenAI transport (`client.chat.completions.create`), FreeHire (a local stub HTTP server) and DuckDuckGo
are replaced by scripted fakes that raise the REAL exception types (openai.*, requests.*, DDGSException).
Everything above the transport (retry, classification, guards, checkpoints, resume) is production code.
Backoff sleeps are stubbed and recorded, so the delays in the report are the delays REQUESTED, not measured.
All results are INDUCED faults, not organic ones.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import patch

try:
    import httpx
except ModuleNotFoundError:  # newer openai releases ship on httpx2
    import httpx2 as httpx
import openai
from ddgs.exceptions import DDGSException

from src.job_agent.agent_runner import AgentRunner
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager
from src.job_agent.tools import research_company as real_research_company

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
_REQ = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

# A CV without digits: the grounding guard has nothing to check, so only the faults are exercised.
CV = "Senior software engineer. Built data platforms in Python and led small teams in regulated industries."
_PARA = " ".join(["I", "build", "reliable", "systems", "for", "customers", "and", "enjoy", "the", "work"] * 5)
GOOD_JSON = json.dumps({
    "tailored_cv_bullets": ["Built data platforms in Python", "Led small teams", "Worked in regulated industries"],
    "cover_letter": "Dear Hiring Manager,\n\n" + "\n\n".join([_PARA] * 3) + "\n\nBest regards",
})
LONG_DESC = "x" * 700  # long enough that research is skipped (rich_description)
THIN_DESC = "Short posting."


def jobs(n: int, desc: str = LONG_DESC) -> List[dict]:
    return [{"id": f"job_{i}", "title": f"Engineer {i}", "company": f"Company {i}", "description": desc}
            for i in range(1, n + 1)]


# ── scripted fakes ──

def api_error(cls, status: int, message: str = "boom"):
    response = httpx.Response(status, request=_REQ, json={"error": {"message": message}})
    return cls(message, response=response, body=None)


def completion(content: Optional[str]):
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, prompt_tokens_details=None,
                            completion_tokens_details=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                           usage=usage, model="gpt-4o-mini")


class FakeLLM:
    """Plays a script. A step is an Exception (raised), a string/None (returned as the model's content),
    "ok" (a valid application) or a callable taking the call number. Once a script is empty, calls succeed.

    `per_job` scripts apply to calls whose prompt names that job's company ("job_3" -> "Company 3");
    `script` applies to every other call.
    """

    def __init__(self, script: Optional[List[Any]] = None, per_job: Optional[Dict[str, List[Any]]] = None):
        self.script = list(script or [])
        self.per_job = {k: list(v) for k, v in (per_job or {}).items()}
        self.calls = 0

    def create(self, model=None, messages=None, **kwargs):
        self.calls += 1
        text = " ".join(str(m.get("content", "")) for m in (messages or []))
        steps = self.script
        for job_id, job_steps in self.per_job.items():
            if f"Company: Company {job_id.split('_')[-1]}\n" in text:
                steps = job_steps
                break
        step = steps.pop(0) if steps else "ok"
        if callable(step):
            step = step(self.calls)
        if isinstance(step, BaseException):
            raise step
        return completion(GOOD_JSON if step == "ok" else step)


@dataclass
class Env:
    tmp: Path
    run_id: str
    delays: List[float] = field(default_factory=list)

    def runner(self, llm: FakeLLM, max_jobs: int = 5) -> AgentRunner:
        os.environ.setdefault("OPENAI_API_KEY", "test-key")
        audit = AuditLogger(trace_dir=str(self.tmp / "traces"))
        cp = CheckpointManager(checkpoint_dir=str(self.tmp / "checkpoints"), run_id=self.run_id)
        runner = AgentRunner(audit_logger=audit, checkpoint_manager=cp, max_jobs=max_jobs, cv_text=CV)
        runner.llm_client.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=llm.create)))
        return runner

    def sleeper(self):
        return patch("src.job_agent.retry.time", SimpleNamespace(sleep=self.delays.append))


def read_trace(runner: AgentRunner) -> List[dict]:
    path = runner.audit_logger.trace_file
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def failures_in(trace: List[dict], tool: str) -> List[dict]:
    return [e["details"]["failure_record"] for e in trace
            if e.get("event_type") == "attempt" and e.get("tool") == tool and e.get("status") == "failure"]


def attempts_of(trace: List[dict], tool: str) -> int:
    return sum(1 for e in trace if e.get("event_type") == "attempt" and e.get("tool") == tool
               and e.get("status") == "start")


def summarise(result: Optional[dict], runner: AgentRunner, env: Env, tool: str, **extra) -> Dict[str, Any]:
    trace = read_trace(runner)
    fails = failures_in(trace, tool)
    out: Dict[str, Any] = {
        "category": "/".join(sorted({f["category"] for f in fails})) or "-",
        "policy": "/".join(sorted({f["retry_policy"] for f in fails})) or "-",
        "attempts": attempts_of(trace, tool),
        "backoff_s": list(env.delays),
    }
    if result is not None:
        out["status"] = result["status"]
        out["applications"] = len(result["applications"])
        out["failed_jobs"] = [(f.job_id, f.error_category) for f in result["failed_jobs"]]
        out["warnings"] = [a.warnings for a in result["applications"] if a.warnings]
    events = [e["event_type"] for e in trace]
    seen = {name: events.count(name) for name in
            ("structure_violation", "structure_retry", "structure_flagged", "research_failed", "job_failed")
            if name in events}
    if seen:
        out["events"] = seen
    out.update(extra)
    return out


def run_pipeline(env: Env, llm: FakeLLM, tool: str = "llm_chat", n_jobs: int = 2, job_list: Optional[list] = None,
                 ) -> Dict[str, Any]:
    runner = env.runner(llm)
    with env.sleeper(), patch("src.job_agent.agent_runner.search_freehire",
                              return_value=job_list or jobs(n_jobs)):
        result = runner.run("q")
    return summarise(result, runner, env, tool, llm_calls=llm.calls)


# ── FreeHire stub server ──

class StubFreeHire:
    """Serves a queue of (status, content_type, body); the last entry repeats."""

    def __init__(self, behaviours: List[tuple]):
        outer = self
        self.behaviours = list(behaviours)
        self.requests = 0

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.requests += 1
                status, ctype, body = outer.behaviours.pop(0) if len(outer.behaviours) > 1 else outer.behaviours[0]
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *args):  # silence
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/search"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def freehire_ok(n: int = 2) -> tuple:
    return 200, "application/json", json.dumps({"data": jobs(n), "meta": {"total": n, "ignored_params": []}})


def run_freehire(env: Env, behaviours: Optional[List[tuple]], url: Optional[str] = None) -> Dict[str, Any]:
    llm = FakeLLM()
    runner = env.runner(llm)

    def go(search_url: str) -> Dict[str, Any]:
        with patch.dict(os.environ, {"FREEHIRE_SEARCH_URL": search_url}), env.sleeper():
            try:
                result = runner.run("q")
            except Exception as e:  # the run itself failed: this is the interesting case
                return summarise(None, runner, env, "search_freehire", raised=f"{type(e).__name__}: {str(e)[:80]}",
                                 checkpoint_written=runner.checkpoint_manager.checkpoint_file.exists())
        return summarise(result, runner, env, "search_freehire", llm_calls=llm.calls)

    if behaviours is None:
        return go(url or "http://127.0.0.1:9/search")  # port 9 (discard): nothing listens
    with StubFreeHire(behaviours) as stub:
        out = go(stub.url)
    out["http_requests"] = stub.requests
    return out


# ── DuckDuckGo ──

class FaultyDDGS:
    def __init__(self, error: BaseException):
        self.error = error

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def text(self, *args, **kwargs):
        raise self.error


def run_ddg(env: Env, error: BaseException) -> Dict[str, Any]:
    llm = FakeLLM()
    runner = env.runner(llm)
    # Re-bind the real research function: the test suite's conftest stubs it out for every test.
    with env.sleeper(), patch("src.job_agent.tools.DDGS", FaultyDDGS(error)), \
            patch("src.job_agent.agent_runner.research_company", real_research_company), \
            patch("src.job_agent.agent_runner.search_freehire", return_value=jobs(1, THIN_DESC)):
        result = runner.run("q")
    out = summarise(result, runner, env, "search_duckduckgo", llm_calls=llm.calls)
    out["letter_generated"] = bool(result["applications"] and result["applications"][0].cover_letter)
    return out


# ── resume ──

def run_resume_after_failure(env: Env, second_llm: FakeLLM) -> Dict[str, Any]:
    """Phase 1: job_2 fails after retries. Phase 2: resume with `second_llm`."""
    first = FakeLLM(per_job={"job_2": [api_error(openai.RateLimitError, 429)] * 3})
    runner1 = env.runner(first)
    with env.sleeper(), patch("src.job_agent.agent_runner.search_freehire", return_value=jobs(3)):
        r1 = runner1.run("q")
    env.delays.clear()
    runner2 = env.runner(second_llm)
    with env.sleeper(), patch("src.job_agent.agent_runner.search_freehire",
                              side_effect=AssertionError("resume must not search again")):
        r2 = runner2.run("q", resume=True)
    return {
        "phase1": f"{r1['status']}: {len(r1['applications'])} apps, failed {[f.job_id for f in r1['failed_jobs']]}",
        "category": "/".join(sorted({f.error_category for f in r1["failed_jobs"]})) or "-",
        "policy": "-", "attempts": None, "backoff_s": [],
        "status": r2["status"], "applications": len(r2["applications"]),
        "failed_jobs": [(f.job_id, f.error_category) for f in r2["failed_jobs"]],
        "llm_calls_on_resume": second_llm.calls,
        "duplicate_apps": len(r2["applications"]) - len({a.job_id for a in r2["applications"]}),
    }


def _kill_child(tmp: str, run_id: str) -> None:
    """Child process for the kill -9 scenario: blocks inside the third job's LLM call."""
    env = Env(Path(tmp), run_id)
    hang = lambda n: time.sleep(120) or "ok"  # noqa: E731
    runner = env.runner(FakeLLM(per_job={"job_3": [hang]}))
    with patch("src.job_agent.agent_runner.search_freehire", return_value=jobs(4)):
        runner.run("q")


def run_kill_and_resume(env: Env) -> Dict[str, Any]:
    child = subprocess.Popen([sys.executable, "-m", "evals.stress.faults", "--child-kill", str(env.tmp), env.run_id],
                             cwd=Path(__file__).resolve().parents[2], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    cp_file = env.tmp / "checkpoints" / f"checkpoint_{env.run_id}.jsonl"
    deadline = time.time() + 60
    done_before_kill = 0
    while time.time() < deadline and child.poll() is None:
        if cp_file.exists():
            lines = [json.loads(line) for line in cp_file.read_text().splitlines() if line.strip()]
            done_before_kill = len(lines[-1]["state"]["jobs_processed"]) if lines else 0
            if done_before_kill >= 2:
                break
        time.sleep(0.2)
    child.send_signal(signal.SIGKILL)
    child.wait()

    llm = FakeLLM()
    runner = env.runner(llm)
    with env.sleeper(), patch("src.job_agent.agent_runner.search_freehire",
                              side_effect=AssertionError("resume must not search again")):
        result = runner.run("q", resume=True)
    return {
        "category": "-", "policy": "-", "attempts": None, "backoff_s": [],
        "jobs_done_before_kill": done_before_kill,
        "status": result["status"], "applications": len(result["applications"]),
        "failed_jobs": [(f.job_id, f.error_category) for f in result["failed_jobs"]],
        "llm_calls_on_resume": llm.calls,
        "duplicate_apps": len(result["applications"]) - len({a.job_id for a in result["applications"]}),
        "usage_calls_after_resume": result["usage"].get("calls"),
    }


# ── scenarios ──

@dataclass
class Scenario:
    id: str
    fault: str
    expect: str
    fn: Callable[[Env], Dict[str, Any]]
    check: Callable[[Dict[str, Any]], bool]


def _transient(cls, status, tool_expect="DEAD_API"):
    return lambda o: (o["category"] == tool_expect and o["policy"] == "RETRY_SAME"
                      and o["status"] == "completed" and o["applications"] == 2 and o["backoff_s"] == [1.0])


SCENARIOS: List[Scenario] = [
    Scenario("B1", "LLM 429 (RateLimitError) on the first call, then success",
             "DEAD_API / RETRY_SAME, 1 retry after 1s, run completed (2 apps)",
             lambda e: run_pipeline(e, FakeLLM([api_error(openai.RateLimitError, 429)])),
             _transient(openai.RateLimitError, 429)),
    Scenario("B2a", "LLM 500 on the first call, then success",
             "DEAD_API / RETRY_SAME, 1 retry after 1s, completed",
             lambda e: run_pipeline(e, FakeLLM([api_error(openai.InternalServerError, 500)])),
             _transient(openai.InternalServerError, 500)),
    Scenario("B2b", "LLM 504 on the first call, then success",
             "DEAD_API / RETRY_SAME, 1 retry after 1s, completed",
             lambda e: run_pipeline(e, FakeLLM([api_error(openai.InternalServerError, 504)])),
             _transient(openai.InternalServerError, 504)),
    Scenario("B2c", "LLM connection error (APIConnectionError), then success",
             "TIMEOUT / RETRY_SAME, 1 retry after 1s, completed",
             lambda e: run_pipeline(e, FakeLLM([openai.APIConnectionError(request=_REQ)])),
             _transient(openai.APIConnectionError, None, "TIMEOUT")),
    Scenario("B2d", "LLM timeout (APITimeoutError), then success",
             "TIMEOUT / RETRY_SAME, 1 retry after 1s, completed",
             lambda e: run_pipeline(e, FakeLLM([openai.APITimeoutError(request=_REQ)])),
             _transient(openai.APITimeoutError, None, "TIMEOUT")),
    Scenario("B2e", "Model returns prose instead of JSON (no exception)",
             "Structure guard: violation, one retry, recovered; completed with 3 LLM calls",
             lambda e: run_pipeline(e, FakeLLM(["Sorry, I cannot help with that."])),
             lambda o: o["status"] == "completed" and o.get("events", {}).get("structure_retry") == 1
             and o["llm_calls"] == 3 and not o["warnings"]),
    Scenario("B2f", "Model returns content=None (e.g. a refusal)",
             "Structure guard: violation, one retry, recovered; completed (2 apps, 3 LLM calls). Before the "
             "Day 22 fix the job failed as UNKNOWN with an AttributeError in _strip_code_fences",
             lambda e: run_pipeline(e, FakeLLM([None])),
             lambda o: o["status"] == "completed" and o["applications"] == 2 and o["llm_calls"] == 3
             and o.get("events", {}).get("structure_retry") == 1 and not o["warnings"]),
    Scenario("B3a", "LLM 429 on all 3 attempts for job_1; job_2 healthy",
             "job_1 fails (DEAD_API), run partial with 1 app, backoff 1s then 2s, 4 llm_chat attempts",
             lambda e: run_pipeline(e, FakeLLM(per_job={"job_1": [api_error(openai.RateLimitError, 429)] * 3})),
             lambda o: o["status"] == "partial" and o["applications"] == 1 and o["backoff_s"] == [1.0, 2.0]
             and o["failed_jobs"] == [("job_1", "DEAD_API")] and o["attempts"] == 4),
    Scenario("B3b", "LLM 401 (AuthenticationError) on every job",
             "AUTH_ERROR / NOT_RETRYABLE: no retries, both jobs failed, run failed",
             lambda e: run_pipeline(e, FakeLLM(per_job={f"job_{i}": [api_error(openai.AuthenticationError, 401)]
                                                         for i in (1, 2)})),
             lambda o: o["status"] == "failed" and o["policy"] == "NOT_RETRYABLE" and o["backoff_s"] == []
             and o["attempts"] == 2),
    Scenario("B3c", "LLM 404 (model not found)",
             "UNKNOWN / NOT_RETRYABLE (404 is not specially handled for OpenAI errors)",
             lambda e: run_pipeline(e, FakeLLM(per_job={f"job_{i}": [api_error(openai.NotFoundError, 404)]
                                                         for i in (1, 2)})),
             lambda o: o["category"] == "UNKNOWN" and o["attempts"] == 2),
    Scenario("B3d", "LLM 400 (BadRequestError)",
             "UNKNOWN / NOT_RETRYABLE (only requests.HTTPError 400 is MALFORMED_RESPONSE)",
             lambda e: run_pipeline(e, FakeLLM(per_job={f"job_{i}": [api_error(openai.BadRequestError, 400)]
                                                         for i in (1, 2)})),
             lambda o: o["category"] == "UNKNOWN" and o["attempts"] == 2),
    Scenario("B3e", "LLM 429 insufficient_quota",
             "AUTH_ERROR / MANUAL_INTERVENTION: not retried",
             lambda e: run_pipeline(e, FakeLLM(per_job={f"job_{i}": [api_error(
                 openai.RateLimitError, 429, "insufficient_quota: You exceeded your current quota")]
                 for i in (1, 2)})),
             lambda o: o["policy"] == "MANUAL_INTERVENTION" and o["backoff_s"] == [] and o["attempts"] == 2),
    Scenario("B3f", "LLM 400 context_length_exceeded, then success",
             "CONTEXT_OVERFLOW / RETRY_MODIFIED: one retry (history halving cannot shrink a 2-message prompt)",
             lambda e: run_pipeline(e, FakeLLM([api_error(openai.BadRequestError, 400, "context_length_exceeded")])),
             lambda o: o["category"] == "CONTEXT_OVERFLOW" and o["policy"] == "RETRY_MODIFIED"
             and o["status"] == "completed"),
    Scenario("B4a", "FreeHire 429, then a valid response",
             "DEAD_API / RETRY_SAME, 1 retry after 1s, run completed",
             lambda e: run_freehire(e, [(429, "text/plain", "slow down"), freehire_ok()]),
             lambda o: o["category"] == "DEAD_API" and o["status"] == "completed" and o["backoff_s"] == [1.0]),
    Scenario("B4b", "FreeHire 500 on every attempt",
             "3 attempts (1s, 2s), then run() raises; no checkpoint exists to resume from",
             lambda e: run_freehire(e, [(500, "text/plain", "oops")]),
             lambda o: o["attempts"] == 3 and "raised" in o and o["backoff_s"] == [1.0, 2.0]),
    Scenario("B4c", "FreeHire 200 with an HTML body",
             "MALFORMED_RESPONSE / RETRY_SAME, 3 attempts, then run() raises",
             lambda e: run_freehire(e, [(200, "text/html", "<html>gateway error</html>")]),
             lambda o: o["category"] == "MALFORMED_RESPONSE" and o["attempts"] == 3 and "raised" in o),
    Scenario("B4d", "FreeHire unreachable (connection refused)",
             "DEAD_API / RETRY_SAME, 3 attempts, then run() raises",
             lambda e: run_freehire(e, None),
             lambda o: o["category"] in ("DEAD_API", "TIMEOUT") and o["attempts"] == 3 and "raised" in o),
    Scenario("B4e", "FreeHire 401",
             "AUTH_ERROR / NOT_RETRYABLE, 1 attempt, run() raises",
             lambda e: run_freehire(e, [(401, "text/plain", "no")]),
             lambda o: o["category"] == "AUTH_ERROR" and o["attempts"] == 1 and "raised" in o),
    Scenario("B4f", "FreeHire reports the query param as ignored",
             "FreeHireIgnoredParamError; classified UNKNOWN / NOT_RETRYABLE; run() raises",
             lambda e: run_freehire(e, [(200, "application/json", json.dumps(
                 {"data": jobs(2), "meta": {"ignored_params": [{"param": "q"}]}}))]),
             lambda o: o["attempts"] == 1 and "FreeHireIgnoredParamError" in o.get("raised", "")),
    Scenario("B4g", "FreeHire returns zero results",
             "Not a failure: run completes with 0 jobs",
             lambda e: run_freehire(e, [(200, "application/json", json.dumps({"data": [], "meta": {}}))]),
             lambda o: o.get("status") == "completed" and o["applications"] == 0),
    Scenario("B5a", "DuckDuckGo raises DDGSException on a thin posting",
             "Research fails (UNKNOWN, not retried), research_failed logged, letter still generated",
             lambda e: run_ddg(e, DDGSException("boom")),
             lambda o: o["status"] == "completed" and o["letter_generated"]
             and o.get("events", {}).get("research_failed") == 1),
    Scenario("B5b", "DuckDuckGo times out on every attempt",
             "TIMEOUT / RETRY_SAME, 3 attempts, research_failed, letter still generated",
             lambda e: run_ddg(e, TimeoutError("ddg timed out")),
             lambda o: o["status"] == "completed" and o["letter_generated"] and o["attempts"] == 3
             and o.get("events", {}).get("research_failed") == 1),
    Scenario("B6", "Process killed with SIGKILL inside job 3 of 4, then --resume",
             "Jobs 1-2 kept, resume does not search again, jobs 3-4 generated, no duplicates, usage covers only "
             "the resumed part",
             run_kill_and_resume,
             lambda o: o["jobs_done_before_kill"] == 2 and o["status"] == "completed" and o["applications"] == 4
             and o["duplicate_apps"] == 0 and o["llm_calls_on_resume"] == 2),
    Scenario("B7a", "job_2 failed (429 x3); resume with a healthy LLM",
             "DESIRED: the failed job is retried on resume (1 LLM call), run completed with 3 apps, 0 failed jobs",
             lambda e: run_resume_after_failure(e, FakeLLM()),
             lambda o: o["llm_calls_on_resume"] == 1 and o["status"] == "completed" and o["applications"] == 3
             and o["failed_jobs"] == []),
    Scenario("B7b", "job_2 failed; on resume it fails again",
             "DESIRED: retried once, still failed, exactly one failure record (no duplicates), run partial",
             lambda e: run_resume_after_failure(
                 e, FakeLLM(per_job={"job_2": [api_error(openai.RateLimitError, 429)] * 3})),
             lambda o: o["llm_calls_on_resume"] == 3 and o["status"] == "partial" and o["applications"] == 2
             and o["failed_jobs"] == [("job_2", "DEAD_API")]),
]


def run_all(only: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    rows = []
    for sc in SCENARIOS:
        if only and sc.id not in only:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            env = Env(Path(tmp), f"stress_{sc.id}")
            try:
                observed = sc.fn(env)
                matched = bool(sc.check(observed))
            except Exception as e:  # a harness or product crash is a finding too
                observed, matched = {"harness_error": f"{type(e).__name__}: {e}"}, False
        rows.append({"id": sc.id, "fault": sc.fault, "expect": sc.expect, "observed": observed, "matches": matched})
    return rows


def render_markdown(rows: List[Dict[str, Any]], stamp: str) -> str:
    lines = [f"# Induced-fault results (offline)\n\nGenerated: {stamp}. All faults are INDUCED (scripted transports, real "
             "exception types, production retry/guard/checkpoint code). Backoff values are delays requested; sleeps "
             "were stubbed.\n",
             f"**{sum(r['matches'] for r in rows)}/{len(rows)} matched expectation.**\n",
             "| ID | Fault | Expected | Observed | Match |", "|---|---|---|---|---|"]
    for r in rows:
        obs = "; ".join(f"{k}={v}" for k, v in r["observed"].items() if v not in (None, [], {}, "-"))
        lines.append(f"| {r['id']} | {r['fault']} | {r['expect']} | {obs} | {'yes' if r['matches'] else '**NO**'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated scenario ids")
    parser.add_argument("--child-kill", nargs=2, metavar=("TMP", "RUN_ID"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child_kill:
        _kill_child(*args.child_kill)
        return
    rows = run_all(args.only.split(",") if args.only else None)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"stress_faults_{stamp}.json").write_text(json.dumps(rows, indent=2, default=str))
    md = render_markdown(rows, stamp)
    (RESULTS_DIR / f"stress_faults_{stamp}.md").write_text(md)
    print(md)
    print(f"Wrote evals/results/stress_faults_{stamp}.md")


if __name__ == "__main__":
    main()
