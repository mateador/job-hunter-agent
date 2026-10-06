import pytest

from evals.scenarios import load_scenarios, run_scenario

SCENARIOS = load_scenarios()


def test_scenario_set_covers_each_decision_reason():
    reasons = {j.expected_reason for s in SCENARIOS for j in s.jobs}
    assert reasons == {"thin_description", "rich_description", "no_company", "agency", "already_researched"}
    assert {s.ddg_mode for s in SCENARIOS} == {"ok", "fail", "empty"}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_scenario_passes(scenario, tmp_path):
    result = run_scenario(scenario, tmp_path)
    assert result.passed, result.problems


def test_scenario_fails_when_labels_disagree(tmp_path):
    wrong = SCENARIOS[0].model_copy(deep=True)
    wrong.jobs[0].expected_research = not wrong.jobs[0].expected_research
    result = run_scenario(wrong, tmp_path)
    assert not result.passed and any("expected" in p for p in result.problems)
