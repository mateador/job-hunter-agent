import json
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

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