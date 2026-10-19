"""The induced-fault scenarios (evals/stress/faults.py) run offline and must match their expectations."""
import pytest

from evals.stress import faults


@pytest.mark.parametrize("scenario", faults.SCENARIOS, ids=lambda s: s.id)
def test_fault_scenario_matches_expectation(scenario):
    rows = faults.run_all([scenario.id])
    assert rows[0]["matches"], rows[0]["observed"]
