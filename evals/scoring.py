"""Deterministic scoring checks. Each check is a pure function of (result, query)."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Set

from src.job_agent.grounding import extract_numbers  # noqa: F401  (re-exported for the harness)
from src.job_agent.research_policy import normalise_company

from .dataset_schema import GoldenQuery
from .result_models import CheckResult, QueryScore, RunResult

RELEVANCE_THRESHOLD = 0.5
COMPLETED_STATUSES = {"completed", "partial"}

# Format thresholds (the generation prompt asks for 3-4 bullets and 3-4 letter paragraphs).
MIN_BULLETS, MAX_BULLETS, MAX_BULLET_CHARS = 3, 4, 300
MIN_BODY_PARAS, MAX_BODY_PARAS = 3, 5  # one more than the prompt asks, to allow a short closing
MIN_WORDS, MAX_WORDS = 150, 350

_GREETING = re.compile(r"^\s*(dear|hello|hi|to whom)\b", re.I)
_PLACEHOLDER = re.compile(r"\[(your|company|hiring|name|position|job|insert|candidate)[^\]]*\]|\bbullet \d\b", re.I)
_TITLE_STOPWORDS = {"and", "the", "for", "with", "ltd", "plc"}

# ── helpers ──

def _job_for(result: RunResult, job_id: Any) -> Dict[str, Any]:
    return next((j for j in result.jobs if j.get("id") == job_id), {})


def _per_application(name: str, result: RunResult,
                     problems_for: Callable[[Dict[str, Any], Dict[str, Any]], List[str]],
                     ok_detail: str) -> CheckResult:
    """Run problems_for(app, job) on every application; pass only if all are clean."""
    if not result.applications:
        return CheckResult(name=name, passed=True, skipped=True, detail="no applications")
    bad: List[str] = []
    clean = 0
    for app in result.applications:
        problems = problems_for(app, _job_for(result, app.get("job_id")))
        if problems:
            bad.append(f"{str(app.get('job_id'))[:30]}: " + ", ".join(problems))
        else:
            clean += 1
    return CheckResult(name=name, passed=not bad, score=clean / len(result.applications),
                       detail="; ".join(bad[:3]) + (f" (+{len(bad) - 3} more)" if len(bad) > 3 else "")
                       if bad else ok_detail.format(n=len(result.applications)))


def _body_paragraphs(letter: str) -> List[str]:
    """Letter paragraphs without the greeting and the short sign-off lines."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", letter) if p.strip()]
    if paras and _GREETING.match(paras[0]) and len(paras[0].split()) <= 12:
        paras = paras[1:]
    while paras and len(paras[-1].split()) <= 8:
        paras = paras[:-1]
    return paras


# ── run-level checks ──

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


# ── format ──

def _format_problems(app: Dict[str, Any], job: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    bullets = app.get("cv_bullets") or []
    letter = str(app.get("cover_letter") or "")
    if not MIN_BULLETS <= len(bullets) <= MAX_BULLETS:
        problems.append(f"{len(bullets)} bullets (want {MIN_BULLETS}-{MAX_BULLETS})")
    if any(not str(b).strip() for b in bullets):
        problems.append("empty bullet")
    if any(len(str(b)) > MAX_BULLET_CHARS for b in bullets):
        problems.append(f"bullet over {MAX_BULLET_CHARS} chars")
    if not letter.strip():
        problems.append("empty cover letter")
        return problems
    if letter.lstrip().startswith(("{", "```")):
        problems.append("letter looks like raw JSON/code fence")
    if "generation failed" in letter.lower():
        problems.append("fallback placeholder letter")
    if _PLACEHOLDER.search(letter) or any(_PLACEHOLDER.search(str(b)) for b in bullets):
        problems.append("unfilled placeholder")
    words = len(letter.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"{words} words (want {MIN_WORDS}-{MAX_WORDS})")
    paras = len(_body_paragraphs(letter))
    if not MIN_BODY_PARAS <= paras <= MAX_BODY_PARAS:
        problems.append(f"{paras} body paragraphs (want {MIN_BODY_PARAS}-{MAX_BODY_PARAS})")
    return problems


def check_format(result: RunResult, query: GoldenQuery) -> CheckResult:
    uncategorised = [str(fj.get("job_id")) for fj in result.failed_jobs if not fj.get("error_category")]
    res = _per_application("format", result, _format_problems, "{n} applications well-formed")
    if uncategorised:
        detail = f"failures without category: {uncategorised}"
        return CheckResult(name="format", passed=False, skipped=False, score=res.score,
                           detail=f"{res.detail}; {detail}" if not res.skipped else detail)
    return res


# ── correctness ──

def _significant_words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in _TITLE_STOPWORDS]


def _addressing_problems(app: Dict[str, Any], job: Dict[str, Any]) -> List[str]:
    letter = str(app.get("cover_letter") or "").lower()
    problems: List[str] = []
    company = re.split(r"[(\-–—|]", job.get("company") or "")[0]
    first = next((w for w in re.findall(r"[a-z0-9]+", company.lower())
                  if w not in {"the", "a", "an"} and not w.isdigit()), None)
    # The prompt tells the model to address agency letters to the consultant, so that also counts.
    greeting = letter.strip().split("\n", 1)[0]
    to_consultant = bool(re.search(r"\b(consultant|recruiter|recruitment)\b", greeting))
    if first and first not in letter and not to_consultant:
        problems.append(f"company '{first}' not mentioned")
    title = job.get("title") or ""
    # Titles often carry prefixes/suffixes ("UK Remote Job – DevOps Engineer"), so any segment may match.
    segments = [_significant_words(s) for s in re.split(r"[(\-–—|:,/)]", title)] + [_significant_words(title)]
    segments = [s for s in segments if s]
    if segments and not any(sum(w in letter for w in s) >= max(1, (len(s) + 1) // 2) for s in segments):
        problems.append("job title not referenced")
    return problems


def check_addressing(result: RunResult, query: GoldenQuery) -> CheckResult:
    return _per_application("addressing", result, _addressing_problems,
                            "{n} letters name the company and role")


def check_grounding(result: RunResult, query: GoldenQuery) -> CheckResult:
    """Numbers in the output must come from the CV or the job posting, else they may be invented."""
    if not result.cv_numbers:
        return CheckResult(name="grounding", passed=True, skipped=True, detail="no CV numbers to ground against")
    cv_numbers = set(result.cv_numbers)
    research_numbers = {d.get("job_id"): set(d.get("numbers") or []) for d in result.research}

    def problems_for(app: Dict[str, Any], job: Dict[str, Any]) -> List[str]:
        allowed = cv_numbers | set(job.get("description_numbers") or []) \
            | extract_numbers(job.get("title")) | extract_numbers(job.get("description")) \
            | research_numbers.get(app.get("job_id"), set())
        text = " ".join([str(app.get("cover_letter") or "")] + [str(b) for b in app.get("cv_bullets") or []])
        invented = sorted(extract_numbers(text) - allowed, key=lambda n: (len(n), n))
        return [f"numbers not in CV or posting: {invented}"] if invented else []

    return _per_application("grounding", result, problems_for,
                            "{n} applications use only numbers from the CV, posting or research")


# ── tools ──

def check_tools(result: RunResult, query: GoldenQuery) -> CheckResult:
    """Every tool the dataset expects for the query must have been called.

    DuckDuckGo is deliberately not listed per query: whether to research is decided per job
    (see check_tool_selection and the tool-selection scenarios).
    """
    names = {"freehire": "search_freehire", "duckduckgo": "search_duckduckgo"}
    expected = [names[t] for t in query.expected_tools]
    missing = [t for t in expected if t not in result.tools_called]
    return CheckResult(name="tools", passed=not missing,
                       detail=f"expected={expected} called={sorted(set(result.tools_called))}")


def check_tool_selection(result: RunResult, query: GoldenQuery) -> CheckResult:
    """DuckDuckGo is called when, and only when, the escalation policy decided to research."""
    wanted = sum(1 for d in result.research if d.get("decision"))
    calls = result.tools_called.count("search_duckduckgo")
    if result.error:
        return CheckResult(name="tool_selection", passed=True, skipped=True, detail="run raised")
    if not result.research and not calls:
        return CheckResult(name="tool_selection", passed=True, skipped=True, detail="no jobs to decide on")
    reasons = ", ".join(f"{k}={v}" for k, v in sorted(_count(d["reason"] for d in result.research).items()))
    if calls < wanted:  # retries may add calls, never remove them
        return CheckResult(name="tool_selection", passed=False,
                           detail=f"policy asked for {wanted} lookups but DuckDuckGo started {calls} times ({reasons})")
    if calls and not wanted:
        return CheckResult(name="tool_selection", passed=False,
                           detail=f"DuckDuckGo called {calls} times without a research decision ({reasons})")
    return CheckResult(name="tool_selection", passed=True,
                       detail=f"{wanted} lookups wanted, {calls} calls ({reasons})")


def check_escalation_graceful(result: RunResult, query: GoldenQuery) -> CheckResult:
    """A research failure must degrade to a letter without research, not lose the job."""
    failed = [d for d in result.research if d.get("error")]
    if not failed:
        return CheckResult(name="escalation_graceful", passed=True, skipped=True, detail="no research failures")
    done = {a.get("job_id") for a in result.applications}
    lost = [str(d["job_id"])[:30] for d in failed if d["job_id"] not in done]
    return CheckResult(name="escalation_graceful", passed=not lost,
                       detail=f"{len(failed)} research failures, jobs lost: {lost}" if lost
                       else f"{len(failed)} research failures, all jobs still got applications")


def check_no_redundant_research(result: RunResult, query: GoldenQuery) -> CheckResult:
    lookups = [normalise_company(d.get("company")) for d in result.research if d.get("decision")]
    if not lookups:
        return CheckResult(name="no_redundant_research", passed=True, skipped=True, detail="no lookups")
    dupes = sorted({c for c in lookups if lookups.count(c) > 1})
    return CheckResult(name="no_redundant_research", passed=not dupes,
                       detail=f"repeated lookups for {dupes}" if dupes else f"{len(lookups)} distinct companies researched")


def _count(items) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for i in items:
        counts[i] = counts.get(i, 0) + 1
    return counts


def check_tool_sequence(result: RunResult, query: GoldenQuery) -> CheckResult:
    """search_freehire runs once and first; LLM calls match jobs processed (retries are noted, not failed)."""
    calls = result.tools_called
    if not calls:
        return CheckResult(name="tool_sequence", passed=True, skipped=True, detail="no tool calls recorded")
    problems: List[str] = []
    searches = calls.count("search_freehire")
    if searches > 1:
        problems.append(f"search_freehire started {searches} times")
    if "llm_chat" in calls and searches and calls.index("llm_chat") < calls.index("search_freehire"):
        problems.append("LLM called before search")
    llm = calls.count("llm_chat")
    if llm and not result.jobs:
        problems.append(f"{llm} LLM calls but no jobs")
    processed = len(result.applications) + len(result.failed_jobs)
    expected_llm = processed + result.grounding_retries
    note = (f"; {llm} LLM calls for {processed} jobs + {result.grounding_retries} grounding retries (retries?)"
            if llm != expected_llm and result.jobs else "")
    return CheckResult(name="tool_sequence", passed=not problems,
                       detail=("; ".join(problems) or f"search once, then {llm} LLM calls") + note)


CHECKS: List[Callable[[RunResult, GoldenQuery], CheckResult]] = [
    check_status, check_min_jobs, check_format, check_addressing, check_grounding,
    check_relevance, check_search_honored, check_tools, check_tool_selection, check_tool_sequence,
    check_escalation_graceful, check_no_redundant_research,
]


def score_result(result: RunResult, query: GoldenQuery) -> QueryScore:
    return QueryScore(result=result, checks=[c(result, query) for c in CHECKS])
