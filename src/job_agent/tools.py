"""
Day 15: Tools with correct FreeHire API endpoint.
"""
import logging
import os
from ddgs import DDGS
import requests
from .audit_logger import AuditLogger
from .retry import execute_with_retry
from .config import FREEHIRE_TIMEOUT, DUCKDUCKGO_TIMEOUT

logger = logging.getLogger(__name__)

# FreeHire agent search endpoint. The generic /api/v1/jobs endpoint silently
# ignores `q` and returns an unfiltered feed, so never default to it.
FREEHIRE_BASE_URL = "https://freehire.me/api/v1/agent/jobs/search"


class FreeHireIgnoredParamError(Exception):
    """FreeHire reported that it ignored a parameter the search depends on."""


def _freehire_settings() -> dict:
    """Read FREEHIRE_* settings at call time so a late-loaded .env is honoured."""
    return {
        "url": os.getenv("FREEHIRE_SEARCH_URL") or FREEHIRE_BASE_URL,
        "query_param": os.getenv("FREEHIRE_QUERY_PARAM") or "q",
        "limit_param": os.getenv("FREEHIRE_LIMIT_PARAM") or "limit",
        "description_format": os.getenv("FREEHIRE_DESCRIPTION_FORMAT") or "markdown",
    }


def search_freehire(
    query: str, 
    limit: int = 10, 
    audit_logger: AuditLogger = None,
    **kwargs
) -> list:
    def _call(**call_kwargs):
        cfg = _freehire_settings()
        params = {
            cfg["query_param"]: call_kwargs["query"],
            cfg["limit_param"]: call_kwargs["limit"],
            "description_format": cfg["description_format"],
            "posted_within_days": 30,
            "regions": "uk"
        }
        # Remove any None values just in case
        params = {k: v for k, v in params.items() if v is not None}

        response = requests.get(
            cfg["url"],
            params=params,
            timeout=FREEHIRE_TIMEOUT
        )
        response.raise_for_status()

        # The FreeHire API returns results inside a "data" key
        payload = response.json()
        meta = payload.get("meta") or {}
        ignored = [p.get("param") for p in meta.get("ignored_params") or []]
        if audit_logger:
            audit_logger.log_event(
                event_type="search_meta",
                total=meta.get("total"),
                ignored_params=ignored,
            )
        if cfg["query_param"] in ignored:
            raise FreeHireIgnoredParamError(
                f"FreeHire ignored the query parameter '{cfg['query_param']}' at {cfg['url']}; "
                f"results would be unrelated to '{call_kwargs['query']}'."
            )
        return payload.get("data", [])

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
        with DDGS(timeout=DUCKDUCKGO_TIMEOUT) as ddgs:
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