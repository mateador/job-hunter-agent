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

def classify_exception(
    exception: Exception,
    tool_name: Optional[str] = None,
    attempt_number: Optional[int] = None
) -> FailureRecord:
    """
    Classifies an exception into a FailureCategory and determines RetryPolicy.
    """
    msg = str(exception)
    
    # Day 10: Explicit timeout handling
    if isinstance(exception, (TimeoutError, requests.Timeout, openai.APITimeoutError)):
        return FailureRecord(
            category=FailureCategory.TIMEOUT,
            retry_policy=RetryPolicy.RETRY_SAME,
            tool_name=tool_name,
            attempt_number=attempt_number,
            message=f"Timeout: {msg}"
        )
    
    # HTTP errors
    if isinstance(exception, requests.HTTPError):
        status_code = exception.response.status_code if exception.response else None
        
        if status_code == 401 or status_code == 403:
            return FailureRecord(
                category=FailureCategory.AUTH_ERROR,
                retry_policy=RetryPolicy.NOT_RETRYABLE,
                tool_name=tool_name,
                attempt_number=attempt_number,
                message=f"Auth error ({status_code}): {msg}"
            )
        
        if status_code == 503 or status_code == 502:
            return FailureRecord(
                category=FailureCategory.DEAD_API,
                retry_policy=RetryPolicy.RETRY_SAME,
                tool_name=tool_name,
                attempt_number=attempt_number,
                message=f"Service unavailable ({status_code}): {msg}"
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
    
    # OpenAI auth errors
    if isinstance(exception, openai.AuthenticationError):
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