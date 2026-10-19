import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

# Strings longer than this are not written to the trace: prompts carry the candidate's CV.
MAX_LOGGED_CHARS = 200


def _fingerprint(text: str) -> Dict[str, Any]:
    return {"chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]}


def redact_for_log(value: Any) -> Any:
    """A copy of `value` that is safe to write to the trace.

    The trace must show what was called and with which small parameters (query, limit), but never
    the content of a prompt: it contains the CV. Long strings become {chars, sha256-prefix} (enough
    to see that two calls sent the same text), and chat messages keep only their role and that
    fingerprint. Numbers, booleans and short strings are kept as they are.
    """
    if isinstance(value, str):
        return value if len(value) <= MAX_LOGGED_CHARS else _fingerprint(value)
    if isinstance(value, dict):
        if "role" in value and isinstance(value.get("content"), str):
            return {"role": value["role"], "content": _fingerprint(value["content"])}
        return {k: redact_for_log(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_for_log(v) for v in value]
    return value


class AuditLogger:
    def __init__(self, trace_dir: str = "traces"):
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.trace_file = self.trace_dir / f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        
    def log_event(self, event_type: str, **kwargs):
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            **kwargs
        }
        with open(self.trace_file, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")
            
    def log_attempt(self, tool: str, attempt_number: int, status: str, details: Optional[Dict[str, Any]] = None):
        """Logs granular attempt telemetry for retry observability."""
        self.log_event(
            event_type="attempt",
            tool=tool,
            attempt_number=attempt_number,
            status=status,
            details=details or {}
        )
        
    def log_failure(self, failure_record):
        self.log_event(
            event_type="failure",
            failure_record=failure_record.model_dump()
        )