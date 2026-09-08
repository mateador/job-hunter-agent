"""
Day 9: Reusable retry mechanism with exponential backoff.
"""
import time
import logging
from typing import Callable, Any, Optional

from .failures import classify_exception, RetryPolicy
from .audit_logger import AuditLogger

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1.0

def execute_with_retry(
    func: Callable,
    args: tuple,
    kwargs: dict,
    audit_logger: AuditLogger,
    tool_name: str,
    modify_kwargs_fn: Optional[Callable[[dict, int], dict]] = None
) -> Any:
    """
    Executes a callable with retry logic based on the classified FailureRecord.
    
    - RETRY_SAME: Retries up to MAX_ATTEMPTS with exponential backoff.
    - RETRY_MODIFIED: Retries exactly once with adjusted parameters (via modify_kwargs_fn).
    - NOT_RETRYABLE / MANUAL_INTERVENTION: Fails immediately.
    """
    attempt = 1
    max_attempts = MAX_ATTEMPTS
    
    while attempt <= max_attempts:
        # 1. Log attempt start
        audit_logger.log_attempt(
            tool=tool_name,
            attempt_number=attempt,
            status="start",
            details={"kwargs": {k: v for k, v in kwargs.items() if not callable(v)}}
        )
        
        try:
            result = func(*args, **kwargs)
            
            # 2. Log success
            audit_logger.log_attempt(
                tool=tool_name,
                attempt_number=attempt,
                status="success"
            )
            return result
            
        except Exception as e:
            # 3. Classify the failure
            failure_record = classify_exception(
                e, 
                tool_name=tool_name, 
                attempt_number=attempt
            )
            
            # 4. Log failure
            audit_logger.log_attempt(
                tool=tool_name,
                attempt_number=attempt,
                status="failure",
                details={"failure_record": failure_record.model_dump()}
            )
            
            policy = failure_record.retry_policy
            
            # 5. Immediate failure for non-retryable or manual intervention
            if policy in (RetryPolicy.NOT_RETRYABLE, RetryPolicy.MANUAL_INTERVENTION):
                logger.warning(f"Failure {failure_record.category} is {policy.value}. Failing immediately.")
                raise e
                
            # 6. Check if we've hit the max attempts
            if attempt >= max_attempts:
                logger.error(f"Max attempts ({max_attempts}) reached for {tool_name}.")
                raise e
                
            # 7. RETRY_MODIFIED gets exactly one retry (so max_attempts becomes attempt + 1)
            if policy == RetryPolicy.RETRY_MODIFIED:
                max_attempts = min(attempt + 1, MAX_ATTEMPTS)
                
            # 8. Exponential backoff
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.info(
                f"Retrying {tool_name} in {delay:.2f}s "
                f"(attempt {attempt + 1}/{max_attempts}) due to {failure_record.category}"
            )
            time.sleep(delay)
            
            # 9. Modify kwargs if RETRY_MODIFIED
            if policy == RetryPolicy.RETRY_MODIFIED and modify_kwargs_fn:
                kwargs = modify_kwargs_fn(kwargs, attempt)
                audit_logger.log_attempt(
                    tool=tool_name,
                    attempt_number=attempt + 1,
                    status="modified",
                    details={"new_kwargs": {k: v for k, v in kwargs.items() if not callable(v)}}
                )
                
            attempt += 1