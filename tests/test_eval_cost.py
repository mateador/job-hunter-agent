import json
import sys

import pytest

from evals.compare import compare_models, main as compare_main, render_comparison
from evals.dataset_schema import GoldenQuery, load_dataset
from evals.report import render_markdown, summarize
from evals.result_models import RunResult
from evals.runner import main as runner_main, run_dataset_budgeted, run_query
from evals.scoring import check_usage_recorded, score_result


def queries(*ids):
    return [q for q in load_dataset().queries if q.id in ids]


def q():
    return GoldenQuery(id="t", query="x", category="standard", description="d")


def result(**kw):
    return RunResult(**{**dict(query_id="t", query="x", category="standard", mode="mock", status="completed"), **kw})


def test_mock_run_records_synthetic_usage(tmp_path):
    r = run_query(queries("std-01")[0], False, 3, "gpt-4o-mini", tmp_path)
    assert r.usage["calls"] == len(r.applications) > 0
    assert r.usage["synthetic"] is True and r.usage["cost_usd"] > 0
    assert set(r.usage["by_purpose"]) == {"application"}


def test_unknown_model_is_unpriced_in_results(tmp_path):
    r = run_query(queries("std-01")[0], False, 3, "no-such-model", tmp_path)
    assert r.usage["unpriced_calls"] == r.usage["calls"] and r.usage["cost_usd"] == 0


def test_retry_model_is_routed_in_results(tmp_path):
    r = run_query(queries("std-01")[0], False, 3, "gpt-4o-mini", tmp_path, retry_model="gpt-4o")
    assert set(r.usage["by_model"]) == {"gpt-4o-mini"}  # no retries happen on clean mock output


def test_usage_recorded_check():
    app = {"job_id": "a", "cover_letter": "x", "cv_bullets": ["b"]}
    assert check_usage_recorded(result(), q()).skipped
    assert check_usage_recorded(result(applications=[app], usage={"calls": 1}), q()).passed
    bad = check_usage_recorded(result(applications=[app, app], usage={"calls": 1}), q())
    assert not bad.passed and "1 usage records for 2 applications" in bad.detail
    assert not check_usage_recorded(result(applications=[app]), q()).passed  # instrumentation silently off


def test_report_has_cost_section_and_per_query_cost(tmp_path):
    scores = [score_result(run_query(x, False, 3, "gpt-4o-mini", tmp_path), x) for x in queries("std-01", "std-02")]
    cost = summarize(scores)["cost"]
    assert cost["calls"] > 0 and cost["cost_per_application_usd"] > 0
    md = render_markdown(scores, "mock", "now")
    assert "## Cost" in md and "synthetic" in md and "not billing" in md and "| Cost |" in md
    assert "| application |" in md and "| gpt-4o-mini |" in md


def test_budget_cap_stops_between_queries(tmp_path):
    scores, reason = run_dataset_budgeted(queries("std-01", "std-02", "std-03"), False, 3, "gpt-4o-mini",
                                          tmp_path, max_cost=1e-9)
    assert len(scores) == 1 and "exceeded" in reason and "1/3" in reason
    scores, reason = run_dataset_budgeted(queries("std-01", "std-02"), False, 3, "gpt-4o-mini", tmp_path, max_cost=5.0)
    assert len(scores) == 2 and reason is None


def test_main_prints_cost_and_notes_budget_stop(tmp_path, capsys):
    assert runner_main(["--ids", "std-01,std-02,std-03", "--max-cost", "0.000000001", "--skip-scenarios",
                        "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Estimated cost: $" in out and "synthetic mock estimate" in out
    md = next(tmp_path.glob("eval_mock_*.md")).read_text()
    assert "Stopped after 1/3 queries" in md


def test_main_flags_unpriced_calls(tmp_path, capsys):
    runner_main(["--ids", "std-01", "--model", "no-such-model", "--skip-scenarios", "--out", str(tmp_path)])
    assert "unpriced calls not included" in capsys.readouterr().out


# ── compare ──

def test_compare_mock_runs_every_model(tmp_path):
    rows = compare_models(["gpt-4o-mini", "gpt-4o", "no-such-model"], queries("std-01", "std-02"), False, 3, tmp_path)
    assert [r["model"] for r in rows] == ["gpt-4o-mini", "gpt-4o", "no-such-model"]
    assert [r["priced"] for r in rows] == [True, True, False]
    assert rows[1]["cost_usd"] > rows[0]["cost_usd"]  # same synthetic tokens, pricier model
    assert rows[2]["cost_usd"] == 0 and rows[2]["unpriced_calls"] > 0
    md = render_comparison(rows, "mock", "now", 2)
    assert "no-such-model (unpriced)" in md and "x |" in md and "synthetic" in md and "cost is understated" in md
    assert (tmp_path / "compare" / "gpt-4o").exists()  # separate run dirs per model


def test_compare_main_writes_files(tmp_path, capsys):
    assert compare_main(["--mock", "--models", "gpt-4o-mini,gpt-4o", "--ids", "std-01", "--out", str(tmp_path)]) == 0
    data = json.loads(next(tmp_path.glob("compare_mock_*.json")).read_text())
    assert [r["model"] for r in data["rows"]] == ["gpt-4o-mini", "gpt-4o"]
    assert "Model Comparison" in next(tmp_path.glob("compare_mock_*.md")).read_text()


def test_compare_needs_two_models(tmp_path):
    with pytest.raises(SystemExit):
        compare_main(["--mock", "--models", "gpt-4o-mini", "--out", str(tmp_path)])


def test_compare_live_aborts_without_confirmation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert compare_main(["--models", "gpt-4o-mini,gpt-4o", "--ids", "std-01", "--out", str(tmp_path)]) == 1
    assert "Aborted" in capsys.readouterr().out
    assert not list(tmp_path.glob("compare_*"))
