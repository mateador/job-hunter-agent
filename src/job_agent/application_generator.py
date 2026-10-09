"""
Day 15: Application generator with CV text support.
Uses raw CV text when available, falls back to candidate profile otherwise.
"""
import json
from typing import Optional

from rich.console import Console

from .llm_client import LLMClient
from .audit_logger import AuditLogger
from .format_rules import MAX_BULLETS, MIN_BULLETS, PROMPT_BULLET_CHARS, PROMPT_MAX_WORDS, PROMPT_MIN_WORDS
from .models import Job, Application, CompanyResearch, JobCandidate

console = Console()


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _build_candidate_section(cv_text: Optional[str], candidate_profile: Optional[JobCandidate]) -> str:
    """Build the candidate section of the prompt from either CV text or profile."""
    if cv_text:
        return f"CANDIDATE CV (verbatim):\n{cv_text}"

    if candidate_profile is None:
        candidate_profile = JobCandidate()

    return (
        f"CANDIDATE PROFILE:\n"
        f"Name: {candidate_profile.name}\n"
        f"Experience: {candidate_profile.years_experience} years\n"
        f"Current Role: {candidate_profile.current_role}\n"
        f"Key Skills: {', '.join(candidate_profile.skills)}\n"
        f"Background: {candidate_profile.background}"
    )


def generate_application(
    job: Job,
    llm_client: LLMClient,
    audit_logger: AuditLogger,
    cv_text: Optional[str] = None,
    company_research: Optional[CompanyResearch] = None,
    candidate_profile: Optional[JobCandidate] = None,
    revision_note: Optional[str] = None,
) -> Application:
    """
    Generate a tailored cover letter and CV bullets for one specific job.

    Args:
        job: Job listing from FreeHire
        llm_client: LLM client with audit integration
        audit_logger: Audit logger for tracking
        cv_text: Optional raw CV text (takes priority over candidate_profile)
        company_research: Optional company research data
        candidate_profile: Optional candidate profile (used if cv_text not provided)
        revision_note: Optional feedback on a previous draft, appended to the prompt

    Returns:
        Application object with cover_letter and cv_bullets
    """
    candidate_section = _build_candidate_section(cv_text, candidate_profile)

    # Build research context
    research_context = "No company research available."
    if company_research:
        if hasattr(company_research, 'summary') and company_research.summary:
            research_context = company_research.summary
            if hasattr(company_research, 'sources') and company_research.sources:
                research_context += f"\nSources: {', '.join(company_research.sources[:3])}"
        else:
            research_parts = []
            if company_research.industry:
                research_parts.append(f"Industry: {company_research.industry}")
            if company_research.mission:
                research_parts.append(f"Mission: {company_research.mission}")
            if company_research.culture:
                research_parts.append(f"Culture: {company_research.culture}")
            research_context = "\n".join(research_parts) if research_parts else "Limited company information available."

    revision_section = f"\nREVISION REQUIRED:\n{revision_note}\n" if revision_note else ""

    prompt = f"""You are a professional career coach and technical writer.

Generate a tailored job application package for the following role.

{candidate_section}

TARGET JOB:
Company: {job.company}
Position: {job.title}
Location: {job.location or 'Not specified'}
Job Description: {job.description or 'No detailed description available.'}

COMPANY RESEARCH:
{research_context}

TASK:
Generate two things:

1. TAILORED CV BULLETS: Create {MIN_BULLETS}-{MAX_BULLETS} bullet points, each one sentence of at most {PROMPT_BULLET_CHARS} characters, that highlight the candidate's most relevant experience for this specific role. Use strong action verbs and quantify results where possible. Focus on skills that match the job requirements. If a real CV was provided, draw directly from it — do NOT invent experience.

2. COVER LETTER: Write a professional cover letter (3-4 paragraphs, {PROMPT_MIN_WORDS}-{PROMPT_MAX_WORDS} words in total including the greeting and sign-off) that:
- Opens with genuine enthusiasm for the specific role and company
- Connects 2-3 specific accomplishments to the job requirements
- Addresses any potential concerns honestly (e.g., location, visa status)
- Closes with a clear call to action

IMPORTANT RULES:
- If the company appears to be a recruitment agency (e.g., Ocho, Corriculo, Hays, Michael Page), address the letter to the recruitment consultant and reference the end-client role described in the job posting.
- Do NOT invent skills, companies, or experience not present in the candidate's CV or profile.
- Only state facts about the hiring company that appear in the job description or the company research above.
- Keep the tone professional but authentic, not generic or overly formal.
- The candidate is based in Cambridge, UK, and holds a Skilled Worker Visa Dependant (no sponsorship required).
{revision_section}
Respond with valid JSON only, no Markdown, no code fences:
{{
  "tailored_cv_bullets": ["bullet 1", "bullet 2", "bullet 3"],
  "cover_letter": "Full cover letter text with paragraph breaks using \\n\\n"
}}"""

    try:
        audit_logger.log_event(
            event_type="application_generation_start",
            job_id=job.id,
            company=job.company,
            has_cv_text=cv_text is not None
        )

        response = llm_client.chat([
            {"role": "system", "content": "You are a professional career coach. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ])

        text = _strip_code_fences(response)
        result = json.loads(text)

        cv_bullets = result.get("tailored_cv_bullets", [])
        cover_letter = result.get("cover_letter", text)

        if not cv_bullets:
            cv_bullets = []
        if not cover_letter:
            cover_letter = "Cover letter generation failed."

        audit_logger.log_event(
            event_type="application_generation_success",
            job_id=job.id,
            company=job.company,
            bullets_count=len(cv_bullets)
        )

        return Application(
            job_id=job.id,
            cover_letter=cover_letter,
            cv_bullets=cv_bullets
        )

    except json.JSONDecodeError as e:
        audit_logger.log_event(
            event_type="application_generation_failed",
            job_id=job.id,
            company=job.company,
            error="JSON decode error",
            details=str(e)
        )
        console.print(f"[yellow]⚠️ Could not parse application JSON for {job.company}. Using raw text.[/yellow]")
        return Application(
            job_id=job.id,
            cover_letter=response if 'response' in dir() else "Generation failed.",
            cv_bullets=[]
        )
    except Exception as exc:
        audit_logger.log_event(
            event_type="application_generation_failed",
            job_id=job.id,
            company=job.company,
            error=str(exc)
        )
        console.print(f"[red]✗ Application generation failed for {job.company}: {exc}[/red]")
        raise