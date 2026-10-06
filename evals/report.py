"""Aggregate scored queries into JSON and Markdown eval reports."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .result_models import QueryScore


def summarize(scores: List[QueryScore]) -> Dict[str, Any]:
    by_cat: Dict[str, List[bool]] = defaultdict(list)
    by_check: Dict[str, List[bool]] = defaultdict(list)
    scores_by_check: Dict[str, List[float]] = defaultdict(list)
    for s in scores:
        by_cat[s.result.category].append(s.passed)
        for c in s.checks:
            if not c.skipped and not c.informational:
                by_check[c.name].append(c.passed)
                if c.score is not None:
                    scores_by_check[c.name].append(c.score)
    rate = lambda xs: (sum(xs) / len(xs)) if xs else None
    latencies = [s.result.latency_s for s in scores]
    return {
        "total": len(scores),
        "passed": sum(s.passed for s in scores),
        "pass_rate": rate([s.passed for s in scores]),
        "by_category": {k: {"n": len(v), "pass_rate": rate(v)} for k, v in sorted(by_cat.items())},
        "by_check": {k: {"n": len(v), "pass_rate": rate(v), "mean_score": rate(scores_by_check.get(k, []))}
                     for k, v in sorted(by_check.items())},
        "latency_mean_s": (sum(latencies) / len(latencies)) if latencies else None,
        "latency_max_s": max(latencies) if latencies else None,
    }


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def render_markdown(scores: List[QueryScore], mode: str, timestamp: str) -> str:
    s = summarize(scores)
    lines = [
        f"# Eval Report ({mode} mode)", "",
        f"Generated: {timestamp}", "",
        f"**Overall:** {s['passed']}/{s['total']} queries passed ({_pct(s['pass_rate'])})", "",
    ]
    if mode == "mock":
        lines += ["> Mock mode: canned jobs and LLM output. This validates the harness, not the agent.", ""]
    lines += ["## By category", "", "| Category | Queries | Pass rate |", "|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {_pct(v['pass_rate'])} |" for k, v in s["by_category"].items()]
    lines += ["", "## By check", "",
              "| Check | Evaluated | Pass rate | Mean score |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {_pct(v['pass_rate'])} | {_pct(v['mean_score'])} |" for k, v in s["by_check"].items()]
    lines += ["", "_Mean score = share of applications (or jobs, for relevance) passing the check._"]
    lat = s["latency_mean_s"]
    lines += ["", f"Latency: mean {lat:.2f}s, max {s['latency_max_s']:.2f}s" if lat is not None else "", ""]
    lines += ["## Per query", "", "| ID | Query | Result | Jobs | Latency | Failed checks |", "|---|---|---|---|---|---|"]
    for sc in scores:
        r = sc.result
        failed = ", ".join(c.name for c in sc.checks if not c.passed and not c.skipped and not c.informational) or "-"
        q = r.query.strip()[:40] or "(blank)"
        lines.append(f"| {r.query_id} | {q} | {'PASS' if sc.passed else 'FAIL'} | {len(r.jobs)} | {r.latency_s:.2f}s | {failed} |")
    fails = [sc for sc in scores if not sc.passed]
    if fails:
        lines += ["", "## Failures", ""]
        for sc in fails:
            lines.append(f"### {sc.result.query_id}")
            lines += [f"- **{c.name}**: {c.detail}" for c in sc.checks if not c.passed and not c.skipped and not c.informational]
            lines.append("")
    infos = [(sc.result.query_id, c) for sc in scores for c in sc.checks if c.informational and not c.passed]
    if infos:
        lines += ["## Informational (not scored)", ""]
        lines += [f"- {qid} / {c.name}: {c.detail}" for qid, c in infos]
    return "\n".join(lines) + "\n"


def write_reports(scores: List[QueryScore], mode: str, out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    json_path, md_path = out_dir / f"eval_{mode}_{stamp}.json", out_dir / f"eval_{mode}_{stamp}.md"
    payload = {"mode": mode, "generated": now.isoformat(), "summary": summarize(scores),
               "queries": [s.model_dump() | {"passed": s.passed} for s in scores]}
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(scores, mode, now.strftime("%Y-%m-%d %H:%M:%S")), encoding="utf-8")
    return json_path, md_path
