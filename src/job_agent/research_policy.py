"""Escalation policy: when is a DuckDuckGo company lookup worth making?

FreeHire is the default source. Research is added per job only when the posting does not
give enough to write a good letter and a lookup could actually help.
"""
import re
from typing import Any, Collection, Mapping, Tuple, Union

from .models import Job

# A description shorter than this is treated as too thin to tailor a letter from.
THIN_DESCRIPTION_CHARS = 600

# Researching an agency is useless: the letter is about the (unnamed) end client.
_AGENCY_PATTERN = re.compile(
    r"\b(recruit\w*|staffing|resourcing|headhunt\w*|hays|ocho|michael page|corriculo|robert half|"
    r"adecco|randstad|manpower|reed|hunter bond|harvey nash)\b",
    re.I,
)

# Second agency signal: the posting speaks for an unnamed end client. Deliberately narrow.
# Singular "our/my ... client" only ("our clients" is ordinary employer language, as is
# "Our Client Success Team"), "the client's office/site", "on behalf of our client", and the
# UK boilerplate "acting as an employment agency/business".
_CLIENT_NOUN_EXCLUDED = r"(?!\s+(?:success|service|services|support|team|care|relations?|experience|portfolio)\b)"
_AGENCY_POSTING_PATTERN = re.compile(
    r"\b(?:our|my)\s+(?:[\w-]+\s+){0,3}client\b" + _CLIENT_NOUN_EXCLUDED
    + r"|\bthe\s+client(?:'|\u2019)?s\s+(?:offices?|sites?|premises|locations?)\b"
    + r"|\bon\s+behalf\s+of\s+(?:our|a|one\s+of\s+our)\s+(?:[\w-]+\s+){0,2}clients?\b"
    + r"|\bacting\s+as\s+an?\s+employment\s+(?:agency|business)\b",
    re.I,
)


def normalise_company(company: Any) -> str:
    return " ".join(str(company or "").lower().split())


def is_agency(company: Any) -> bool:
    return bool(_AGENCY_PATTERN.search(str(company or "")))


def has_agency_language(description: Any) -> bool:
    return bool(_AGENCY_POSTING_PATTERN.search(str(description or "")))


def should_research(
    job: Union[Job, Mapping[str, Any]],
    researched: Collection[str] = (),
) -> Tuple[bool, str]:
    """Decide whether to call the company-research tool for this job.

    Returns (research?, reason). `researched` holds normalised names of companies already
    looked up in this run. Reasons: no_company, agency, already_researched,
    agency_posting, rich_description, thin_description.
    """
    get = job.get if isinstance(job, Mapping) else lambda k, d=None: getattr(job, k, d)
    company = normalise_company(get("company"))
    if not company:
        return False, "no_company"
    if is_agency(company):
        return False, "agency"
    if has_agency_language(get("description")):
        return False, "agency_posting"
    if company in researched:
        return False, "already_researched"
    if len((get("description") or "").strip()) >= THIN_DESCRIPTION_CHARS:
        return False, "rich_description"
    return True, "thin_description"
