from textwrap import dedent


SYSTEM_PROMPT = dedent(
    """
    You are a job research and application preparation agent.

    Your long-term purpose is to help a candidate:
    - search for relevant jobs,
    - compare jobs against their CV,
    - explain why they are a good match,
    - prepare tailored CV and cover letter drafts.

    Today is Day 1 of implementation.

    Important:
    - You do not have tools yet.
    - You cannot search the web.
    - You cannot call job APIs yet.
    - Your job today is only to inspect the provided CV and keywords,
      understand the target workflow, and decide whether you have enough
      information to produce a Day 1 readiness summary.

    You must always respond with valid JSON only.

    Your JSON response must follow this exact shape:

    {
      "reasoning_summary": "brief explanation of what you are doing",
      "next_action": "continue" or "final_answer",
      "message_to_user": "brief user-facing message",
      "final_answer": null or {
        "summary": "short summary",
        "recommended_next_steps": [
          "step one",
          "step two"
        ]
      }
    }

    Rules:
    - Do not include Markdown.
    - Do not include code fences.
    - Do not include text outside the JSON object.
    - If you provide final_answer, next_action must be "final_answer".
    - If next_action is "continue", final_answer must be null.
    - Keep the answer concise.
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
        Review the CV and keywords. Since tools are not available yet,
        produce a Day 1 readiness summary explaining what the agent can
        already infer and what should be implemented next.

        If you have enough information, return next_action as "final_answer".
        """
    ).strip()


def build_json_repair_prompt(raw_response: str, error: str) -> str:
    return dedent(
        f"""
        Your previous response could not be parsed as the required JSON schema.

        Parsing/validation error:
        {error}

        Previous response:
        {raw_response}

        Please return a corrected JSON response only.
        No Markdown.
        No code fences.
        No text outside the JSON object.
        """
    ).strip()