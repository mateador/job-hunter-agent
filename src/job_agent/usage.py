"""Per-call LLM usage records and their aggregation."""
from collections import defaultdict
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .pricing import estimate_cost


class LLMUsage(BaseModel):
    model: str
    purpose: str = "unspecified"
    job_id: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0  # part of completion_tokens (hidden thinking), billed as output
    latency_s: float = 0.0
    synthetic: bool = False  # True for mock-mode estimates that did not come from an API response

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> Optional[float]:
        return estimate_cost(self.model, self.prompt_tokens, self.completion_tokens, self.cached_tokens)


def _bucket() -> Dict[str, Any]:
    return {"calls": 0, "tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0}


class UsageTracker:
    """Collects LLMUsage records for one run.

    Only successful calls are recorded: the API reports no usage for failed or timed-out
    attempts, so retried calls are undercounted.
    """

    def __init__(self) -> None:
        self.records: List[LLMUsage] = []

    def record(self, usage: LLMUsage) -> None:
        self.records.append(usage)

    def summary(self) -> Dict[str, Any]:
        total = _bucket()
        by_purpose: Dict[str, Dict[str, Any]] = defaultdict(_bucket)
        by_model: Dict[str, Dict[str, Any]] = defaultdict(_bucket)
        prompt = completion = cached = 0
        for r in self.records:
            prompt += r.prompt_tokens
            completion += r.completion_tokens
            cached += r.cached_tokens
            cost = r.cost_usd
            for bucket in (total, by_purpose[r.purpose], by_model[r.model]):
                bucket["calls"] += 1
                bucket["tokens"] += r.total_tokens
                if cost is None:
                    bucket["unpriced_calls"] += 1
                else:
                    bucket["cost_usd"] += cost
        return {
            "calls": total["calls"],
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cached_tokens": cached,
            "total_tokens": prompt + completion,
            "cost_usd": total["cost_usd"],
            "unpriced_calls": total["unpriced_calls"],  # their cost is NOT in cost_usd
            "synthetic": any(r.synthetic for r in self.records),
            "by_purpose": {k: dict(v) for k, v in sorted(by_purpose.items())},
            "by_model": {k: dict(v) for k, v in sorted(by_model.items())},
        }
