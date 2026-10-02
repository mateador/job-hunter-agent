"""
Day 13: Pydantic models for agent data structures.
Includes Week 1 models + Day 13 additions.
"""
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Any


# ── Week 1 Models (used by application_generator.py) ──

class CompanyResearch(BaseModel):
    """Research data about a company from DuckDuckGo."""
    company_name: str
    industry: Optional[str] = None
    mission: Optional[str] = None
    culture: Optional[str] = None
    recent_news: Optional[str] = None
    key_products: Optional[str] = None
    values: Optional[str] = None


class JobCandidate(BaseModel):
    """Candidate profile for tailoring applications."""
    name: str = "Candidate"
    years_experience: int = 5
    current_role: str = "Software Engineer"
    skills: List[str] = Field(default_factory=lambda: [
        "Python", "TypeScript", "AWS", "Docker", "Kubernetes"
    ])
    background: str = "Experienced software engineer with expertise in building scalable systems."
    education: Optional[str] = None
    certifications: List[str] = Field(default_factory=list)


# ── Day 1-7 Models ──

class Job(BaseModel):
    """Job listing from FreeHire API."""
    id: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    posted_date: Optional[str] = None
    salary: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def map_freehire_fields(cls, data: Any) -> Any:
        """Map FreeHire API specific fields to our standard Job model."""
        if isinstance(data, dict):
            # FreeHire uses 'public_slug' as the unique identifier
            if "id" not in data and "public_slug" in data:
                data["id"] = str(data["public_slug"])
            
            # FreeHire uses 'body' for the job description
            if "description" not in data and "body" in data:
                data["description"] = data["body"]
            
            # Construct a URL if one isn't provided but we have the slug
            if "url" not in data and "public_slug" in data:
                data["url"] = f"https://freehire.me/j/{data['public_slug']}"
                
            # Fallback for title/company if they happen to be named differently
            if "title" not in data and "role" in data:
                data["title"] = data["role"]
                
        return data

class Application(BaseModel):
    """Generated application materials for a job."""
    job_id: str
    cover_letter: str
    cv_bullets: List[str]


# ── Day 13 Models ──

class FailedJob(BaseModel):
    """Track jobs that failed during processing."""
    job_id: str
    job_title: str
    error: str
    error_category: Optional[str] = None
    attempt_number: Optional[int] = None


class AgentResult(BaseModel):
    """Final result from agent run."""
    query: str
    jobs_found: List[Job]
    applications: List[Application]
    failed_jobs: List[FailedJob] = Field(default_factory=list)
    checkpoint_file: str
    status: str = "completed"  # "completed", "partial", "failed"