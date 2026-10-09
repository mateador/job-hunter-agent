"""Hand-labelled tool-selection scenarios, run offline against the real AgentRunner.

The expected decisions are written by hand in tool_scenarios.json, independently of the
policy code, so these scenarios test the escalation policy rather than restating it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.job_agent.agent_runner import AgentRunner
from src.job_agent.audit_logger import AuditLogger
from src.job_agent.checkpoint import CheckpointManager

from .result_models import ScenarioResult

SCENARIOS_PATH = Path(__file__).parent / "tool_scenarios.json"


class ScenarioJob(BaseModel):
    id: str
    title: str = "Software Engineer"
    company: Optional[str]
    description_chars: Optional[int] = None  # None (with no text) means no description at all
    description_text: Optional[str] = None  # used as written, then padded with filler to description_chars
    expected_research: bool
    expected_reason: str


class Scenario(BaseModel):
    id: str
    description: str
    jobs: List[ScenarioJob] = Field(min_length=1)
    ddg_mode: Literal["ok", "fail", "empty"] = "ok"


def load_scenarios(path: Path = SCENARIOS_PATH) -> List[Scenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    scenarios = [Scenario.model_validate(s) for s in data["scenarios"]]
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate scenario ids")
    return scenarios


def _description(job: ScenarioJob) -> Optional[str]:
    if job.description_text is None:
        return None if job.description_chars is None else "a" * job.description_chars
    return job.description_text.ljust(job.description_chars or 0, ".")


def run_scenario(scenario: Scenario, out_dir: Path) -> ScenarioResult:
    # Imported here: runner imports this module's siblings, avoid a circular import at load time.
    from .runner import _mock_environment, _read_trace, _tools_from_trace

    run_dir = out_dir / "scenarios" / scenario.id
    audit_logger = AuditLogger(trace_dir=str(run_dir / "traces"))
    checkpoint_manager = CheckpointManager(checkpoint_dir=str(run_dir / "checkpoints"), run_id=scenario.id)
    jobs = [
        {"id": j.id, "title": j.title, "company": j.company,
         "description": _description(j)}
        for j in scenario.jobs
    ]
    problems: List[str] = []
    try:
        with _mock_environment(audit_logger, jobs=jobs, research_mode=scenario.ddg_mode):
            agent = AgentRunner(audit_logger=audit_logger, checkpoint_manager=checkpoint_manager,
                                max_jobs=len(jobs), cv_text=None)
            output = agent.run("scenario")
    except Exception as e:
        return ScenarioResult(id=scenario.id, description=scenario.description, passed=False,
                              problems=[f"run raised {type(e).__name__}: {e}"])

    decisions = {d["job_id"]: d for d in output["research_decisions"]}
    for j in scenario.jobs:
        d = decisions.get(j.id)
        if d is None:
            problems.append(f"{j.id}: no decision recorded")
            continue
        if (d["decision"], d["reason"]) != (j.expected_research, j.expected_reason):
            problems.append(f"{j.id}: got ({d['decision']}, {d['reason']}), "
                            f"expected ({j.expected_research}, {j.expected_reason})")
        if scenario.ddg_mode == "fail" and j.expected_research and not d["error"]:
            problems.append(f"{j.id}: research failure was not recorded")

    expected_calls = sum(j.expected_research for j in scenario.jobs)
    ddg_calls = _tools_from_trace(_read_trace(audit_logger.trace_file)).count("search_duckduckgo")
    if ddg_calls != expected_calls:
        problems.append(f"DuckDuckGo called {ddg_calls} times, expected {expected_calls}")
    if output["status"] != "completed" or len(output["applications"]) != len(jobs):
        problems.append(f"jobs did not all complete (status={output['status']}, "
                        f"{len(output['applications'])}/{len(jobs)} applications)")
    return ScenarioResult(id=scenario.id, description=scenario.description,
                          passed=not problems, problems=problems)


def run_scenarios(out_dir: Path) -> List[ScenarioResult]:
    return [run_scenario(s, out_dir) for s in load_scenarios()]
