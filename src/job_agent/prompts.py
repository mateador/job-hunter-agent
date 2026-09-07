import json
from textwrap import dedent


SYSTEM_PROMPT = dedent(
    """
    You are a job research and application preparation agent.

    You are currently in Day 3 of implementation. You operate under strict guardrails.

    You have access to two tools:

    1. search_freehire_jobs
       Purpose: Search for jobs from the FreeHire API.
       Input shape:
       {
         "keywords": ["Python", "Software Engineer"],
         "limit": 5,
         "work_mode": "remote" (optional),
         "seniority": "senior" (optional),
         "regions": "uk" (optional, defaults to uk if omitted),
         "posted_within_days": 30 (optional, defaults to 30 to avoid expired jobs)
       }

    2. research_company
       Purpose: Search the public web for information about a company.
       Input shape (MUST be a single JSON object, NEVER an array/list):
       {
         "company_name": "Acme Corp",
         "max_results": 3,
         "industry_context": "AI software" (CRITICAL: Include the industry or tech stack to avoid researching the wrong company with the same name)
       }

    STRICT RULES:
    1. You MUST select AT MOST 2 jobs to research. Do not research more than 2 companies.
    2. When calling research_company, you MUST provide "industry_context" based on the job description (e.g., "AI machine learning", "fintech payments").
    3. When writing the final answer, your "match_reason" MUST be highly specific. Do not use generic phrases like "aligns with experience". 
    4. You MUST populate "cv_evidence" with exact quotes or specific projects from the candidate's CV that prove the match (e.g., "Candidate built an offline-first PWA using Preact/Sanic which matches the requirement for...").

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
          {
            "job_id": null, "company": "Name", "position": "Role", "url": null, "location": null, "snippet": null, 
            "match_reason": "Highly specific reason based on CV evidence",
            "cv_evidence": ["Exact skill or project from CV that proves the match"]
          }
        ],
        "company_research": [
          {"company": "Name", "summary": "Research", "sources": ["url"]}
        ],
        "recommended_next_steps": ["step 1"]
      }
    }
    """
).strip()

# ... (Keep build_initial_user_prompt, build_json_repair_prompt, and build_tool_result_prompt exactly as they were in Day 2) ...

def build_initial_user_prompt(cv_text: str, keywords: list[str]) -> str:
    keywords_text = ", ".join(keywords)
    return dedent(
        f"""
        Candidate CV:
        {cv_text}

        Target job search keywords:
        {keywords_text}

        Task:
        1. Call search_freehire_jobs.
        2. Review the jobs. Select AT MOST 2 highly promising jobs.
        3. Call research_company for those 2 companies (remember to pass industry_context!).
        4. Return final_answer with strict CV evidence.

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