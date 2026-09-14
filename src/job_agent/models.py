"""
Day 13: Pydantic models for agent data structures.
Includes Week 1 models + Day 13 additions.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


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
    title: str
    company: str
    location: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    posted_date: Optional[str] = None
    salary: Optional[str] = None


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