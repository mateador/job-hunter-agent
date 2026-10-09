"""Re-score a saved eval run with the current checks, without any API calls.

Usage:
    python -m evals.rescore evals/results/eval_live_20261009_132309.json

Use it after fixing a check (a false positive, say) to see what a past run would score under the
corrected check. It re-applies the checks to the stored results only: the generated letters and
the agent's behaviour are unchanged, so it says nothing about the agent itself. Stored job
descriptions are truncated to 500 characters; checks that depend on them use the numbers saved
with each job.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dataset_schema import load_dataset
from .report import write_reports
from .result_models import QueryScore, RunResult, ScenarioResult
from .runner import DEFAULT_OUT
from .scoring import score_result


def rescore(payload: Dict[str, Any]) -> List[QueryScore]:
    queries = {q.id: q for q in load_dataset().queries}
    scores = []
    for item in payload["queries"]:
        result = RunResult.model_validate(item["result"])
        scores.append(score_result(result, queries[result.query_id]))
    return scores


def changes(payload: Dict[str, Any], scores: List[QueryScore]) -> List[str]:
    """One line per query whose pass/fail changed, with the checks that now differ."""
    lines = []
    for item, new in zip(payload["queries"], scores):
        old = {c["name"]: c["passed"] for c in item["checks"] if not c.get("skipped")}
        now = {c.name: c.passed for c in new.checks if not c.skipped}
        diff = [n for n in now if old.get(n) != now[n]]
        if diff or item["passed"] != new.passed:
            lines.append(f"{new.result.query_id}: {'PASS' if item['passed'] else 'FAIL'} -> "
                         f"{'PASS' if new.passed else 'FAIL'} (checks changed: {', '.join(diff) or 'none'})")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Re-score a saved eval run with the current checks (no API calls)")
    p.add_argument("results", type=Path, help="eval_<mode>_<timestamp>.json from a previous run")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)

    payload = json.loads(args.results.read_text(encoding="utf-8"))
    scores = rescore(payload)
    diff = changes(payload, scores)
    note = (f"Re-scored from {args.results.name} with the current checks; no new agent run. "
            f"{len(diff)} query result(s) changed." + ("" if not diff else " " + "; ".join(diff)))
    scenarios = [ScenarioResult.model_validate(s) for s in payload.get("scenarios", [])]
    json_path, md_path = write_reports(scores, f"{payload['mode']}_rescored", args.out, scenarios, notes=[note])
    old_pass = sum(i["passed"] for i in payload["queries"])
    print(f"Before: {old_pass}/{len(scores)} passed. After: {sum(s.passed for s in scores)}/{len(scores)} passed.")
    for line in diff:
        print("  " + line)
    print(f"Report: {md_path}\nData:   {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
