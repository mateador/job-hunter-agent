import json

from rich.console import Console

from job_agent.llm_client import LLMClient
from job_agent.models import CompanyResearch, JobCandidate

console = Console()


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def generate_application_package(
    cv_text: str,
    job: JobCandidate,
    company_research: CompanyResearch | None,
) -> dict:
    """
    Day 6: Generate a tailored cover letter and CV bullets for one specific job.

    This runs AFTER the agent loop completes, so it gets its own clean
    context window focused entirely on writing quality.
    """

    llm = LLMClient()

    research_context = "No company research available."
    if company_research:
        research_context = company_research.summary
        if company_research.sources:
            research_context += f"\nSources: {', '.join(company_research.sources[:3])}"

    evidence_text = "\n".join(f"- {e}" for e in job.cv_evidence) if job.cv_evidence else "No specific evidence provided."

    prompt = f"""You are a professional career coach and technical writer.

Generate a tailored job application package for the following role.

CANDIDATE CV:
{cv_text}

TARGET JOB:
Company: {job.company}
Position: {job.position}
Location: {job.location}
Job Description: {job.snippet}

COMPANY RESEARCH:
{research_context}

MATCH ANALYSIS:
{job.match_reason}

CV EVIDENCE:
{evidence_text}

TASK:
Generate two things:

1. TAILORED CV BULLETS: Rewrite 3-4 bullet points from the candidate's CV specifically tailored to this job. Use the same real accomplishments but reframe them to match the job's requirements. Use strong action verbs and quantified results. Do NOT invent experience.

2. COVER LETTER: Write a concise, professional cover letter (3-4 paragraphs) that:
- Opens with genuine enthusiasm for the specific role and company
- Connects 2-3 specific CV accomplishments to the job requirements
- Addresses any potential concerns honestly (e.g., career transitions, location)
- Closes with a clear call to action

IMPORTANT RULES:
- If the company appears to be a recruitment agency (e.g., Ocho, Corriculo, Hays, Michael Page), address the letter to the recruitment consultant and reference the end-client role described in the job posting.
- Do NOT invent skills, companies, or experience not present in the CV.
- Keep the tone professional but authentic, not generic or overly formal.
- The candidate is based in Cambridge, UK, and holds a Skilled Worker Visa Dependant (no sponsorship required).

Respond with valid JSON only, no Markdown, no code fences:
{{
  "tailored_cv_bullets": ["bullet 1", "bullet 2", "bullet 3"],
  "cover_letter": "Full cover letter text with paragraph breaks using \\n\\n"
}}"""

    try:
        response = llm.complete([
            {"role": "system", "content": "You are a professional career coach. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ])

        text = _strip_code_fences(response)
        result = json.loads(text)

        # Validate expected keys
        if "tailored_cv_bullets" not in result:
            result["tailored_cv_bullets"] = []
        if "cover_letter" not in result:
            result["cover_letter"] = text

        return result

    except json.JSONDecodeError:
        console.print(f"[yellow]⚠️ Could not parse application JSON for {job.company}. Using raw text.[/yellow]")
        return {
            "tailored_cv_bullets": [],
            "cover_letter": response if 'response' in dir() else "Generation failed.",
        }
    except Exception as exc:
        console.print(f"[red]✗ Application generation failed for {job.company}: {exc}[/red]")
        return {
            "tailored_cv_bullets": [],
            "cover_letter": f"Generation failed: {exc}",
        }
