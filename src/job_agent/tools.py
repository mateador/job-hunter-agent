import argparse
import json
import os
import re
import urllib.parse

import requests
from pydantic import BaseModel, Field, ValidationError

from job_agent.failures import classify_exception, FailureRecord

class FreeHireSearchInput(BaseModel):
    keywords: list[str] = Field(min_length=1, description="List of keywords to search for.")
    limit: int = Field(default=5, ge=1, le=20, description="Max jobs to return.")
    work_mode: str | None = Field(default=None, description="remote, hybrid, or onsite")
    seniority: str | None = Field(default=None, description="intern, junior, middle, senior, lead, staff, principal")
    regions: str | None = Field(default=None, description="global, north_america, latam, eu, uk, etc.")
    countries: str | None = Field(default=None, description="Country codes like UK, DE, BR")
    posted_within_days: int = Field(default=30, ge=1, le=365, description="Only return jobs posted in the last N days.")


class CompanyResearchInput(BaseModel):
    company_name: str = Field(min_length=2)
    max_results: int = Field(default=3, ge=1, le=5)
    industry_context: str | None = Field(default=None, description="Industry or tech stack to narrow the search (e.g. 'AI software')")


def _truncate(text: str | None, length: int = 500) -> str | None:
    if text is None:
        return None
    text = str(text).strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


def _extract_jobs(payload) -> list[dict]:
    candidates: list = []

    if payload is None:
        return []

    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        for key in ("jobs", "results", "data", "items", "listings"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
        
        if not candidates and ("company" in payload or "title" in payload):
            candidates = [payload]

    jobs = []
    for item in candidates:
        if not isinstance(item, dict):
            continue

        company = item.get("company_name") or item.get("company") or "Unknown company"
        position = item.get("title") or item.get("position") or "Unknown position"
        description = item.get("description") or item.get("snippet") or ""
        
        raw_job_id = item.get("id") or item.get("job_id") or item.get("slug") or item.get("jid")
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
    posted_within_days: int = 30
) -> dict:
    try:
        args = FreeHireSearchInput(
            keywords=keywords, limit=limit, work_mode=work_mode,
            seniority=seniority, regions=regions, countries=countries,
            posted_within_days=posted_within_days
        )
    except ValidationError as exc:
        return {"status": "error", "tool": "search_freehire_jobs", "message": "Invalid input.", "details": exc.errors()}

    url = os.getenv("FREEHIRE_SEARCH_URL", "https://freehire.me/api/v1/agent/jobs/search")
    
    # GUARDRAIL 1: Geography Default
    if not args.regions and not args.countries:
        args.regions = "uk"

    params = {
        "q": ", ".join(args.keywords),
        "limit": args.limit,
        "description_format": os.getenv("FREEHIRE_DESCRIPTION_FORMAT", "markdown"),
        "posted_within_days": args.posted_within_days
    }

    if args.work_mode: params["work_mode"] = args.work_mode
    if args.seniority: params["seniority"] = args.seniority
    if args.regions: params["regions"] = args.regions
    if args.countries: params["countries"] = args.countries

    headers = {"Accept": "application/json", "User-Agent": "job-hunter-agent/0.3.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        if not response.ok:
            return {"status": "error", "tool": "search_freehire_jobs", "message": f"API returned {response.status_code}", "details": response.text[:500]}

        payload = response.json()
        jobs = _extract_jobs(payload)

        return {
            "status": "success", "tool": "search_freehire_jobs",
            "query_keywords": args.keywords,
            "filters_applied": {"work_mode": args.work_mode, "seniority": args.seniority, "regions": args.regions, "posted_within_days": args.posted_within_days},
            "jobs_returned": len(jobs), "jobs": jobs
        }
    except Exception as exc:
        failure = classify_exception(exc, source="search_freehire_jobs")
        return {
            "status": "error",
            "tool": "search_freehire_jobs",
            "message": failure.message,
            "failure_category": failure.category.value,
            "retry_policy": failure.retry_policy.value,
            "is_recoverable": failure.is_recoverable,
            "details": str(exc),
        }


def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

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


def research_company(company_name: str, max_results: int = 3, industry_context: str | None = None) -> dict:
    try:
        args = CompanyResearchInput(company_name=company_name, max_results=max_results, industry_context=industry_context)
    except ValidationError as exc:
        return {"status": "error", "tool": "research_company", "message": "Invalid input.", "details": exc.errors()}

    # GUARDRAIL 3: Contextual Research
    context = args.industry_context or "software technology"
    query = f"{args.company_name} company {context} engineering culture news careers"

    try:
        results = _search_duckduckgo(query, args.max_results)
        if results:
            return {"status": "success", "tool": "research_company", "source": "duckduckgo", "company_name": args.company_name, "results_returned": len(results), "results": results}
    except Exception as exc:
        failure = classify_exception(exc, source="research_company")
        return {
            "status": "error",
            "tool": "research_company",
            "message": failure.message,
            "failure_category": failure.category.value,
            "retry_policy": failure.retry_policy.value,
            "is_recoverable": failure.is_recoverable,
            "details": str(exc),
        }

    return {"status": "error", "tool": "research_company", "message": f"No research found for: {args.company_name}"}


def execute_tool(tool_name: str, tool_arguments: dict) -> dict:
    try:
        if tool_name == "search_freehire_jobs": return search_freehire_jobs(**tool_arguments)
        if tool_name == "research_company": return research_company(**tool_arguments)
        return {"status": "error", "tool": tool_name, "message": f"Unknown tool: {tool_name}"}
    except TypeError as exc:
        return {"status": "error", "tool": tool_name, "message": "Invalid tool arguments.", "details": str(exc)}
    except Exception as exc:
        failure = classify_exception(exc, source=f"execute_tool:{tool_name}")
        return {
            "status": "error",
            "tool": tool_name,
            "message": failure.message,
            "failure_category": failure.category.value,
            "retry_policy": failure.retry_policy.value,
            "is_recoverable": failure.is_recoverable,
            "details": str(exc),
        }

def _cli() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Day 3 tools.")
    parser.add_argument("--keywords", nargs="+", help="Keywords for FreeHire.")
    parser.add_argument("--company", help="Company name to research.")
    parser.add_argument("--context", help="Industry context for company research.")
    args = parser.parse_args()

    if args.keywords:
        print(json.dumps(search_freehire_jobs(keywords=args.keywords), ensure_ascii=False, indent=2))
    if args.company:
        print(json.dumps(research_company(company_name=args.company, industry_context=args.context), ensure_ascii=False, indent=2))
    if not args.keywords and not args.company:
        parser.print_help()

if __name__ == "__main__":
    _cli()
    