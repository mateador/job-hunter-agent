"""Aggregate scored queries into JSON and Markdown eval reports."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .result_models import QueryScore, ScenarioResult


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
    usages = [s.result.usage for s in scores if s.result.usage]
    decisions = [d for s in scores for d in s.result.research]
    apps = [a for s in scores for a in s.result.applications]
    reasons: Dict[str, int] = defaultdict(int)
    for d in decisions:
        reasons[d["reason"]] += 1
    return {
        "cost": _summarize_cost(usages, len([a for s in scores for a in s.result.applications]), len(scores)),
        "grounding_guard": {
            "applications": len(apps),
            "retries": sum(s.result.grounding_retries for s in scores),
            "flagged": sum(1 for a in apps if a.get("warnings")),
        },
        "structure_guard": {
            "applications": len(apps),
            "retries": sum(s.result.structure_retries for s in scores),
            "flagged": sum(s.result.structure_flagged for s in scores),
        },
        "escalation": {
            "jobs": len(decisions),
            "researched": sum(1 for d in decisions if d["decision"]),
            "failures": sum(1 for d in decisions if d.get("error")),
            "by_reason": dict(sorted(reasons.items())),
        },
        "total": len(scores),
        "passed": sum(s.passed for s in scores),
        "pass_rate": rate([s.passed for s in scores]),
        "by_category": {k: {"n": len(v), "pass_rate": rate(v)} for k, v in sorted(by_cat.items())},
        "by_check": {k: {"n": len(v), "pass_rate": rate(v), "mean_score": rate(scores_by_check.get(k, []))}
                     for k, v in sorted(by_check.items())},
        "latency_mean_s": (sum(latencies) / len(latencies)) if latencies else None,
        "latency_max_s": max(latencies) if latencies else None,
    }


def _summarize_cost(usages: List[Dict[str, Any]], applications: int, queries: int) -> Dict[str, Any]:
    keys = ("calls", "prompt_tokens", "completion_tokens", "cached_tokens", "total_tokens", "cost_usd", "unpriced_calls")
    total = {k: sum(u.get(k, 0) for u in usages) for k in keys}
    by_purpose: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost_usd": 0.0})
    by_model: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost_usd": 0.0})
    for u in usages:
        for group, target in ((u.get("by_purpose", {}), by_purpose), (u.get("by_model", {}), by_model)):
            for name, b in group.items():
                for k in ("calls", "tokens", "cost_usd"):
                    target[name][k] += b.get(k, 0)
    return {
        **total,
        "synthetic": any(u.get("synthetic") for u in usages),
        "cost_per_application_usd": (total["cost_usd"] / applications) if applications else None,
        "cost_per_query_usd": (total["cost_usd"] / queries) if queries else None,
        "by_purpose": dict(sorted(by_purpose.items())),
        "by_model": dict(sorted(by_model.items())),
    }


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _cost_section(c: Dict[str, Any]) -> List[str]:
    if not c["calls"]:
        return []
    from src.job_agent.pricing import pricing_note
    lines = ["## Cost", ""]
    if c["synthetic"]:
        lines += ["> Mock mode: token counts are synthetic (about 4 characters per token). The plumbing is real; the numbers are not.", ""]
    per_app = c["cost_per_application_usd"]
    lines += [
        f"**Estimated total:** ${c['cost_usd']:.4f} for {c['calls']} LLM calls, {c['total_tokens']:,} tokens "
        f"({c['prompt_tokens']:,} prompt, {c['completion_tokens']:,} completion, {c['cached_tokens']:,} cached).",
        "",
        f"Per application: {'n/a' if per_app is None else f'${per_app:.4f}'}. "
        f"Per query: ${c['cost_per_query_usd']:.4f}.",
        "",
    ]
    if c["unpriced_calls"]:
        lines += [f"**{c['unpriced_calls']} calls used a model with no price in `pricing.json`; their cost is NOT included above.**", ""]
    lines += ["| Purpose | Calls | Tokens | Est. cost |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['calls']} | {v['tokens']:,} | ${v['cost_usd']:.4f} |" for k, v in c["by_purpose"].items()]
    lines += ["", "| Model | Calls | Tokens | Est. cost |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['calls']} | {v['tokens']:,} | ${v['cost_usd']:.4f} |" for k, v in c["by_model"].items()]
    lines += ["", f"_Costs are estimates at {pricing_note()}. They are not billing: credits and free tiers are not reflected, "
                  "and failed or timed-out attempts report no usage so are not counted._", ""]
    return lines


def render_markdown(scores: List[QueryScore], mode: str, timestamp: str,
                    scenarios: Optional[List[ScenarioResult]] = None,
                    notes: Optional[List[str]] = None) -> str:
    s = summarize(scores)
    lines = [
        f"# Eval Report ({mode} mode)", "",
        f"Generated: {timestamp}", "",
        f"**Overall:** {s['passed']}/{s['total']} queries passed ({_pct(s['pass_rate'])})", "",
    ]
    for note in notes or []:
        lines += [f"> **{note}**", ""]
    if mode == "mock":
        lines += ["> Mock mode: canned jobs and LLM output. This validates the harness, not the agent.", ""]
    lines += ["## By category", "", "| Category | Queries | Pass rate |", "|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {_pct(v['pass_rate'])} |" for k, v in s["by_category"].items()]
    lines += ["", "## By check", "",
              "| Check | Evaluated | Pass rate | Mean score |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {_pct(v['pass_rate'])} | {_pct(v['mean_score'])} |" for k, v in s["by_check"].items()]
    lines += ["", "_Mean score = share of applications (or jobs, for relevance) passing the check._"]
    esc = s["escalation"]
    if esc["jobs"]:
        reasons = ", ".join(f"{k}: {v}" for k, v in esc["by_reason"].items())
        lines += ["", f"**Escalation:** {esc['researched']}/{esc['jobs']} jobs researched via DuckDuckGo "
                      f"({esc['failures']} failed). Decisions: {reasons}."]
    gg = s["grounding_guard"]
    if gg["applications"]:
        lines += ["", f"**Grounding guard:** {gg['retries']} of {gg['applications']} applications regenerated, "
                      f"{gg['flagged']} still flagged for review after the retry."]
    sg = s["structure_guard"]
    if sg["retries"] or sg["flagged"]:
        lines += ["", f"**Structure guard:** {sg['retries']} of {sg['applications']} applications regenerated for missing "
                      f"bullets or an unusable letter, {sg['flagged']} still defective after the retry."]
    lat = s["latency_mean_s"]
    lines += ["", f"Latency: mean {lat:.2f}s, max {s['latency_max_s']:.2f}s" if lat is not None else "", ""]
    lines += _cost_section(s["cost"])
    lines += ["## Per query", "", "| ID | Query | Result | Jobs | Latency | Cost | Failed checks |", "|---|---|---|---|---|---|---|"]
    for sc in scores:
        r = sc.result
        failed = ", ".join(c.name for c in sc.checks if not c.passed and not c.skipped and not c.informational) or "-"
        q = r.query.strip()[:40] or "(blank)"
        cost = f"${r.usage['cost_usd']:.4f}" if r.usage.get("calls") else "-"
        lines.append(f"| {r.query_id} | {q} | {'PASS' if sc.passed else 'FAIL'} | {len(r.jobs)} | {r.latency_s:.2f}s | {cost} | {failed} |")
    fails = [sc for sc in scores if not sc.passed]
    if fails:
        lines += ["", "## Failures", ""]
        for sc in fails:
            lines.append(f"### {sc.result.query_id}")
            lines += [f"- **{c.name}**: {c.detail}" for c in sc.checks if not c.passed and not c.skipped and not c.informational]
            lines.append("")
    if scenarios:
        ok = sum(r.passed for r in scenarios)
        lines += ["## Tool-selection scenarios", "", f"{ok}/{len(scenarios)} passed (hand-labelled, offline).", "",
                  "| Scenario | Result | Notes |", "|---|---|---|"]
        lines += [f"| {r.id} | {'PASS' if r.passed else 'FAIL'} | {'; '.join(r.problems) or r.description} |"
                  for r in scenarios]
        lines.append("")
    infos = [(sc.result.query_id, c) for sc in scores for c in sc.checks if c.informational and not c.passed]
    if infos:
        lines += ["## Informational (not scored)", ""]
        lines += [f"- {qid} / {c.name}: {c.detail}" for qid, c in infos]
    return "\n".join(lines) + "\n"


def write_reports(scores: List[QueryScore], mode: str, out_dir: Path,
                  scenarios: Optional[List[ScenarioResult]] = None,
                  notes: Optional[List[str]] = None) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    json_path, md_path = out_dir / f"eval_{mode}_{stamp}.json", out_dir / f"eval_{mode}_{stamp}.md"
    payload = {"mode": mode, "generated": now.isoformat(), "summary": summarize(scores),
               "scenarios": [r.model_dump() for r in scenarios or []],
               "notes": notes or [],
               "queries": [s.model_dump() | {"passed": s.passed} for s in scores]}
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(scores, mode, now.strftime("%Y-%m-%d %H:%M:%S"), scenarios, notes), encoding="utf-8")
    return json_path, md_path
