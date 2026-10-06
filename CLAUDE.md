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
python -m pytest tests -q   # 50 tests, all passing
```

Run tests with `python -m pytest`, not bare `pytest`: a user-level pytest in `~/.local` can shadow the venv's and fail with `No module named 'ddgs'`.

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
- Day 15: golden dataset (`evals/golden_dataset.json`, 20 queries with per-query `cv_path`, `relevance_keywords`, `expected_tools`, validated by `evals/dataset_schema.py`), restored `--cv`/`--keywords` flags, fixed OpenAI/httpx2 `process()` kwarg error.
- Day 16: eval harness in `evals/` (`runner.py`, `scoring.py`, `report.py`, `result_models.py`, `fixtures/mock_jobs.json`). `python -m evals.runner` is mock mode (offline, free; validates the harness only); `--live` hits real FreeHire/OpenAI and asks for confirmation unless `--yes`. Other flags: `--ids`, `--limit`, `--max-jobs`, `--out`. Reports go to gitignored `evals/results/`. Run-level checks: status, min_jobs, relevance (>=50% of job TITLES match keywords), search_honored. Day 17 per-application checks (a query passes only if every application passes; `score` = share passing): `format` (3-4 bullets <=300 chars, 3-5 body paragraphs, 150-350 words, no raw JSON/placeholder/fallback text), `addressing` (letter names the company or is addressed to a consultant, and references the job title), `grounding` (every number in the output must appear in the CV or job posting; numbers-only, so invented employers/skills are NOT caught; skipped without a CV). Tool checks: `tools` (FreeHire required; DuckDuckGo missing is noted, not scored until Day 18) and `tool_sequence` (search once and first; LLM calls match jobs, retries noted not failed). `min_jobs`/`relevance_keywords` values are untuned guesses; adjust after the first live run.
- Day 16 live-eval finding (fixed): `search_freehire` used the generic `/api/v1/jobs` endpoint, which silently ignores `q` and returns an unfiltered feed (agent produced applications for irrelevant jobs while reporting "completed"). It now defaults to `/api/v1/agent/jobs/search` (no API key needed), reads `FREEHIRE_*` settings from the environment at call time, logs `meta.ignored_params` as a `search_meta` trace event, and raises `FreeHireIgnoredParamError` if the query param is ignored. Only `regions=uk` and `posted_within_days` are honoured filters there; `location`/`country` are ignored (`countries` is the real name).
- First full live eval (20 queries, 2 jobs each): 18/20. It exposed that a blank query searched an unfiltered feed and generated applications for random jobs; now rejected by the CLI (`parser.error`) and by `AgentRunner.run` (`InvalidQueryError`, raised before any search). Baseline write-up in `docs/` is deferred until after Day 17.
- Day 17 on the saved 20-query live run: format 100%, grounding 100% (11 CV runs), addressing 2 false positives fixed in the heuristics. Real data has not yet shown a genuine format/grounding failure; the checks are proven only by synthetic bad fixtures in `tests/test_eval_scoring.py`. Consider an `--judge` LLM faithfulness check later (catches invented employers/skills).
- Day 18: rule-based escalation. `src/job_agent/research_policy.py::should_research` decides per job: no company -> skip; agency (name pattern/list) -> skip; company already researched this run -> reuse; description >= 600 chars -> skip; otherwise research via `tools.research_company` (DuckDuckGo, ad/tracker URLs filtered, top 3 snippets + sources into `CompanyResearch.summary/sources`). Research failure is logged (`research_failed`) and degrades to a letter without research, never failing the job. Every decision is a `research_decision` trace event and is returned as `research_decisions` by `AgentRunner.run` (in-memory only, not checkpointed; the per-run company cache is not restored on resume). The generation prompt now also says to state only company facts found in the posting or research. Evals: `evals/tool_scenarios.json` (14 hand-labelled scenarios, run offline against the real AgentRunner by `evals/scenarios.py`; `python -m evals.runner --scenarios-only` runs just these, free) plus run-level checks `tool_selection`, `escalation_graceful`, `no_redundant_research`; `grounding` also accepts numbers from research text. Dataset `expected_tools` no longer lists duckduckgo (research is per job). `tests/conftest.py` stubs `research_company` for every test (tests must never hit the network).
- Day 18 follow-ups (from the first full live baseline, 19/20, written up in `docs/BASELINE.md` with a stripped summary in `docs/baselines/`): (1) `search_duckduckgo` treats ddgs's `DDGSException("No results found")` as an empty list, not a failure; (2) runtime grounding guard in `AgentRunner._generate_checked`: if the CV has figures and the draft states numbers absent from CV/posting/research (`src/job_agent/grounding.py`, shared with the evals), regenerate ONCE with a `revision_note` naming them; if still ungrounded keep the application with `Application.warnings` (shown as "Review needed" in the report; trace events `grounding_violation`/`grounding_retry`/`grounding_flagged`); skipped when no CV or the CV has no figures. Evals: `tool_sequence` allows one extra LLM call per `grounding_retries`; report has a "Grounding guard" line. FreeHire descriptions from adzuna/whatjobs-uk are truncated to ~500 chars upstream, so "thin_description" mostly means "truncated"; the 600 threshold sits in an empty gap (502-1300), so it is not sensitive. Follow-up live run (niche-02, niche-04, agency-02; `eval_live_20261006_130312`): 3/3 pass; the empty-result fix is confirmed live (107632 Capital Markets: empty result, 0 failures); the grounding guard did NOT trigger (0/6), so it is only unit-tested, not demonstrated live (the model simply did not fabricate this time). Agency detection is name-based: 'Intec Select Ltd' (a recruiter whose posting says 'the client's office') was researched as a normal company.
- Known gaps (for later days): README/PROGRESS still describe features that are no longer in `src/` (LLM tool-call loop, 12 guardrails, tiktoken context pruning; `prompts.py` SYSTEM_PROMPT is imported but unused); agency detection is name-pattern only and has no letter-level eval check; FreeHire search is hard-coded to `regions: "uk"`, so non-UK queries (e.g. edge-04 Lisbon) are weak tests (Day 20 failure modes); no full 20-query live baseline exists with the Day 17/18 checks yet.

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
