"""
Day 15: Tests for CV and keywords integration.
Run with: pytest tests/test_cv_integration.py -v
"""
import sys
import json
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import patch, MagicMock

from src.job_agent.main import load_cv, load_keywords
from src.job_agent.application_generator import _build_candidate_section
from src.job_agent.models import JobCandidate


# ── CV Loading Tests ──

def test_load_cv_reads_file(tmp_path):
    cv_file = tmp_path / "cv.md"
    cv_file.write_text("# My CV\n\nExperienced engineer.")
    result = load_cv(str(cv_file))
    assert result == "# My CV\n\nExperienced engineer."


def test_load_cv_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_cv(str(tmp_path / "nonexistent.md"))


def test_load_cv_directory_instead_of_file(tmp_path):
    with pytest.raises(ValueError, match="not a file"):
        load_cv(str(tmp_path))


# ── Keywords Loading Tests ──

def test_load_keywords_list_format(tmp_path):
    kw_file = tmp_path / "kw.json"
    kw_file.write_text(json.dumps(["query1", "query2", "query3"]))
    result = load_keywords(str(kw_file))
    assert result == ["query1", "query2", "query3"]


def test_load_keywords_object_format(tmp_path):
    kw_file = tmp_path / "kw.json"
    kw_file.write_text(json.dumps({"queries": ["query1", "query2"]}))
    result = load_keywords(str(kw_file))
    assert result == ["query1", "query2"]


def test_load_keywords_strips_whitespace(tmp_path):
    kw_file = tmp_path / "kw.json"
    kw_file.write_text(json.dumps(["  query1  ", "", "  "]))
    result = load_keywords(str(kw_file))
    assert result == ["query1"]


def test_load_keywords_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_keywords(str(tmp_path / "nonexistent.json"))


def test_load_keywords_invalid_format(tmp_path):
    kw_file = tmp_path / "kw.json"
    kw_file.write_text(json.dumps({"wrong_key": ["query1"]}))
    with pytest.raises(ValueError, match="Invalid keywords format"):
        load_keywords(str(kw_file))


def test_load_keywords_empty_list(tmp_path):
    kw_file = tmp_path / "kw.json"
    kw_file.write_text(json.dumps([]))
    with pytest.raises(ValueError, match="contains no queries"):
        load_keywords(str(kw_file))


# ── Candidate Section Builder Tests ──

def test_build_candidate_section_with_cv_text():
    cv_text = "# John Doe\n\nSenior Python Engineer with 10 years experience."
    result = _build_candidate_section(cv_text, None)
    assert "CANDIDATE CV (verbatim)" in result
    assert "John Doe" in result
    assert "Senior Python Engineer" in result


def test_build_candidate_section_with_profile():
    profile = JobCandidate(
        name="Jane Smith",
        years_experience=7,
        current_role="Tech Lead",
        skills=["Python", "AWS"],
        background="Experienced leader."
    )
    result = _build_candidate_section(None, profile)
    assert "CANDIDATE PROFILE" in result
    assert "Jane Smith" in result
    assert "7 years" in result


def test_build_candidate_section_cv_text_takes_priority():
    cv_text = "Raw CV content"
    profile = JobCandidate(name="Should Not Appear")
    result = _build_candidate_section(cv_text, profile)
    assert "Raw CV content" in result
    assert "Should Not Appear" not in result


def test_build_candidate_section_defaults_when_both_none():
    result = _build_candidate_section(None, None)
    assert "CANDIDATE PROFILE" in result
    # Should use the default JobCandidate values
    assert "Candidate" in result