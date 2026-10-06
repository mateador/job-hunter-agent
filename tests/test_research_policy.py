import pytest

from src.job_agent.models import Job
from src.job_agent.research_policy import THIN_DESCRIPTION_CHARS, is_agency, should_research


def job(company="Acme", chars=100):
    return {"id": "x", "company": company, "description": None if chars is None else "a" * chars}


def test_thin_description_escalates():
    assert should_research(job(chars=100)) == (True, "thin_description")
    assert should_research(job(chars=None)) == (True, "thin_description")


def test_threshold_boundary():
    assert should_research(job(chars=THIN_DESCRIPTION_CHARS - 1)) == (True, "thin_description")
    assert should_research(job(chars=THIN_DESCRIPTION_CHARS)) == (False, "rich_description")


def test_whitespace_does_not_count_towards_length():
    j = {"company": "Acme", "description": " " * 1000 + "short"}
    assert should_research(j) == (True, "thin_description")


@pytest.mark.parametrize("company", [None, "", "   "])
def test_no_company(company):
    assert should_research(job(company=company)) == (False, "no_company")


@pytest.mark.parametrize("company", ["Hays", "Ocho People", "Michael Page", "GCS Recruitment",
                                     "Northwind Recruitment Ltd", "Acme Staffing", "Reed"])
def test_agencies_are_skipped(company):
    assert is_agency(company)
    assert should_research(job(company=company)) == (False, "agency")


@pytest.mark.parametrize("company", ["Octopus Energy", "Freed Software", "Workato", "Applied Intuition"])
def test_non_agencies_are_researched(company):
    assert not is_agency(company)
    assert should_research(job(company=company)) == (True, "thin_description")


def test_already_researched_is_case_and_space_insensitive():
    assert should_research(job(company="  ACME   corp "), researched={"acme corp"}) == (False, "already_researched")


def test_accepts_job_model():
    j = Job(id="1", company="Acme", description="short")
    assert should_research(j) == (True, "thin_description")
