import pytest

from src.job_agent.models import Job
from src.job_agent.research_policy import THIN_DESCRIPTION_CHARS, has_agency_language, is_agency, should_research


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


# Phrases taken from real saved postings (recruiters whose names the name check misses).
@pytest.mark.parametrize("text", [
    "Our client isn't buying off-the-shelf solutions or stitching together tools.",
    "My globally known client are looking for a AWS DevOps Consultant.",
    "Hybrid with 2 days per week on-site at the client\u2019s office.",
    "About the Company: Our client is a fast-scaling AI software business.",
    "Recruiting on behalf of our client, a retail bank.",
    "We are acting as an employment agency in relation to this vacancy.",
])
def test_agency_language_detected(text):
    assert has_agency_language(text)


@pytest.mark.parametrize("text", [
    "Our Client Success Team partners with employers.",
    "Our work helps our clients build critical infrastructure.",
    "Draft communications on behalf of senior leadership.",
    "Take ownership of client projects and client accounts.",
    "We bring a client-first mindset to everything.",
    "Coordinate workflow across hospital clients and staff.",
    "Tailored to client's needs, you will deliver software.",
    "",
    None,
])
def test_ordinary_client_language_is_not_agency(text):
    assert not has_agency_language(text)


def test_agency_language_skips_research_for_unrecognised_name():
    j = {"company": "Northwind Digital Ltd", "description": "Our client is a fintech scale-up."}
    assert not is_agency(j["company"])
    assert should_research(j) == (False, "agency_posting")


def test_agency_language_beats_rich_description_and_cache():
    text = "Our client is a fintech scale-up. " + "x" * 1000
    j = {"company": "Northwind Digital Ltd", "description": text}
    assert should_research(j, researched={"northwind digital ltd"}) == (False, "agency_posting")


def test_agency_name_still_reported_as_agency():
    j = {"company": "Hays", "description": "Our client is a fintech."}
    assert should_research(j) == (False, "agency")
