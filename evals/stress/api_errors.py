"""Live API error probes (no CV, no job data): how do REAL OpenAI errors classify and retry?

Usage (your terminal, venv active, OPENAI_API_KEY set; the prompt is the single word "ping"):
    python -m evals.stress.api_errors

Probes: invalid API key (401), nonexistent model (404), a 1 ms client timeout (real timeouts, real 1s/2s
backoff), and gpt-5.4 with reasoning_effort="minimal" (a known 400). The first three cost nothing (rejected or
never completed); the 400 is rejected before generation. Backoff delays are MEASURED from trace timestamps.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from src.job_agent.audit_logger import AuditLogger
from src.job_agent.llm_client import LLMClient
from src.job_agent.routing import ModelRouter

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
MESSAGES = [{"role": "user", "content": "ping"}]


def probe(name: str, expect: str, model: str = "gpt-4o-mini", api_key: str = None, timeout: str = None,
          effort: str = None) -> Dict[str, Any]:
    real_key = os.environ["OPENAI_API_KEY"]
    old_timeout = os.environ.get("LLM_TIMEOUT")
    os.environ["OPENAI_API_KEY"] = api_key or real_key
    if timeout:
        os.environ["LLM_TIMEOUT"] = timeout
    try:
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLogger(trace_dir=tmp)
            client = LLMClient(audit_logger=audit, model=model, router=ModelRouter(model), reasoning_effort=effort)
            error = None
            try:
                client.chat(MESSAGES)
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)[:100]}"
            events = [json.loads(line) for line in audit.trace_file.read_text().splitlines()]
    finally:
        os.environ["OPENAI_API_KEY"] = real_key
        if old_timeout is None:
            os.environ.pop("LLM_TIMEOUT", None)
        else:
            os.environ["LLM_TIMEOUT"] = old_timeout
    starts = [e for e in events if e["event_type"] == "attempt" and e["status"] == "start"]
    fails = [e["details"]["failure_record"] for e in events if e["event_type"] == "attempt" and e["status"] == "failure"]
    stamps = [datetime.fromisoformat(e["timestamp"]) for e in starts]
    gaps = [round((b - a).total_seconds(), 2) for a, b in zip(stamps, stamps[1:])]
    return {"probe": name, "expect": expect, "exception": error, "attempts": len(starts),
            "category": "/".join(sorted({f["category"] for f in fails})) or "-",
            "policy": "/".join(sorted({f["retry_policy"] for f in fails})) or "-",
            "gaps_between_attempts_s": gaps}


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set")
        return 2
    rows: List[Dict[str, Any]] = [
        probe("invalid key", "401 -> AUTH_ERROR / NOT_RETRYABLE, 1 attempt", api_key="sk-invalid-stress-test"),
        probe("unknown model", "404 -> UNKNOWN / NOT_RETRYABLE, 1 attempt (predicted from the classifier)",
              model="gpt-does-not-exist"),
        probe("1 ms timeout", "TIMEOUT / RETRY_SAME, 3 attempts, gaps about 1s then 2s", timeout="0.001"),
        probe("gpt-5.4 effort=minimal", "400 -> UNKNOWN / NOT_RETRYABLE (predicted), or model not available",
              model="gpt-5.4", effort="minimal"),
    ]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    lines = [f"# Live API error probes\n\nGenerated: {stamp}. Prompt: \"ping\". No CV, no job data.\n",
             "| Probe | Expected | Exception | Attempts | Category / policy | Gaps (s) |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['probe']} | {r['expect']} | {r['exception']} | {r['attempts']} | "
                     f"{r['category']} / {r['policy']} | {r['gaps_between_attempts_s']} |")
    md = "\n".join(lines) + "\n"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"stress_api_errors_{stamp}.md").write_text(md)
    (RESULTS_DIR / f"stress_api_errors_{stamp}.json").write_text(json.dumps(rows, indent=2))
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
