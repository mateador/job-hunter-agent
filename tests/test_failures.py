from types import SimpleNamespace

import openai
import pytest
import requests

from src.job_agent.failures import FailureCategory, RetryPolicy, classify_exception


def http_error(status):
    response = requests.Response()  # real object: its truthiness is False for 4xx/5xx
    response.status_code = status
    return requests.HTTPError(response=response)


def openai_error(cls, status, message="m"):
    request = SimpleNamespace(method="POST", url="https://example.test")
    return cls(message, response=SimpleNamespace(request=request, status_code=status, headers={}), body=None)


@pytest.mark.parametrize("status, category, policy", [
    (401, FailureCategory.AUTH_ERROR, RetryPolicy.NOT_RETRYABLE),
    (403, FailureCategory.AUTH_ERROR, RetryPolicy.NOT_RETRYABLE),
    (429, FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME),
    (500, FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME),
    (502, FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME),
    (503, FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME),
    (504, FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME),
    (408, FailureCategory.TIMEOUT, RetryPolicy.RETRY_SAME),
    (404, FailureCategory.UNKNOWN, RetryPolicy.NOT_RETRYABLE),
    (400, FailureCategory.MALFORMED_RESPONSE, RetryPolicy.NOT_RETRYABLE),
])
def test_http_status_is_classified_from_a_real_response(status, category, policy):
    record = classify_exception(http_error(status), tool_name="search_freehire")
    assert (record.category, record.retry_policy) == (category, policy)


def test_http_error_without_a_response_is_unknown():
    assert classify_exception(requests.HTTPError()).category == FailureCategory.UNKNOWN


def test_timeouts_and_dropped_connections_are_retried():
    request = SimpleNamespace(method="POST", url="https://example.test")
    for exc in (requests.Timeout(), openai.APITimeoutError(request=request), openai.APIConnectionError(request=request)):
        record = classify_exception(exc)
        assert (record.category, record.retry_policy) == (FailureCategory.TIMEOUT, RetryPolicy.RETRY_SAME)


def test_openai_auth_and_context_overflow():
    auth = classify_exception(openai_error(openai.AuthenticationError, 401))
    assert (auth.category, auth.retry_policy) == (FailureCategory.AUTH_ERROR, RetryPolicy.NOT_RETRYABLE)
    overflow = classify_exception(openai_error(openai.BadRequestError, 400, "context_length_exceeded"))
    assert (overflow.category, overflow.retry_policy) == (FailureCategory.CONTEXT_OVERFLOW, RetryPolicy.RETRY_MODIFIED)


def test_connection_failures_are_retried_but_timeouts_stay_timeouts():
    dns = classify_exception(requests.ConnectionError("name resolution failed"))
    assert (dns.category, dns.retry_policy) == (FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME)
    assert classify_exception(requests.ConnectTimeout()).category == FailureCategory.TIMEOUT


def test_non_json_body_is_retried():
    record = classify_exception(requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0))
    assert (record.category, record.retry_policy) == (FailureCategory.MALFORMED_RESPONSE, RetryPolicy.RETRY_SAME)


def test_openai_rate_limit_and_server_errors_are_retried():
    for exc in (openai_error(openai.RateLimitError, 429, "Rate limit reached"),
                openai_error(openai.InternalServerError, 500)):
        record = classify_exception(exc)
        assert (record.category, record.retry_policy) == (FailureCategory.DEAD_API, RetryPolicy.RETRY_SAME)


def test_exhausted_quota_is_not_retried():
    record = classify_exception(openai_error(openai.RateLimitError, 429, "insufficient_quota: check your plan"))
    assert (record.category, record.retry_policy) == (FailureCategory.AUTH_ERROR, RetryPolicy.MANUAL_INTERVENTION)


def test_openai_permission_denied_is_an_auth_error():
    assert classify_exception(openai_error(openai.PermissionDeniedError, 403)).category == FailureCategory.AUTH_ERROR
