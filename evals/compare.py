"""Compare models on the same golden queries: quality against estimated cost and latency.

Usage:
    python -m evals.compare --models gpt-4o-mini,gpt-5-nano --limit 6 --max-cost 0.50
    python -m evals.compare --mock --models a,b      # offline dry run (synthetic tokens)

Each model runs the same queries with the same checks. The table is the evidence for choosing a
default model or a retry model; it is not a verdict by itself (small samples, one run each).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.job_agent.pricing import price_for, pricing_note

from .dataset_schema import load_dataset
from .report import summarize
from .runner import DEFAULT_OUT, run_dataset_budgeted


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def compare_models(models: List[str], queries, live: bool, max_jobs: int, out_dir: Path,
                   max_cost: Optional[float] = None, retry_model: Optional[str] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for model in models:
        print(f"\n=== {model} ===")
        scores, stopped = run_dataset_budgeted(queries, live, max_jobs, model, out_dir / "compare" / _slug(model),
                                               retry_model, max_cost)
        s = summarize(scores)
        cost = s["cost"]
        rows.append({
            "model": model,
            "priced": price_for(model) is not None,
            "queries_run": len(scores),
            "stopped": stopped,
            "queries_passed": s["passed"],
            "pass_rate": s["pass_rate"],
            "checks": {k: v["pass_rate"] for k, v in s["by_check"].items()},
            "applications": sum(len(sc.result.applications) for sc in scores),
            "grounding_retries": s["grounding_guard"]["retries"],
            "grounding_flagged": s["grounding_guard"]["flagged"],
            "total_tokens": cost["total_tokens"],
            "cost_usd": cost["cost_usd"],
            "unpriced_calls": cost["unpriced_calls"],
            "cost_per_application_usd": cost["cost_per_application_usd"],
            "latency_mean_s": s["latency_mean_s"],
            "synthetic": cost["synthetic"],
        })
    return rows


def render_comparison(rows: List[Dict[str, Any]], mode: str, timestamp: str, queries: int) -> str:
    def pct(x): return "n/a" if x is None else f"{x:.0%}"
    def usd(x): return "n/a" if x is None else f"${x:.4f}"
    base = rows[0]
    lines = [f"# Model Comparison ({mode} mode)", "", f"Generated: {timestamp}", "",
             f"{queries} queries per model, same checks for each. First model ({base['model']}) is the reference.", ""]
    if mode == "mock":
        lines += ["> Mock mode: quality and token numbers are synthetic and identical across models. This only checks the tooling.", ""]
    lines += ["| Model | Queries passed | Grounding | Format | Applications | Retries / flagged | Est. cost | Cost / app | vs ref | Mean latency |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ratio = "-"
        if r is not base and base["cost_per_application_usd"] and r["cost_per_application_usd"] is not None:
            ratio = f"{r['cost_per_application_usd'] / base['cost_per_application_usd']:.2f}x"
        name = r["model"] + ("" if r["priced"] else " (unpriced)")
        lines.append(f"| {name} | {r['queries_passed']}/{r['queries_run']} ({pct(r['pass_rate'])}) | "
                     f"{pct(r['checks'].get('grounding'))} | {pct(r['checks'].get('format'))} | {r['applications']} | "
                     f"{r['grounding_retries']} / {r['grounding_flagged']} | {usd(r['cost_usd'])} | "
                     f"{usd(r['cost_per_application_usd'])} | {ratio} | "
                     f"{'n/a' if r['latency_mean_s'] is None else format(r['latency_mean_s'], '.1f') + 's'} |")
    for r in rows:
        if r["stopped"]:
            lines += ["", f"**{r['model']}:** {r['stopped']}"]
        if r["unpriced_calls"]:
            lines += ["", f"**{r['model']}:** {r['unpriced_calls']} calls have no price in `pricing.json`; cost is understated."]
    lines += ["", "## How to read this", "",
              "- Pass rate counts a query as passed only if every scored check passed for every application.",
              "- Each model ran once on a few queries: differences of one query are noise. Prefer a cost or quality gap that is large.",
              "- Cheaper is only better if grounding and format hold. A cheap model that fabricates costs more in review than it saves.",
              f"- Costs are estimates at {pricing_note()}; they are not billing.", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Compare models on the golden dataset")
    p.add_argument("--models", required=True, help="Comma-separated model ids; the first is the reference")
    p.add_argument("--mock", action="store_true", help="Offline dry run with synthetic usage")
    p.add_argument("--yes", action="store_true", help="Skip the live-mode confirmation prompt")
    p.add_argument("--ids", help="Comma-separated query ids")
    p.add_argument("--limit", type=int, help="Only the first N selected queries")
    p.add_argument("--max-jobs", type=int, default=2)
    p.add_argument("--max-cost", type=float, default=1.0, help="Per-model cap in USD (estimated, list price)")
    p.add_argument("--retry-model", help="Model for grounding retries, applied to every compared model")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)
    load_dotenv(Path(__file__).parent.parent / ".env")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if len(models) < 2:
        p.error("Give at least two models to compare")
    queries = load_dataset().queries
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        unknown = wanted - {q.id for q in queries}
        if unknown:
            p.error(f"Unknown query ids: {sorted(unknown)}")
        queries = [q for q in queries if q.id in wanted]
    if args.limit:
        queries = queries[: args.limit]

    live = not args.mock
    if live and not args.yes:
        calls = len(models) * len(queries) * (args.max_jobs + 1)
        unpriced = [m for m in models if price_for(m) is None]
        print(f"Live comparison: {len(models)} models x {len(queries)} queries, up to {calls} OpenAI calls, "
              f"capped at ${args.max_cost:.2f} estimated per model.")
        if unpriced:
            print(f"WARNING: no price for {unpriced}; the cap cannot protect you for those models.")
        if not sys.stdin.isatty() or input("Continue? [y/N] ").strip().lower() != "y":
            print("Aborted. Use --yes to skip this prompt.")
            return 1

    rows = compare_models(models, queries, live, args.max_jobs, args.out, args.max_cost, args.retry_model)
    mode = "live" if live else "mock"
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    args.out.mkdir(parents=True, exist_ok=True)
    md, js = args.out / f"compare_{mode}_{stamp}.md", args.out / f"compare_{mode}_{stamp}.json"
    md.write_text(render_comparison(rows, mode, now.strftime("%Y-%m-%d %H:%M:%S"), len(queries)), encoding="utf-8")
    js.write_text(json.dumps({"mode": mode, "generated": now.isoformat(), "queries": [q.id for q in queries],
                              "rows": rows}, indent=2, default=str), encoding="utf-8")
    print(f"\nComparison: {md}\nData:       {js}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
