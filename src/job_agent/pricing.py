"""Token pricing and cost estimation.

Prices live in pricing.json and are list prices: they estimate what a run would cost, not what
the account is actually billed (credits, free tiers and discounts are not reflected). A model
without a price is reported as unpriced; a price is never guessed.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

PRICING_PATH = Path(__file__).parent / "pricing.json"
_SNAPSHOT_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}$")


@lru_cache(maxsize=1)
def load_pricing(path: str = str(PRICING_PATH)) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalise_model(model: Optional[str]) -> str:
    """'gpt-4o-mini-2024-07-18' -> 'gpt-4o-mini' (the API reports dated snapshot ids)."""
    return _SNAPSHOT_SUFFIX.sub("", model or "")


def price_for(model: Optional[str]) -> Optional[Dict[str, float]]:
    return load_pricing()["models"].get(normalise_model(model))


def estimate_cost(
    model: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> Optional[float]:
    """Estimated USD cost of one call, or None if the model has no price."""
    price = price_for(model)
    if price is None:
        return None
    cached = min(max(cached_tokens, 0), prompt_tokens)
    return (
        (prompt_tokens - cached) * price["input"]
        + cached * price["cached_input"]
        + completion_tokens * price["output"]
    ) / 1_000_000


def pricing_note() -> str:
    p = load_pricing()
    state = "verified" if p.get("verified") else "NOT verified"
    return f"list prices as of {p['as_of']} ({state}), source {p['source_url']}"
