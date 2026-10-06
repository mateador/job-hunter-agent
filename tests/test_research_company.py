from unittest.mock import patch

import pytest

from src.job_agent.audit_logger import AuditLogger
from ddgs.exceptions import DDGSException

from src.job_agent.tools import _is_ad_result, research_company, search_duckduckgo

ORGANIC = {"title": "Acme - Wikipedia", "href": "https://en.wikipedia.org/wiki/Acme", "body": "Acme makes anvils."}
AD = {"title": "Acme Official", "href": "https://www.bing.com/aclick?ld=abc&u=xyz", "body": "Buy now"}
DDG_AD = {"title": "Acme", "href": "https://duckduckgo.com/y.js?ad=1", "body": "Sponsored"}


@pytest.fixture
def logger(tmp_path):
    return AuditLogger(trace_dir=str(tmp_path))


def test_ad_detection():
    assert _is_ad_result(AD["href"]) and _is_ad_result(DDG_AD["href"]) and _is_ad_result("")
    assert not _is_ad_result(ORGANIC["href"])


def test_filters_ads_and_builds_summary(logger):
    with patch("src.job_agent.tools.search_duckduckgo", return_value=[AD, ORGANIC, DDG_AD]):
        research = research_company("Acme", audit_logger=logger)
    assert research.company_name == "Acme"
    assert research.sources == [ORGANIC["href"]]
    assert "Acme makes anvils." in research.summary and "Buy now" not in research.summary


def test_returns_none_when_nothing_useful(logger):
    with patch("src.job_agent.tools.search_duckduckgo", return_value=[AD]):
        assert research_company("Acme", audit_logger=logger) is None
    with patch("src.job_agent.tools.search_duckduckgo", return_value=[]):
        assert research_company("Acme", audit_logger=logger) is None
    empty_body = {**ORGANIC, "body": "  "}
    with patch("src.job_agent.tools.search_duckduckgo", return_value=[empty_body]):
        assert research_company("Acme", audit_logger=logger) is None


def test_limits_results_and_snippet_length(logger):
    many = [{"title": f"T{i}", "href": f"https://s{i}.example/p", "body": "x" * 1000} for i in range(10)]
    with patch("src.job_agent.tools.search_duckduckgo", return_value=many) as search:
        research = research_company("Acme", audit_logger=logger, max_results=3, snippet_chars=50)
    assert len(research.sources) == 3
    assert "x" * 51 not in research.summary
    assert search.call_args.kwargs["limit"] == 6  # headroom for filtered-out ads


def test_tool_failure_propagates_for_the_caller_to_handle(logger):
    with patch("src.job_agent.tools.search_duckduckgo", side_effect=ConnectionError("down")):
        with pytest.raises(ConnectionError):
            research_company("Acme", audit_logger=logger)


def test_no_results_exception_is_an_empty_result_not_a_failure(logger):
    with patch("src.job_agent.tools.DDGS") as ddgs:
        ddgs.return_value.__enter__.return_value.text.side_effect = DDGSException("No results found.")
        assert search_duckduckgo("zzz", audit_logger=logger) == []
        assert research_company("zzz", audit_logger=logger) is None
    trace = logger.trace_file.read_text()
    assert '"failure"' not in trace and '"success"' in trace


def test_other_ddgs_errors_still_raise(logger):
    with patch("src.job_agent.tools.DDGS") as ddgs:
        ddgs.return_value.__enter__.return_value.text.side_effect = DDGSException("Ratelimit exceeded")
        with pytest.raises(DDGSException):
            search_duckduckgo("zzz", audit_logger=logger)
