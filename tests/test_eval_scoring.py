from evals.dataset_schema import GoldenQuery
from evals.result_models import QueryScore, RunResult
from evals.scoring import (check_format, check_min_jobs, check_relevance,
                           check_status, check_tools, score_result)


def make_query(**kw):
    base = dict(id="t-1", query="python", category="standard", description="d",
                min_jobs=1, relevance_keywords=["python"])
    return GoldenQuery(**{**base, **kw})


def make_result(**kw):
    base = dict(query_id="t-1", query="python", category="standard", mode="mock", status="completed")
    return RunResult(**{**base, **kw})


JOB_PY = {"title": "Python Engineer", "description": "Write Python"}
JOB_OTHER = {"title": "Chef", "description": "Cook food"}
GOOD_APP = {"job_id": "a", "cover_letter": "Dear...", "cv_bullets": ["b"]}


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


def test_format_checks():
    assert check_format(make_result(), make_query()).skipped
    assert check_format(make_result(applications=[GOOD_APP]), make_query()).passed
    bad = {"job_id": "a", "cover_letter": " ", "cv_bullets": []}
    res = check_format(make_result(applications=[bad]), make_query())
    assert not res.passed and "empty cover letter" in res.detail and "no CV bullets" in res.detail
    assert not check_format(make_result(failed_jobs=[{"job_id": "x"}]), make_query()).passed


def test_relevance_scoring_and_threshold():
    res = check_relevance(make_result(jobs=[JOB_PY, JOB_OTHER]), make_query())
    assert res.passed and res.score == 0.5
    res = check_relevance(make_result(jobs=[JOB_PY, JOB_OTHER, JOB_OTHER]), make_query())
    assert not res.passed
    assert check_relevance(make_result(jobs=[JOB_PY]), make_query(relevance_keywords=[])).skipped
    assert check_relevance(make_result(jobs=[]), make_query()).skipped


def test_relevance_is_case_insensitive():
    job = {"title": "PYTHON dev", "description": None}
    assert check_relevance(make_result(jobs=[job]), make_query()).passed


def test_tools_check_is_informational():
    q = make_query(expected_tools=["freehire", "duckduckgo"])
    res = check_tools(make_result(tools_called=["search_freehire"]), q)
    assert not res.passed and res.informational
    score = QueryScore(result=make_result(jobs=[JOB_PY], applications=[GOOD_APP],
                                          tools_called=["search_freehire"]), checks=[res])
    assert score.passed  # informational failures don't fail the query


def test_score_result_runs_all_checks():
    s = score_result(make_result(jobs=[JOB_PY], applications=[GOOD_APP]), make_query())
    assert {c.name for c in s.checks} == {"status", "min_jobs", "format", "relevance", "search_honored", "tools"}


def test_relevance_uses_title_only():
    job = {"title": "Chef", "description": "python python python"}
    assert not check_relevance(make_result(jobs=[job]), make_query()).passed


def test_search_honored():
    from evals.scoring import check_search_honored
    assert check_search_honored(make_result(), make_query()).passed
    assert check_search_honored(make_result(ignored_params=["regions"]), make_query()).passed
    res = check_search_honored(make_result(ignored_params=["q"]), make_query())
    assert not res.passed and "q" in res.detail
