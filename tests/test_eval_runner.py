import json

from evals.dataset_schema import load_dataset
from evals.report import summarize
from evals.runner import main, run_dataset, run_query


def _queries(*ids):
    return [q for q in load_dataset().queries if q.id in ids]


def test_mock_run_is_offline_and_produces_applications(tmp_path):
    q = _queries("std-01")[0]
    result = run_query(q, live=False, max_jobs=3, model="gpt-4o-mini", out_dir=tmp_path)
    assert result.error is None
    assert result.status == "completed"
    assert result.jobs and len(result.applications) == len(result.jobs)
    assert "search_freehire" in result.tools_called and "llm_chat" in result.tools_called


def test_gibberish_query_returns_no_jobs(tmp_path):
    result = run_query(_queries("edge-01")[0], False, 3, "gpt-4o-mini", tmp_path)
    assert result.jobs == [] and result.error is None


def test_run_dataset_scores_and_summarizes(tmp_path):
    scores = run_dataset(_queries("std-01", "edge-01", "edge-02"), False, 3, "gpt-4o-mini", tmp_path)
    by_id = {s.result.query_id: s for s in scores}
    assert by_id["std-01"].passed
    assert by_id["edge-02"].passed  # blank query counts as graceful failure
    summary = summarize(scores)
    assert summary["total"] == 3 and "edge_case" in summary["by_category"]


def test_main_writes_reports(tmp_path, capsys):
    code = main(["--ids", "std-01,std-02", "--out", str(tmp_path)])
    assert code == 0
    jsons = list(tmp_path.glob("eval_mock_*.json"))
    mds = list(tmp_path.glob("eval_mock_*.md"))
    assert len(jsons) == 1 and len(mds) == 1
    payload = json.loads(jsons[0].read_text())
    assert payload["mode"] == "mock" and payload["summary"]["total"] == 2
    assert "Mock mode" in mds[0].read_text()


def test_unknown_id_is_rejected(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        main(["--ids", "nope", "--out", str(tmp_path)])


def test_live_mode_aborts_without_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["--live", "--ids", "std-01", "--out", str(tmp_path)]) == 1
    assert not list(tmp_path.glob("eval_*"))
