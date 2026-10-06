"""Run the golden dataset through AgentRunner and score the results.

Usage:
    python -m evals.runner                      # mock mode (no network, no cost)
    python -m evals.runner --live --limit 5     # real FreeHire + OpenAI calls
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, Iterator, List, Optional
from unittest.mock import patch

from dotenv import load_dotenv

from src.job_agent.agent_runner import AgentRunner
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager

from .dataset_schema import GoldenQuery, load_dataset
from .report import write_reports
from .result_models import QueryScore, RunResult
from .scoring import extract_numbers, score_result

FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_OUT = Path(__file__).parent / "results"
MOCK_CV = "Mock CV: Python engineer with LLM, API and AWS experience."
_FILLER = ("I have spent years building reliable software, working closely with customers, and turning "
           "ambiguous requirements into dependable systems that teams can trust and extend over time. ") * 3


def mock_llm_response(prompt: str) -> str:
    """A well-formed application that echoes the company and position found in the prompt."""
    company = re.search(r"Company: (.*)", prompt)
    position = re.search(r"Position: (.*)", prompt)
    company, position = (company.group(1) if company else "the company"), (position.group(1) if position else "the role")
    letter = (f"Dear Hiring Team at {company},\n\n"
              f"I am excited to apply for the {position} position at {company}. {_FILLER}\n\n"
              f"My recent work combined Python, APIs and cloud services. {_FILLER}\n\n"
              f"I would welcome the chance to discuss how I can contribute to {company}.\n\n"
              "Best regards,\nCandidate")
    return json.dumps({
        "tailored_cv_bullets": ["Built LLM agents in Python", "Deployed APIs on AWS", "Led customer integrations"],
        "cover_letter": letter,
    })


def _tokens(text: str) -> set:
    return {t for t in text.lower().split() if len(t) >= 3}


def make_mock_search(audit_logger: AuditLogger) -> Callable:
    jobs = json.loads((FIXTURES / "mock_jobs.json").read_text(encoding="utf-8"))

    def mock_search(query: str, limit: int = 10, audit_logger=audit_logger, **kwargs) -> list:
        audit_logger.log_attempt("search_freehire", 1, "start")
        audit_logger.log_event(event_type="search_meta", total=None, ignored_params=[])
        audit_logger.log_attempt("search_freehire", 1, "success")
        q = _tokens(query)
        hits = [j for j in jobs if q & _tokens(f"{j['title']} {j['description']}")]
        return [dict(j) for j in hits[:limit]]

    return mock_search


@contextlib.contextmanager
def _mock_environment(audit_logger: AuditLogger) -> Iterator[None]:
    def fake_chat(self, messages, **kwargs):
        self.audit_logger.log_attempt("llm_chat", 1, "start")
        self.audit_logger.log_attempt("llm_chat", 1, "success")
        return mock_llm_response(messages[-1]["content"])

    with patch.dict(os.environ, {"OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "mock-key")}), \
         patch("src.job_agent.agent_runner.search_freehire", make_mock_search(audit_logger)), \
         patch("src.job_agent.llm_client.LLMClient.chat", fake_chat):
        yield


def _read_trace(trace_file: Path) -> List[dict]:
    events: List[dict] = []
    if trace_file.exists():
        for line in trace_file.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _tools_from_trace(events: List[dict]) -> List[str]:
    """One entry per tool invocation: count 'start' events only, not their outcomes."""
    return [e["tool"] for e in events
            if e.get("event_type") == "attempt" and e.get("status") == "start" and e.get("tool")]


def _ignored_params_from_trace(events: List[dict]) -> List[str]:
    ignored: List[str] = []
    for e in events:
        if e.get("event_type") == "search_meta":
            ignored.extend(e.get("ignored_params") or [])
    return ignored


def _load_cv(query: GoldenQuery, live: bool, notes: List[str]) -> Optional[str]:
    if not query.cv_path:
        return None
    if not live:
        return MOCK_CV
    path = Path(query.cv_path)
    if not path.exists():
        notes.append(f"cv_path {query.cv_path} not found; ran query-only")
        return None
    return path.read_text(encoding="utf-8")


def run_query(query: GoldenQuery, live: bool, max_jobs: int, model: str, out_dir: Path) -> RunResult:
    mode = "live" if live else "mock"
    notes: List[str] = []
    run_dir = out_dir / "runs" / mode / query.id
    audit_logger = AuditLogger(trace_dir=str(run_dir / "traces"))
    checkpoint_manager = CheckpointManager(checkpoint_dir=str(run_dir / "checkpoints"), run_id=query.id)
    cv_text = _load_cv(query, live, notes)

    result = RunResult(query_id=query.id, query=query.query, category=query.category, mode=mode, notes=notes,
                       cv_numbers=sorted(extract_numbers(cv_text)))
    ctx = contextlib.nullcontext() if live else _mock_environment(audit_logger)
    start = time.perf_counter()
    try:
        with ctx:
            agent = AgentRunner(audit_logger=audit_logger, checkpoint_manager=checkpoint_manager,
                                model=model, max_jobs=max_jobs, cv_text=cv_text)
            output = agent.run(query.query)
        result.status = output["status"]
        result.jobs = [{**j.model_dump(), "description": (j.description or "")[:500],
                        "description_numbers": sorted(extract_numbers(j.description))}
                       for j in output["jobs_found"]]
        result.applications = [a.model_dump() for a in output["applications"]]
        result.failed_jobs = [f.model_dump() for f in output["failed_jobs"]]
    except Exception as e:  # a crash is a result, not a harness failure
        result.error = f"{type(e).__name__}: {e}"
    result.latency_s = time.perf_counter() - start
    events = _read_trace(audit_logger.trace_file)
    result.tools_called = _tools_from_trace(events)
    result.ignored_params = _ignored_params_from_trace(events)
    return result


def run_dataset(queries: List[GoldenQuery], live: bool, max_jobs: int, model: str, out_dir: Path) -> List[QueryScore]:
    scores = []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q.id}: {q.query.strip()[:50]!r}")
        scores.append(score_result(run_query(q, live, max_jobs, model, out_dir), q))
    return scores


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run the golden dataset eval harness")
    p.add_argument("--live", action="store_true", help="Use real FreeHire and OpenAI calls (costs money)")
    p.add_argument("--yes", action="store_true", help="Skip the live-mode confirmation prompt")
    p.add_argument("--limit", type=int, help="Only run the first N selected queries")
    p.add_argument("--ids", help="Comma-separated query ids to run")
    p.add_argument("--max-jobs", type=int, default=3, help="Jobs to process per query")
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory")
    args = p.parse_args(argv)
    load_dotenv(Path(__file__).parent.parent / ".env")

    queries = load_dataset().queries
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        unknown = wanted - {q.id for q in queries}
        if unknown:
            p.error(f"Unknown query ids: {sorted(unknown)}")
        queries = [q for q in queries if q.id in wanted]
    if args.limit:
        queries = queries[: args.limit]

    if args.live and not args.yes:
        calls = len(queries) * (args.max_jobs + 1)
        print(f"Live mode: {len(queries)} queries, up to {calls} API calls (OpenAI {args.model} + FreeHire).")
        if not sys.stdin.isatty() or input("Continue? [y/N] ").strip().lower() != "y":
            print("Aborted. Use --yes to skip this prompt.")
            return 1

    scores = run_dataset(queries, args.live, args.max_jobs, args.model, args.out)
    json_path, md_path = write_reports(scores, "live" if args.live else "mock", args.out)
    passed = sum(s.passed for s in scores)
    print(f"\n{passed}/{len(scores)} queries passed\nReport: {md_path}\nData:   {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
