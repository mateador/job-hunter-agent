import json
import os
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """
    Day 5: Structured JSONL audit trail.

    Every event in the agent loop is appended as a single JSON line
    to a per-run file inside the logs/ directory.

    Design decisions:
    - JSONL (one JSON object per line) for easy appending and grep.
    - One file per run, named with timestamp + short run_id.
    - Sensitive fields (CV text) are logged locally but logs/ is gitignored.
    - API keys are NEVER logged (they live in env vars, not messages).
    """

    def __init__(self, run_id: str, logs_dir: str = "logs"):
        self.run_id = run_id
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_id = run_id[:8]
        self.log_file = self.logs_dir / f"run_{timestamp}_{short_id}.jsonl"

        self.step = 0
        self._event_count = 0

    def log(self, event_type: str, data: dict) -> None:
        entry = {
            "timestamp": utc_now_iso(),
            "run_id": self.run_id,
            "step": self.step,
            "event_type": event_type,
            "data": data,
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

        self._event_count += 1

    def increment_step(self) -> None:
        self.step += 1

    @property
    def file_path(self) -> str:
        return str(self.log_file)

    @property
    def event_count(self) -> int:
        return self._event_count
