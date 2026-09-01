import json
from textwrap import dedent


SYSTEM_PROMPT = dedent(
    """
    You are a job research and application preparation agent.

    Your long-term purpose is to help a candidate:
    - search for relevant jobs,
    - compare jobs against their CV,
    - explain why they are a good match,
    - prepare tailored CV and cover letter drafts.

    You are currently in Day 2 of implementation.

    You have access to two tools:

    1. search_freehire_jobs
       Purpose: Search for jobs from the FreeHire API.
       Input shape:
       {
         "keywords": ["Python", "Software Engineer"],
         "limit": 5,
         "work_mode": "remote" (optional: remote, hybrid, onsite),
         "seniority": "senior" (optional: junior, middle, senior, lead),
         "regions": "eu" (optional: global, north_america, latam, eu, etc.)
       }
       Output: A JSON object containing normalized job results with full Markdown descriptions.

    2. research_company
       Purpose: Search the public web for information about a company.
       Input shape:
       {
         "company_name": "Acme Corp",
         "max_results": 3
       }
       Output: A JSON object containing search results about the company.

    Your workflow should be:
    Step 1: Call search_freehire_jobs using the candidate keywords.
    Step 2: Review the returned jobs. Select up to 2 promising jobs based on the CV.
    Step 3: For each selected company, call research_company once.
    Step 4: When you have enough information, return final_answer.

    You must always respond with valid JSON only. No Markdown, no code fences.

    Your JSON response must follow this exact shape:
    {
      "reasoning_summary": "brief explanation",
      "next_action": "tool_call" or "final_answer",
      "message_to_user": "brief message",
      "tool_name": null or "search_freehire_jobs" or "research_company",
      "tool_arguments": null or {},
      "final_answer": null or {
        "summary": "short summary",
        "jobs_reviewed": 0,
        "selected_jobs": [
          {"job_id": null, "company": "Name", "position": "Role", "url": null, "location": null, "snippet": null, "match_reason": "Why"}
        ],
        "company_research": [
          {"company": "Name", "summary": "Research", "sources": ["url"]}
        ],
        "recommended_next_steps": ["step 1"]
      }
    }
    """
).strip()


def build_initial_user_prompt(cv_text: str, keywords: list[str]) -> str:
    keywords_text = ", ".join(keywords)
    return dedent(
        f"""
        Candidate CV:
        {cv_text}

        Target job search keywords:
        {keywords_text}

        Task:
        Use the available tools to search for jobs that may match this CV.
        Then research only the most promising companies.
        Finally, produce a structured Day 2 summary.

        Start by calling search_freehire_jobs.
        """
    ).strip()


def build_json_repair_prompt(raw_response: str, error: str) -> str:
    return dedent(
        f"""
        Your previous response could not be parsed as the required JSON schema.
        Error: {error}
        Previous response: {raw_response}
        Please return a corrected JSON response only. No Markdown. No code fences.
        """
    ).strip()


def build_tool_result_prompt(tool_name: str, tool_arguments: dict, tool_result: dict) -> str:
    tool_arguments_text = json.dumps(tool_arguments, ensure_ascii=False, indent=2)
    tool_result_text = json.dumps(tool_result, ensure_ascii=False, indent=2)

    if len(tool_result_text) > 20000:
        tool_result_text = tool_result_text[:20000] + "\n...TRUNCATED..."

    return dedent(
        f"""
        Tool result for: {tool_name}
        Arguments used: {tool_arguments_text}
        Result: {tool_result_text}

        Use this information to continue the workflow.
        If you need another tool call, return next_action as "tool_call".
        If you have enough information, return next_action as "final_answer".
        """
    ).strip()