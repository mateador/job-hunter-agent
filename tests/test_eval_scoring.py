from evals.dataset_schema import GoldenQuery
from evals.result_models import QueryScore, RunResult
from evals.scoring import (check_addressing, check_format, check_grounding, check_min_jobs,
                           check_relevance, check_search_honored, check_status, check_tool_sequence,
                           check_tools, extract_numbers, score_result)


def make_query(**kw):
    base = dict(id="t-1", query="python", category="standard", description="d",
                min_jobs=1, relevance_keywords=["python"])
    return GoldenQuery(**{**base, **kw})


def make_result(**kw):
    base = dict(query_id="t-1", query="python", category="standard", mode="mock", status="completed")
    return RunResult(**{**base, **kw})


JOB_PY = {"id": "j1", "title": "Python Engineer", "company": "Acme Ltd", "description": "Write Python"}
JOB_OTHER = {"id": "j2", "title": "Chef", "description": "Cook food"}

PARA = "I build reliable software and work closely with customers every day to solve real problems. " * 3
LETTER = (f"Dear Hiring Team at Acme,\n\nI am excited to apply for the Python Engineer position. {PARA}\n\n"
          f"{PARA}\n\n{PARA}\n\nBest regards,\nCandidate")
BULLETS = ["Built APIs", "Led a team", "Shipped features"]
GOOD_APP = {"job_id": "j1", "cover_letter": LETTER, "cv_bullets": BULLETS}


def app(**kw):
    return {**GOOD_APP, **kw}


# ── run-level ──

def test_status_pass_and_fail():
    assert check_status(make_result(), make_query()).passed
    assert not check_status(make_result(status="failed"), make_query()).passed
    assert not check_status(make_result(status=None, error="boom"), make_query()).passed


def test_status_expect_failure():
    q = make_query(expect_failure=True)
    assert check_status(make_result(status=None, error="boom"), q).passed
    assert check_status(make_result(status="completed", jobs=[]), q).passed
    assert not check_status(make_result(status="completed", jobs=[JOB_PY]), q).passed


def test_min_jobs():
    assert check_min_jobs(make_result(jobs=[JOB_PY]), make_query()).passed
    assert not check_min_jobs(make_result(jobs=[]), make_query()).passed
    assert check_min_jobs(make_result(jobs=[]), make_query(expect_failure=True)).skipped


def test_relevance_scoring_and_threshold():
    res = check_relevance(make_result(jobs=[JOB_PY, JOB_OTHER]), make_query())
    assert res.passed and res.score == 0.5
    res = check_relevance(make_result(jobs=[JOB_PY, JOB_OTHER, JOB_OTHER]), make_query())
    assert not res.passed
    assert check_relevance(make_result(jobs=[JOB_PY]), make_query(relevance_keywords=[])).skipped
    assert check_relevance(make_result(jobs=[]), make_query()).skipped


def test_relevance_is_case_insensitive_and_title_only():
    assert check_relevance(make_result(jobs=[{"title": "PYTHON dev", "description": None}]), make_query()).passed
    assert not check_relevance(make_result(jobs=[{"title": "Chef", "description": "python python"}]), make_query()).passed


def test_search_honored():
    assert check_search_honored(make_result(), make_query()).passed
    assert check_search_honored(make_result(ignored_params=["regions"]), make_query()).passed
    res = check_search_honored(make_result(ignored_params=["q"]), make_query())
    assert not res.passed and "q" in res.detail


# ── format ──

def test_format_passes_for_well_formed_application():
    res = check_format(make_result(jobs=[JOB_PY], applications=[GOOD_APP]), make_query())
    assert res.passed and res.score == 1.0


def test_format_skipped_without_outputs():
    assert check_format(make_result(), make_query()).skipped


def test_format_flags_each_problem():
    cases = {
        "bullets": app(cv_bullets=["only one"]),
        "empty bullet": app(cv_bullets=["a", " ", "c"]),
        "over 300": app(cv_bullets=["a", "b", "x" * 301]),
        "empty cover letter": app(cover_letter="  "),
        "raw JSON": app(cover_letter='{"cover_letter": "' + LETTER + '"}'),
        "fallback placeholder": app(cover_letter=LETTER + " Cover letter generation failed."),
        "unfilled placeholder": app(cover_letter=LETTER.replace("Acme", "[Company Name]")),
        "words": app(cover_letter="Dear Hiring Team,\n\nToo short.\n\nBest regards,\nMe"),
        "body paragraphs": app(cover_letter=f"Dear Team,\n\n{PARA * 2}\n\nBest,\nMe"),
    }
    for expected, bad in cases.items():
        res = check_format(make_result(jobs=[JOB_PY], applications=[bad]), make_query())
        assert not res.passed and expected in res.detail, (expected, res.detail)


def test_format_score_is_share_of_clean_applications():
    res = check_format(make_result(jobs=[JOB_PY], applications=[GOOD_APP, app(cv_bullets=[])]), make_query())
    assert not res.passed and res.score == 0.5


def test_format_flags_failures_without_category():
    res = check_format(make_result(failed_jobs=[{"job_id": "x"}]), make_query())
    assert not res.passed


# ── correctness ──

def test_extract_numbers_normalises():
    assert extract_numbers("Grew 30% in 2019, 1,000 users, 2.5 avg, eighteen years, 1st, 2m") == \
        {"30", "2019", "1000", "2.5", "18"}
    assert extract_numbers(None) == set()


def test_addressing_pass_and_fail():
    ok = check_addressing(make_result(jobs=[JOB_PY], applications=[GOOD_APP]), make_query())
    assert ok.passed
    wrong_company = app(cover_letter=LETTER.replace("Acme", "Globex"))
    res = check_addressing(make_result(jobs=[JOB_PY], applications=[wrong_company]), make_query())
    assert not res.passed and "company" in res.detail
    wrong_role = app(cover_letter=LETTER.replace("Python Engineer", "chef"))
    res = check_addressing(make_result(jobs=[JOB_PY], applications=[wrong_role]), make_query())
    assert not res.passed and "title" in res.detail


def test_addressing_title_with_prefix_and_agency_letters():
    job = {"id": "j1", "title": "UK Remote Job – DevOps Engineer at Covetrus", "company": "EasyInfoBlog.com"}
    letter = LETTER.replace("Acme", "Covetrus").replace("Python Engineer", "DevOps Engineer") + " (seen on EasyInfoBlog.com)"
    assert check_addressing(make_result(jobs=[job], applications=[app(cover_letter=letter)]), make_query()).passed
    agency = {"id": "j1", "title": "AWS DevOps Consultant", "company": "GCS Recruitment"}
    letter = LETTER.replace("Dear Hiring Team at Acme", "Dear Recruitment Consultant").replace("Python Engineer", "AWS DevOps Consultant")
    assert check_addressing(make_result(jobs=[agency], applications=[app(cover_letter=letter)]), make_query()).passed
    letter = LETTER.replace("Acme", "Globex").replace("Python Engineer", "AWS DevOps Consultant")
    assert not check_addressing(make_result(jobs=[agency], applications=[app(cover_letter=letter)]), make_query()).passed


def test_grounding_skipped_without_cv_numbers():
    assert check_grounding(make_result(applications=[GOOD_APP]), make_query()).skipped


def test_grounding_flags_invented_numbers():
    invented = app(cv_bullets=["Grew revenue by 47%", "Led 12 engineers", "Shipped features"])
    res = check_grounding(make_result(jobs=[JOB_PY], applications=[invented], cv_numbers=["12"]), make_query())
    assert not res.passed and "47" in res.detail and "12" not in res.detail.split("[")[1]


def test_grounding_allows_cv_and_posting_numbers():
    job = {**JOB_PY, "description_numbers": ["5"]}
    text = app(cv_bullets=["Grew revenue by 30%", "Five years of 5+ experience", "Shipped"],
               cover_letter=LETTER + " 5 years")
    res = check_grounding(make_result(jobs=[job], applications=[text], cv_numbers=["30"]), make_query())
    assert res.passed, res.detail


# ── tools ──

def test_tools_requires_freehire_but_not_duckduckgo():
    q = make_query(expected_tools=["freehire", "duckduckgo"])
    res = check_tools(make_result(tools_called=["search_freehire"]), q)
    assert res.passed and "known gap" in res.detail
    assert not check_tools(make_result(tools_called=["llm_chat"]), q).passed
    assert check_tools(make_result(), make_query(expected_tools=[])).passed


def test_tool_sequence():
    ok = check_tool_sequence(make_result(jobs=[JOB_PY], applications=[GOOD_APP],
                                         tools_called=["search_freehire", "llm_chat"]), make_query())
    assert ok.passed
    twice = check_tool_sequence(make_result(tools_called=["search_freehire", "search_freehire"]), make_query())
    assert not twice.passed
    early = check_tool_sequence(make_result(jobs=[JOB_PY], tools_called=["llm_chat", "search_freehire"]), make_query())
    assert not early.passed
    orphan = check_tool_sequence(make_result(jobs=[], tools_called=["search_freehire", "llm_chat"]), make_query())
    assert not orphan.passed
    retry = check_tool_sequence(make_result(jobs=[JOB_PY], applications=[GOOD_APP],
                                            tools_called=["search_freehire", "llm_chat", "llm_chat"]), make_query())
    assert retry.passed and "retries" in retry.detail
    assert check_tool_sequence(make_result(), make_query()).skipped


def test_failed_scored_checks_fail_query_but_not_informational():
    bad = make_result(jobs=[JOB_PY], applications=[app(cv_bullets=[])])
    assert not score_result(bad, make_query()).passed


def test_score_result_runs_all_checks():
    s = score_result(make_result(jobs=[JOB_PY], applications=[GOOD_APP],
                                 tools_called=["search_freehire", "llm_chat"]), make_query())
    assert {c.name for c in s.checks} == {"status", "min_jobs", "format", "addressing", "grounding",
                                          "relevance", "search_honored", "tools", "tool_sequence"}
    assert s.passed
