# Job Hunter Agent

30-Day Forward Deployed Software Engineer (FDSE) case study. Goal: a production-ready, observable, resilient AI agent that searches jobs, researches companies, matches a CV, and drafts tailored applications, ending in a defensible engineering case study.

Core value: survives crashes, resumes cleanly from checkpoints, delivers partial results when individual jobs fail, and keeps a full audit trail of every decision.

**Status:** Day 15 of 30 complete. Next: Day 16 (eval harness).

## Stack
Python 3.10+, OpenAI API (gpt-4o-mini), FreeHire API (job search), DuckDuckGo via the `ddgs` package (company research; import is `from ddgs import DDGS`, NOT `duckduckgo_search`), Pydantic, Rich, tiktoken, JSONL for audit trails and checkpoints, pytest.

## Setup and running
Always use the project venv; system `python3` lacks the dependencies. If the system Python was upgraded the venv breaks; rebuild it from the user's own terminal (the VS Code sandbox sees a different system Python than their terminal).

```bash
python3 -m venv --clear .venv && source .venv/bin/activate
pip install -e . pytest
export OPENAI_API_KEY=...   # or put it in .env
```

```bash
# query-based
python3 -m src.job_agent.main "python engineer london" --max-jobs 5
# CV-based (tailored applications)
python3 -m src.job_agent.main "Forward Deployed Engineer" --cv private/alexandre_cv.md --max-jobs 1
python3 -m src.job_agent.main --cv private/alexandre_cv.md --keywords examples/keywords.json --max-jobs 3
# options / recovery
python3 -m src.job_agent.main "query" --cv private/cv.md --verbose
python3 -m src.job_agent.main --list-interrupted
python3 -m src.job_agent.main "query" --resume --run-id <RUN_ID>
python3 -m src.job_agent.view_trace --narrative
pytest tests/ -v          # 44 tests, all passing
```

## Architecture
`main.py` (CLI) -> `AgentRunner` (loop controller, checkpoint manager, failure tracking) -> `LLMClient` (OpenAI, retry, timeout) + `tools.py` (FreeHire, DuckDuckGo) -> `ApplicationGenerator` (cover letters, CV bullets) -> `ReportGenerator` (Markdown).
Sidecars: `AuditLogger` -> `traces/trace_*.jsonl`; `CheckpointManager` -> `checkpoints/checkpoint_*.jsonl`.

Key modules in `src/job_agent/`: agent_runner, application_generator, audit_logger, checkpoint, config (timeouts), failures (8-category taxonomy), llm_client, main, models, prompts, report_generator, retry (exponential backoff, max 3), tools, view_trace.
Other dirs: `tests/`, `evals/` (dataset_schema.py, golden_dataset.json with 20 queries), `docs/` (PROGRESS.md, FAILURE_TAXONOMY.md), `examples/keywords.json`.
Gitignored runtime/private dirs: `private/` (real CV), `reports/`, `checkpoints/`, `traces/`.

Timeouts: LLM 60s, FreeHire 15s, DDG 10s.

## Progress
- Week 1 (Days 1-7): agent loop, FreeHire, DDG research, 12 output guardrails, tiktoken context pruning, tailored CV bullets/cover letters, JSONL audit trail + Markdown report.
- Week 2 (Days 8-14): failure taxonomy, retry/backoff, timeouts, checkpointing, validated resume, partial completion, recovery demo.
- Day 15: golden dataset (20 queries), restored `--cv`/`--keywords` flags, fixed OpenAI/httpx2 `process()` kwarg error.

## Roadmap
- Week 3 (measure): 16 eval harness (`evals/runner.py`, `scoring.py`, `report.py`), 17 correctness/format evals, 18 tool selection and escalation, 19 cost tracking and model routing, 20 failure-mode frequencies, 21 final eval report.
- Week 4 (communicate): 22 pain-point doc, 23 architecture doc, 24 iteration story, 25 engineer pitch, 26 VP pitch, 27 case study assembly, 28 final review/GitHub polish.

## Conventions and lessons
- Preserve all public symbols when replacing files.
- Test mocks should accept `**kwargs` so they survive signature changes.
- Keep tests isolated: `sys.modules` pollution in one test can break others.
- Verify exact dependency versions; environment issues (e.g. httpx2 vs httpx) can masquerade as code bugs.
- Prefer partial completion over all-or-nothing.
- Cover letters need human review. Single LLM provider (OpenAI) by design for now.
