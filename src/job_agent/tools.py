import logging
from duckduckgo_search import DDGS
import requests
from .audit_logger import AuditLogger
from .retry import execute_with_retry

logger = logging.getLogger(__name__)

# Placeholder base URL for FreeHire
FREEHIRE_BASE_URL = "https://api.freehire.com/agent/jobs/search"

def search_freehire(
    query: str, 
    limit: int = 10, 
    audit_logger: AuditLogger = None,
    **kwargs
) -> list:
    def _call(**call_kwargs):
        params = {
            "q": call_kwargs["query"],
            "limit": call_kwargs["limit"],
            "description_format": "markdown",
            "posted_within_days": 30,
            "regions": "uk"
        }
        # Basic timeout added; Day 10 will enforce strict global timeouts
        response = requests.get(FREEHIRE_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("jobs", [])

    def _modify_freehire_kwargs(kwargs_dict, attempt):
        # Reduce limit on retry to prevent timeouts/payload issues
        current_limit = kwargs_dict.get("limit", 10)
        kwargs_dict["limit"] = max(1, current_limit // 2)
        return kwargs_dict

    call_kwargs = {"query": query, "limit": limit, **kwargs}
    
    return execute_with_retry(
        func=_call,
        args=(),
        kwargs=call_kwargs,
        audit_logger=audit_logger,
        tool_name="search_freehire",
        modify_kwargs_fn=_modify_freehire_kwargs
    )

def search_duckduckgo(
    query: str, 
    limit: int = 5, 
    audit_logger: AuditLogger = None,
    **kwargs
) -> list:
    def _call(**call_kwargs):
        with DDGS() as ddgs:
            results = list(ddgs.text(call_kwargs["query"], max_results=call_kwargs["limit"]))
            return results

    def _modify_ddg_kwargs(kwargs_dict, attempt):
        current_limit = kwargs_dict.get("limit", 5)
        kwargs_dict["limit"] = max(1, current_limit // 2)
        return kwargs_dict

    call_kwargs = {"query": query, "limit": limit, **kwargs}
    
    return execute_with_retry(
        func=_call,
        args=(),
        kwargs=call_kwargs,
        audit_logger=audit_logger,
        tool_name="search_duckduckgo",
        modify_kwargs_fn=_modify_ddg_kwargs
    )