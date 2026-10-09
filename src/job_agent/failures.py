"""
Day 8 + Day 10: Failure taxonomy and exception classification.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel
import requests
import openai

class FailureCategory(str, Enum):
    MISSING_DATA = "MISSING_DATA"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    DEAD_API = "DEAD_API"
    TIMEOUT = "TIMEOUT"
    PARTIAL_COMPLETION = "PARTIAL_COMPLETION"
    GUARDRAIL_TRIGGERED = "GUARDRAIL_TRIGGERED"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    AUTH_ERROR = "AUTH_ERROR"
    UNKNOWN = "UNKNOWN"

class RetryPolicy(str, Enum):
    NOT_RETRYABLE = "NOT_RETRYABLE"
    RETRY_SAME = "RETRY_SAME"
    RETRY_MODIFIED = "RETRY_MODIFIED"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"

class FailureRecord(BaseModel):
    category: FailureCategory
    retry_policy: RetryPolicy
    tool_name: Optional[str] = None
    attempt_number: Optional[int] = None
    message: Optional[str] = None

# Rate limiting and server-side errors: worth retrying with backoff.
_TRANSIENT_STATUSES = (429, 500, 502, 503, 504)


def classify_exception(
    exception: Exception,
    tool_name: Optional[str] = None,
    attempt_number: Optional[int] = None
) -> FailureRecord:
    """
    Classifies an exception into a FailureCategory and determines RetryPolicy.
    """
    msg = str(exception)
    
    # Day 15: Explicit timeout and connection drop handling
    if isinstance(exception, (TimeoutError, requests.Timeout, openai.APITimeoutError, openai.APIConnectionError)):
        return FailureRecord(
            category=FailureCategory.TIMEOUT,
            retry_policy=RetryPolicy.RETRY_SAME,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"Connection/Timeout error: {msg}"
        )
    
    # Connection never established (DNS failure, refused). Timeouts were handled above.
    if isinstance(exception, requests.ConnectionError):
        return FailureRecord(
            category=FailureCategory.DEAD_API,
            retry_policy=RetryPolicy.RETRY_SAME,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"Connection failed: {msg}"
        )

    # A 2xx body that is not JSON is usually a gateway or error page, often transient.
    if isinstance(exception, requests.exceptions.JSONDecodeError):
        return FailureRecord(
            category=FailureCategory.MALFORMED_RESPONSE,
            retry_policy=RetryPolicy.RETRY_SAME,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"Response was not valid JSON: {msg}"
        )

    # HTTP errors
    if isinstance(exception, requests.HTTPError):
        # `is not None`: a requests.Response with a 4xx/5xx status is falsy.
        status_code = exception.response.status_code if exception.response is not None else None

        if status_code in (401, 403):
            return FailureRecord(
                category=FailureCategory.AUTH_ERROR,
                retry_policy=RetryPolicy.NOT_RETRYABLE,
                tool_name=tool_name,
                attempt_number=attempt_number,
                message=f"Auth error ({status_code}): {msg}"
            )

        if status_code == 408:
            return FailureRecord(
                category=FailureCategory.TIMEOUT,
                retry_policy=RetryPolicy.RETRY_SAME,
                tool_name=tool_name,
                attempt_number=attempt_number,
                message=f"Request timeout ({status_code}): {msg}"
            )

        if status_code in _TRANSIENT_STATUSES:
            return FailureRecord(
                category=FailureCategory.DEAD_API,
                retry_policy=RetryPolicy.RETRY_SAME,
                tool_name=tool_name,
                attempt_number=attempt_number,
                message=f"Service unavailable or rate limited ({status_code}): {msg}"
            )

        if status_code == 400:
            return FailureRecord(
                category=FailureCategory.MALFORMED_RESPONSE,
                retry_policy=RetryPolicy.NOT_RETRYABLE,
                tool_name=tool_name,
                attempt_number=attempt_number,
                message=f"Bad request ({status_code}): {msg}"
            )

    # OpenAI context overflow
    if isinstance(exception, openai.APIError) and "context_length_exceeded" in msg.lower():
        return FailureRecord(
            category=FailureCategory.CONTEXT_OVERFLOW,
            retry_policy=RetryPolicy.RETRY_MODIFIED,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"Context overflow: {msg}"
        )
    
    # An exhausted quota is reported as a 429 RateLimitError but waiting will not fix it.
    if isinstance(exception, openai.RateLimitError) and "insufficient_quota" in msg.lower():
        return FailureRecord(
            category=FailureCategory.AUTH_ERROR,
            retry_policy=RetryPolicy.MANUAL_INTERVENTION,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"OpenAI quota exhausted, check billing: {msg}"
        )

    # OpenAI rate limit (429) and server errors (5xx): transient
    if isinstance(exception, (openai.RateLimitError, openai.InternalServerError)):
        return FailureRecord(
            category=FailureCategory.DEAD_API,
            retry_policy=RetryPolicy.RETRY_SAME,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"OpenAI rate limited or unavailable: {msg}"
        )

    # OpenAI auth errors
    if isinstance(exception, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return FailureRecord(
            category=FailureCategory.AUTH_ERROR,
            retry_policy=RetryPolicy.NOT_RETRYABLE,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"OpenAI auth error: {msg}"
        )
    
    # Default: unknown
    return FailureRecord(
        category=FailureCategory.UNKNOWN,
        retry_policy=RetryPolicy.NOT_RETRYABLE,
        tool_name=tool_name,
        attempt_number=attempt_number,
        message=f"Unknown error: {msg}"
    )