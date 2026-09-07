import argparse
import json
import os
import re
import urllib.parse

import requests
from pydantic import BaseModel, Field, ValidationError


class FreeHireSearchInput(BaseModel):
    """
    Input schema for the FreeHire agent search endpoint.
    """
    keywords: list[str] = Field(min_length=1, description="List of keywords to search for.")
    limit: int = Field(default=5, ge=1, le=20, description="Max jobs to return.")
    
    # Optional facets the agent can use to narrow down the search
    work_mode: str | None = Field(default=None, description="remote, hybrid, or onsite")
    seniority: str | None = Field(default=None, description="intern, junior, middle, senior, lead, staff, principal")
    regions: str | None = Field(default=None, description="global, north_america, latam, eu, etc.")
    countries: str | None = Field(default=None, description="uk, etc.")


class CompanyResearchInput(BaseModel):
    company_name: str = Field(min_length=2)
    max_results: int = Field(default=3, ge=1, le=5)


def _truncate(text: str | None, length: int = 500) -> str | None:
    if text is None:
        return None
    text = str(text).strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


def _extract_jobs(payload) -> list[dict]:
    """
    Normalize the FreeHire response.
    Based on standard REST practices, it likely returns a list or an object with a 'jobs'/'results' key.
    """
    candidates: list = []

    if payload is None:
        return []

    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        # Check common wrapper keys
        for key in ("jobs", "results", "data", "items", "listings"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
        
        # If no wrapper found, maybe the dict itself is a single job (unlikely for search, but safe)
        if not candidates and ("company" in payload or "title" in payload):
            candidates = [payload]

    jobs = []
    for item in candidates:
        if not isinstance(item, dict):
            continue

        company = item.get("company_name") or item.get("company") or "Unknown company"
        position = item.get("title") or item.get("position") or "Unknown position"
        
        # The agent endpoint provides the full description!
        description = item.get("description") or item.get("snippet") or ""

        # 1. Try to find the ID (added 'jid' as FreeHire might use that)
        raw_job_id = item.get("id") or item.get("job_id") or item.get("slug") or item.get("jid")
        
        # 2. Only convert to string if it actually exists, otherwise leave as Python None (JSON null)
        job_id = str(raw_job_id) if raw_job_id else None
        
        jobs.append(
            {
                "job_id": job_id,
                "company": str(company),
                "position": str(position),
                "url": item.get("url") or item.get("apply_url"),
                "location": item.get("location") or item.get("countries") or item.get("regions"),
                "work_mode": item.get("work_mode"),
                "seniority": item.get("seniority"),
                # Keep description manageable for the context window, but longer than a snippet
                "description": _truncate(description, 1500), 
            }
        )

    return jobs


def search_freehire_jobs(
    keywords: list[str],
    limit: int = 5,
    work_mode: str | None = None,
    seniority: str | None = None,
    regions: str | None = None,
    countries: str | None = None,
) -> dict:
    """
    Call the FreeHire /agent/jobs/search API.
    """
    try:
        args = FreeHireSearchInput(
            keywords=keywords, 
            limit=limit, 
            work_mode=work_mode,
            seniority=seniority,
            regions=regions
        )
    except ValidationError as exc:
        return {
            "status": "error",
            "tool": "search_freehire_jobs",
            "message": "Invalid input for FreeHire job search.",
            "details": exc.errors(),
        }

    url = os.getenv("FREEHIRE_SEARCH_URL", "https://freehire.me/api/v1/agent/jobs/search")
    
    # Build query parameters
    params = {
        "q": ", ".join(args.keywords),
        "limit": args.limit,
        "description_format": os.getenv("FREEHIRE_DESCRIPTION_FORMAT", "markdown")
    }

    # Add optional facets if the agent provided them
    if args.work_mode:
        params["work_mode"] = args.work_mode
    if args.seniority:
        params["seniority"] = args.seniority
    if args.regions:
        params["regions"] = args.regions
    if args.countries:
        params["countries"] = args.countries

    headers = {
        "Accept": "application/json",
        "User-Agent": "job-hunter-agent/0.2.0",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        
        if not response.ok:
            return {
                "status": "error",
                "tool": "search_freehire_jobs",
                "message": f"FreeHire API returned status {response.status_code}",
                "details": response.text[:500]
            }

        payload = response.json()
        jobs = _extract_jobs(payload)

        return {
            "status": "success",
            "tool": "search_freehire_jobs",
            "query_keywords": args.keywords,
            "filters_applied": {
                "work_mode": args.work_mode,
                "seniority": args.seniority,
                "regions": args.regions
            },
            "jobs_returned": len(jobs),
            "jobs": jobs
        }

    except requests.RequestException as exc:
        return {
            "status": "error",
            "tool": "search_freehire_jobs",
            "message": "FreeHire job search network failure.",
            "details": str(exc),
        }
    except ValueError:
        return {
            "status": "error",
            "tool": "search_freehire_jobs",
            "message": "FreeHire returned invalid JSON.",
            "raw_text": response.text[:500]
        }


def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    # Try the new package name first
    try:
        from ddgs import DDGS
    except ImportError:
        # Fallback to the old package name if it's still installed
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:
            raise RuntimeError(
                "Could not import DuckDuckGo search library. "
                "Please run: pip install ddgs"
            ) from exc

    results = []

    with DDGS() as ddgs:
        raw_results = list(ddgs.text(query, max_results=max_results))

    for item in raw_results:
        results.append({
            "title": item.get("title"),
            "url": item.get("href") or item.get("url"),
            "snippet": _truncate(item.get("body") or item.get("snippet"), 300),
        })
    return results


def research_company(company_name: str, max_results: int = 3) -> dict:
    """
    Research a company using DuckDuckGo.
    """
    try:
        args = CompanyResearchInput(company_name=company_name, max_results=max_results)
    except ValidationError as exc:
        return {
            "status": "error",
            "tool": "research_company",
            "message": "Invalid input for company research.",
            "details": exc.errors(),
        }

    query = f"{args.company_name} company engineering culture news careers"

    try:
        results = _search_duckduckgo(query, args.max_results)
        if results:
            return {
                "status": "success",
                "tool": "research_company",
                "source": "duckduckgo",
                "company_name": args.company_name,
                "results_returned": len(results),
                "results": results,
            }
    except Exception as exc:
        return {
            "status": "error",
            "tool": "research_company",
            "message": f"DuckDuckGo search failed: {exc}",
        }

    return {
        "status": "error",
        "tool": "research_company",
        "message": f"Could not find research for company: {args.company_name}",
    }


def execute_tool(tool_name: str, tool_arguments: dict) -> dict:
    """
    Central tool execution entrypoint.
    """
    try:
        if tool_name == "search_freehire_jobs":
            return search_freehire_jobs(**tool_arguments)

        if tool_name == "research_company":
            return research_company(**tool_arguments)

        return {
            "status": "error",
            "tool": tool_name,
            "message": f"Unknown tool: {tool_name}",
        }

    except TypeError as exc:
        return {
            "status": "error",
            "tool": tool_name,
            "message": "Invalid tool arguments.",
            "details": str(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "tool": tool_name,
            "message": "Unexpected tool execution failure.",
            "details": str(exc),
        }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Day 2 tools.")
    parser.add_argument("--keywords", nargs="+", help="Keywords for FreeHire.")
    parser.add_argument("--company", help="Company name to research.")
    parser.add_argument("--remote", action="store_true", help="Filter for remote jobs.")
    parser.add_argument("--region", help="Filter by region (e.g. uk, eu, global, north_america).")
    parser.add_argument("--country", help="Filter by country code (e.g. UK, DE, BR).")
    parser.add_argument("--seniority", help="Filter by seniority (e.g. senior, lead, middle).")

    args = parser.parse_args()

    if args.keywords:
        work_mode = "remote" if args.remote else None
        result = search_freehire_jobs(
            keywords=args.keywords,
            work_mode=work_mode,
            regions=args.region,
            countries=args.country,
            seniority=args.seniority,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.company:
        result = research_company(company_name=args.company)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if not args.keywords and not args.company:
        parser.print_help()


if __name__ == "__main__":
    _cli()