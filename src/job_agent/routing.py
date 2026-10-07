"""Model routing: which model serves which kind of LLM call.

Today every call uses the default model. An optional separate model for grounding retries is
supported because a retry means the first model just produced unsupported content; whether a
different model there is worth its cost is a question for the model comparison (evals.compare),
not a default.
"""
from typing import Optional

RETRY_PURPOSES = {"grounding_retry"}


class ModelRouter:
    def __init__(self, default: str, retry_model: Optional[str] = None) -> None:
        self.default = default
        self.retry_model = retry_model

    def model_for(self, purpose: Optional[str]) -> str:
        if purpose in RETRY_PURPOSES and self.retry_model:
            return self.retry_model
        return self.default
