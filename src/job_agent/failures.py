"""
Day 8: Failure Taxonomy

Exception hierarchy and retryability classification for all failure modes.

This module is the foundation for:
- Day 9:  Retry with exponential backoff
- Day 10: Timeout enforcement
- Day 11: Checkpointing
- Day 12: Resume after failure
- Day 13: Partial completion recovery
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FailureCategory(str, Enum):
    MISSING_DATA = "missing_data"
    MALFORMED_RESPONSE = "malformed_response"
    DEAD_API = "dead_api"
    TIMEOUT = "timeout"
    PARTIAL_COMPLETION = "partial_completion"
    GUARDRAIL_TRIGGERED = "guardrail_triggered"
    CONTEXT_OVERFLOW = "context_overflow"
    AUTH_ERROR = "auth_error"
    UNKNOWN = "unknown"


class RetryPolicy(str, Enum):
    RETRY_SAME = "retry_same"
    RETRY_MODIFIED = "retry_modified"
    NOT_RETRYABLE = "not_retryable"
    MANUAL_INTERVENTION = "manual_intervention"


# ---------------------------------------------------------------------------
# Structured failure record (for audit logging)
# ---------------------------------------------------------------------------

class FailureRecord(BaseModel):
    category: FailureCategory
    retry_policy: RetryPolicy
    message: str
    source: str = Field(description="Which component raised the failure")
    original_error_type: str | None = None
    is_recoverable: bool = True
    attempt: int = Field(default=1, description="Which attempt this failure occurred on")


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class AgentError(Exception):
    """Base exception for all classified agent errors."""

    def __init__(
        self,
        message: str,
        category: FailureCategory,
        retry_policy: RetryPolicy,
        source: str,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.category = category
        self.retry_policy = retry_policy
        self.source = source
        self.original_error = original_error

    def to_record(self, attempt: int = 1) -> FailureRecord:
        return FailureRecord(
            category=self.category,
            retry_policy=self.retry_policy,
            message=str(self),
            source=self.source,
            original_error_type=type(self.original_error).__name__ if self.original_error else None,
            is_recoverable=self.retry_policy != RetryPolicy.MANUAL_INTERVENTION,
            attempt=attempt,
        )


class MissingDataError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.MISSING_DATA, RetryPolicy.RETRY_MODIFIED, source, original_error)


class MalformedResponseError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.MALFORMED_RESPONSE, RetryPolicy.RETRY_SAME, source, original_error)


class DeadAPIError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME, source, original_error)


class AgentTimeoutError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.TIMEOUT, RetryPolicy.RETRY_SAME, source, original_error)


class PartialCompletionError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.PARTIAL_COMPLETION, RetryPolicy.RETRY_MODIFIED, source, original_error)


class GuardrailError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.GUARDRAIL_TRIGGERED, RetryPolicy.NOT_RETRYABLE, source, original_error)


class ContextOverflowError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.CONTEXT_OVERFLOW, RetryPolicy.RETRY_MODIFIED, source, original_error)


class AuthError(AgentError):
    def __init__(self, message: str, source: str, original_error: Optional[Exception] = None):
        super().__init__(message, FailureCategory.AUTH_ERROR, RetryPolicy.MANUAL_INTERVENTION, source, original_error)


# ---------------------------------------------------------------------------
# Classification function
# ---------------------------------------------------------------------------

def classify_exception(exc: Exception, source: str) -> FailureRecord:
    """
    Map any Python exception to a structured FailureRecord.

    This is the single entry point for failure classification.
    Every catch block in the system should call this function.
    """

    exc_type = type(exc).__name__
    exc_msg = str(exc)
    exc_lower = exc_msg.lower()

    # --- requests library exceptions ---
    try:
        import requests

        if isinstance(exc, requests.exceptions.ConnectionError):
            return DeadAPIError(exc_msg, source, exc).to_record()

        if isinstance(exc, requests.exceptions.Timeout):
            return AgentTimeoutError(exc_msg, source, exc).to_record()

        if isinstance(exc, requests.exceptions.HTTPError):
            response = getattr(exc, "response", None)
            if response is not None:
                status = response.status_code
                if status in (401, 403):
                    return AuthError(f"HTTP {status}: {exc_msg}", source, exc).to_record()
                if status == 429:
                    return DeadAPIError(f"HTTP 429 rate limited: {exc_msg}", source, exc).to_record()
                if status >= 500:
                    return DeadAPIError(f"HTTP {status}: {exc_msg}", source, exc).to_record()
                if status == 404:
                    return MissingDataError(f"HTTP 404: {exc_msg}", source, exc).to_record()
            return DeadAPIError(exc_msg, source, exc).to_record()

    except ImportError:
        pass

    # --- OpenAI exceptions ---
    try:
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return AuthError(exc_msg, source, exc).to_record()

        if isinstance(exc, openai.RateLimitError):
            return DeadAPIError(f"Rate limited: {exc_msg}", source, exc).to_record()

        if isinstance(exc, openai.APITimeoutError):
            return AgentTimeoutError(exc_msg, source, exc).to_record()

    except ImportError:
        pass

    # --- JSON / schema errors ---
    import json
    if isinstance(exc, json.JSONDecodeError):
        return MalformedResponseError(exc_msg, source, exc).to_record()

    try:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            return MalformedResponseError(exc_msg, source, exc).to_record()
    except ImportError:
        pass

    # --- Value / key errors → often missing data ---
    if isinstance(exc, (ValueError, KeyError)):
        if any(word in exc_lower for word in ("empty", "missing", "none", "not found", "required")):
            return MissingDataError(exc_msg, source, exc).to_record()
        return MalformedResponseError(exc_msg, source, exc).to_record()

    # --- Timeout built-in ---
    if isinstance(exc, TimeoutError):
        return AgentTimeoutError(exc_msg, source, exc).to_record()

    # --- Fallback ---
    return FailureRecord(
        category=FailureCategory.UNKNOWN,
        retry_policy=RetryPolicy.NOT_RETRYABLE,
        message=exc_msg,
        source=source,
        original_error_type=exc_type,
        is_recoverable=False,
    )