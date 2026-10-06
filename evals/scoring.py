"""Deterministic scoring checks. Each check is a pure function of (result, query)."""
from __future__ import annotations

from typing import Callable, List

from .dataset_schema import GoldenQuery
from .result_models import CheckResult, QueryScore, RunResult

RELEVANCE_THRESHOLD = 0.5
COMPLETED_STATUSES = {"completed", "partial"}


def check_status(result: RunResult, query: GoldenQuery) -> CheckResult:
    if query.expect_failure:
        failed = result.error is not None or result.status == "failed" or not result.jobs
        return CheckResult(
            name="status", passed=failed,
            detail="failed gracefully as expected" if failed
            else f"expected failure but status={result.status} with {len(result.jobs)} jobs",
        )
    ok = result.error is None and result.status in COMPLETED_STATUSES
    return CheckResult(
        name="status", passed=ok,
        detail=f"status={result.status}" if result.error is None else f"raised: {result.error}",
    )


def check_min_jobs(result: RunResult, query: GoldenQuery) -> CheckResult:
    if query.expect_failure:
        return CheckResult(name="min_jobs", passed=True, skipped=True, detail="expect_failure")
    n = len(result.jobs)
    return CheckResult(name="min_jobs", passed=n >= query.min_jobs,
                       detail=f"{n} jobs found, need >= {query.min_jobs}")


def check_format(result: RunResult, query: GoldenQuery) -> CheckResult:
    if not result.applications and not result.failed_jobs:
        return CheckResult(name="format", passed=True, skipped=True, detail="no outputs to check")
    problems: List[str] = []
    for app in result.applications:
        if not str(app.get("cover_letter", "")).strip():
            problems.append(f"{app.get('job_id')}: empty cover letter")
        if not app.get("cv_bullets"):
            problems.append(f"{app.get('job_id')}: no CV bullets")
    for fj in result.failed_jobs:
        if not fj.get("error_category"):
            problems.append(f"{fj.get('job_id')}: failure without category")
    return CheckResult(name="format", passed=not problems,
                       detail="; ".join(problems) or f"{len(result.applications)} applications well-formed")


def check_relevance(result: RunResult, query: GoldenQuery) -> CheckResult:
    if not query.relevance_keywords or not result.jobs:
        return CheckResult(name="relevance", passed=True, skipped=True,
                           detail="no keywords or no jobs")
    # Title only: a keyword buried in a description is too easy to match by accident.
    keywords = [k.lower() for k in query.relevance_keywords]
    matched = sum(any(k in (job.get("title") or "").lower() for k in keywords) for job in result.jobs)
    score = matched / len(result.jobs)
    return CheckResult(name="relevance", passed=score >= RELEVANCE_THRESHOLD, score=score,
                       detail=f"{matched}/{len(result.jobs)} job titles match keywords (threshold {RELEVANCE_THRESHOLD:.0%})")


def check_search_honored(result: RunResult, query: GoldenQuery) -> CheckResult:
    """FreeHire reports parameters it ignored; an ignored query means unfiltered results."""
    bad = sorted({p for p in result.ignored_params if p in {"q", "query"}})
    return CheckResult(name="search_honored", passed=not bad,
                       detail=f"query param ignored by FreeHire: {bad}" if bad
                       else f"ignored params: {sorted(set(result.ignored_params)) or 'none'}")


def check_tools(result: RunResult, query: GoldenQuery) -> CheckResult:
    """Informational until tool selection is evaluated (Day 18)."""
    names = {"freehire": "search_freehire", "duckduckgo": "search_duckduckgo"}
    expected = [names[t] for t in query.expected_tools]
    missing = [t for t in expected if t not in result.tools_called]
    return CheckResult(name="tools", passed=not missing, informational=True,
                       detail=f"expected={expected} called={sorted(set(result.tools_called))}")


CHECKS: List[Callable[[RunResult, GoldenQuery], CheckResult]] = [
    check_status, check_min_jobs, check_format, check_relevance, check_search_honored, check_tools,
]


def score_result(result: RunResult, query: GoldenQuery) -> QueryScore:
    return QueryScore(result=result, checks=[c(result, query) for c in CHECKS])
