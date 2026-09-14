"""
Day 13: Application generator with audit trail integration.
Bridges Week 1 logic with Day 9-13 architecture.
"""
import json
from typing import Optional

from rich.console import Console

from .llm_client import LLMClient
from .audit_logger import AuditLogger
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


def generate_application(
    job: Job,
    llm_client: LLMClient,
    audit_logger: AuditLogger,
    company_research: Optional[CompanyResearch] = None,
    candidate_profile: Optional[JobCandidate] = None,
) -> Application:
    """
    Day 13: Generate a tailored cover letter and CV bullets for one specific job.
    
    This integrates with the audit trail and uses the injected LLMClient.
    
    Args:
        job: Job listing from FreeHire
        llm_client: LLM client with audit integration
        audit_logger: Audit logger for tracking
        company_research: Optional company research data
        candidate_profile: Optional candidate profile (uses defaults if not provided)
    
    Returns:
        Application object with cover_letter and cv_bullets
    """
    # Use default candidate profile if not provided
    if candidate_profile is None:
        candidate_profile = JobCandidate()
    
    # Build research context
    research_context = "No company research available."
    if company_research:
        if hasattr(company_research, 'summary') and company_research.summary:
            research_context = company_research.summary
            if hasattr(company_research, 'sources') and company_research.sources:
                research_context += f"\nSources: {', '.join(company_research.sources[:3])}"
        else:
            # Fallback for older CompanyResearch model
            research_parts = []
            if company_research.industry:
                research_parts.append(f"Industry: {company_research.industry}")
            if company_research.mission:
                research_parts.append(f"Mission: {company_research.mission}")
            if company_research.culture:
                research_parts.append(f"Culture: {company_research.culture}")
            research_context = "\n".join(research_parts) if research_parts else "Limited company information available."
    
    # Build candidate evidence
    evidence_text = "\n".join(f"- {e}" for e in candidate_profile.skills[:5])
    
    # Build prompt
    prompt = f"""You are a professional career coach and technical writer.

Generate a tailored job application package for the following role.

CANDIDATE PROFILE:
Name: {candidate_profile.name}
Experience: {candidate_profile.years_experience} years
Current Role: {candidate_profile.current_role}
Key Skills: {', '.join(candidate_profile.skills)}
Background: {candidate_profile.background}

TARGET JOB:
Company: {job.company}
Position: {job.title}
Location: {job.location or 'Not specified'}
Job Description: {job.description or 'No detailed description available.'}

COMPANY RESEARCH:
{research_context}

TASK:
Generate two things:

1. TAILORED CV BULLETS: Create 3-4 bullet points that highlight the candidate's most relevant experience for this specific role. Use strong action verbs and quantify results where possible. Focus on skills that match the job requirements.

2. COVER LETTER: Write a concise, professional cover letter (3-4 paragraphs) that:
- Opens with genuine enthusiasm for the specific role and company
- Connects 2-3 specific accomplishments to the job requirements
- Addresses any potential concerns honestly (e.g., location, visa status)
- Closes with a clear call to action

IMPORTANT RULES:
- If the company appears to be a recruitment agency (e.g., Ocho, Corriculo, Hays, Michael Page), address the letter to the recruitment consultant and reference the end-client role described in the job posting.
- Do NOT invent skills, companies, or experience not present in the candidate profile.
- Keep the tone professional but authentic, not generic or overly formal.
- The candidate is based in Cambridge, UK, and holds a Skilled Worker Visa Dependant (no sponsorship required).

Respond with valid JSON only, no Markdown, no code fences:
{{
  "tailored_cv_bullets": ["bullet 1", "bullet 2", "bullet 3"],
  "cover_letter": "Full cover letter text with paragraph breaks using \\n\\n"
}}"""

    try:
        # Log the generation attempt
        audit_logger.log_event(
            event_type="application_generation_start",
            job_id=job.id,
            company=job.company
        )
        
        # Call LLM with audit integration
        response = llm_client.chat([
            {"role": "system", "content": "You are a professional career coach. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ])

        text = _strip_code_fences(response)
        result = json.loads(text)

        # Validate and extract fields
        cv_bullets = result.get("tailored_cv_bullets", [])
        cover_letter = result.get("cover_letter", text)
        
        if not cv_bullets:
            cv_bullets = []
        if not cover_letter:
            cover_letter = "Cover letter generation failed."

        # Log success
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
        raise  # Re-raise so agent_runner can catch and track it