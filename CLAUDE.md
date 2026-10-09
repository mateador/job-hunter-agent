# Job Hunter Agent

30-Day Forward Deployed Software Engineer (FDSE) case study. Goal: an observable, resilient AI workflow that searches jobs, researches companies, matches a CV, and drafts tailored applications, ending in a defensible engineering case study. Core value: survives crashes, resumes from checkpoints, delivers partial results when jobs fail, keeps a full audit trail, and is measured by evals.

## Where we are (read this first when resuming)
- **Status:** Day 21 of 30 complete (Week 3 checkpoint). **Next: Day 22** (Week 4: pain-point doc), then 23-28 (architecture, iteration story, pitches, assembly, final review).
- **Uncommitted at the time of writing:** the Day 19-21 follow-ups (Day 20 work, reasoning-effort/timeout options, `format_rules.py` and structure guard, addressing-check fix, `evals/rescore.py`, Day 21 baseline docs). Run `git status` and `git log --oneline` to see whether it was committed. The user commits; never commit without being asked.
- **Day 20 done:** (1) `docs/FAILURE_TAXONOMY.md` rewritten as a failure-mode document with evidence labels; the old one described the removed loop. Real organic failure data is nearly empty (live eval era: 0 failed attempts; the 52 "Connection error." job failures are from development sessions). (2) Agency-language signal in `research_policy.py` (`agency_posting` reason; 5 new scenarios, 19 total; replayed on 112 saved postings: caught Huxley, Intec, SThree, remotestar that the name check missed; tuned on that same sample, no live re-measure). (3) `FREEHIRE_REGIONS` env var (default `uk`); non-UK values are unverified, so edge-04 still only tests the empty path. (4) Bug fix: `classify_exception` used `if exception.response`, falsy for 4xx/5xx, so real HTTP errors were all `UNKNOWN`. (5) Then made 429/500/504, `requests.ConnectionError`, non-JSON bodies, `openai.RateLimitError` and 5xx retryable (`RETRY_SAME`, 1s/2s backoff, no `Retry-After`); `insufficient_quota` is `MANUAL_INTERVENTION`. Unit-tested only.
- **Open after Day 20 (needs a decision):** `--resume` skips failed jobs instead of retrying them; categories MISSING_DATA, PARTIAL_COMPLETION, GUARDRAIL_TRIGGERED are never emitted.
- **Day 19 comparison done (Oct 9, user's terminal, 6 queries x 12 applications per model):** `docs/MODEL_COMPARISON.md` has the table and limits. Short version: gpt-4o-mini 6/6 (twice), gpt-4.1-mini 6/6 at 2.85x cost, gpt-5-nano 3/6 and gpt-5.4 (effort low) 3/6 at 32x cost, both failing the FORMAT check on length limits the prompt never states (bullets <=300 chars, letter <=350 words) plus one gpt-5.4 letter with empty bullets. Grounding 100% everywhere, grounding retries 0 everywhere, so the retry-model question is unanswered. No routing default changes. `pricing.json` verified by the user (4 models only). `reasoning_effort` accepted values differ per model: gpt-5.4 rejects `minimal` (400; accepts none/low/medium/high/xhigh); gpt-5-nano accepted `minimal`. Both follow-ups DONE before Day 21: length limits now stated in the prompt (shared `format_rules.py`) and the structure guard. The prompt changed, so the old 19/20 baseline and the Day 19 comparison are not comparable with new runs; Day 21 full live run is the new baseline.
- **Still unproven live:** the runtime grounding guard has only unit tests; in the one live follow-up it never triggered (the model did not fabricate). The earlier real fabrication (niche-02: invented "40%"/"25%" and an Azure-lead claim; CV says Azure foundational) was caught by the eval check.
- **Day 21 checkpoint done:** live run `eval_live_20261009_132309` (user's terminal): 18/20 as run, 19/20 after fixing two addressing-check false positives (slug company name; named-consultant greeting) via `python -m evals.rescore`. $0.0164 for 34 calls ($0.0005/application), mean latency 8.4s, 8/34 researched. Grounding guard, structure guard and the `agency_posting` signal did NOT fire live (unit-tested only). Real defect: letters averaged 173 words, none inside the prompt's 220-300 target (prompt then still said 'concise'; see the next item). Eden Scott (recruiter describing the end client in the third person) was not flagged as an agency by the policy; the model handled it anyway. Record: `docs/BASELINE.md` (Day 21 section) and `docs/baselines/eval_live_20261009_132309.summary.json`.
- **Letter length (measured):** dropping "concise" did not help (re-run `eval_live_20261009_133140`, std-01..06, 6/6 pass: mean 179 words vs 173; pooled 46 letters mean 175, none in 220-300), so the prompt target is now 160-300 (`format_rules.PROMPT_*`), unmeasured. gpt-4o-mini ignores numeric word targets; the old prompt with no numbers gave 226. **Open:** the model comparison predates the prompt change; retry-model question untested.

## How the user wants to work
- **Plan first.** For each day: inspect the code, present findings and a plan, ask the questions that matter, and wait for "go" before changing code. They validate plans.
- **Be honest about limits.** Report what is NOT proven (mock vs live, unit-tested vs measured, estimates vs billing). Flag documentation that claims more than the code does.
- **Confirm before anything that costs money or sends the CV out** (live evals, comparisons). Small, approved probes were fine. Live runs the user triggers themselves are usually run in their own terminal.
- **The user commits.** Docs and CLAUDE.md are updated as part of each day; keep README/PROGRESS truthful.

## Stack
Python 3.10+ (user's terminal; the VS Code sandbox sees 3.13), OpenAI API (default `gpt-4o-mini`), FreeHire API (job search, no key needed), DuckDuckGo via the `ddgs` package (`from ddgs import DDGS`, NOT `duckduckgo_search`), Pydantic, Rich, JSONL for audit trails and checkpoints, pytest. `tiktoken` is declared in pyproject but unused (candidate to remove).

## Setup and running
The user runs everything in their own terminal with the project venv. If the venv breaks after a system Python upgrade, rebuild it from the user's terminal (the sandbox's Python differs, so a venv built there will not work for them; for sandbox testing use a separate scratch venv).
```bash
python3 -m venv --clear .venv && source .venv/bin/activate
pip install -e . pytest          # OPENAI_API_KEY in .env or exported
python -m pytest tests -q        # 243 tests; use "python -m pytest", bare pytest can resolve to ~/.local
python3 -m src.job_agent.main "Forward Deployed Engineer" --cv private/alexandre_cv.md --max-jobs 1
python3 -m src.job_agent.main --keywords examples/keywords.json --cv private/alexandre_cv.md
python3 -m src.job_agent.main "q" --resume --run-id <ID>   # also --list-interrupted, --retry-model, --verbose
python3 -m src.job_agent.view_trace --narrative
python -m evals.runner                              # MOCK: offline, free, validates the harness only
python -m evals.runner --scenarios-only             # 19 hand-labelled tool-selection scenarios, offline
python -m evals.runner --live --max-jobs 2 [--limit N --ids a,b --max-cost 0.50 --yes --retry-model M]
python -m evals.compare --models a,b[,c] [--mock] [--limit 6 --max-cost 0.50]
python -m evals.rescore evals/results/eval_live_<ts>.json   # re-score a saved run with current checks, no API calls
```
Tests never touch the network: `tests/conftest.py` stubs `research_company` for every test.

## Architecture (current code)
A fixed pipeline, NOT an LLM-driven loop (the Day 1-5 loop, 12 guardrails and tiktoken pruning were removed in the Day 11 checkpointing commit; README/PROGRESS were corrected on Day 18; `prompts.py` SYSTEM_PROMPT is imported but unused).
`main.py` (CLI) -> `AgentRunner` -> `search_freehire` -> per job: `research_policy.should_research` -> optional `research_company` (DuckDuckGo) -> `_generate_checked` (`application_generator` via `LLMClient`, grounding guard) -> `report_generator` (Markdown in `reports/`).
Sidecars: `AuditLogger` -> `traces/trace_*.jsonl`; `CheckpointManager` -> `checkpoints/checkpoint_*.jsonl` (checkpointed after search and after every job).
Modules in `src/job_agent/`: agent_runner, application_generator, audit_logger, checkpoint, config (timeouts: LLM 60s, FreeHire 15s, DDG 10s), failures (8-category taxonomy), grounding, llm_client, main, models, pricing (+pricing.json), prompts, report_generator, research_policy, retry (backoff 1s then 2s, max 3 attempts), routing, tools, usage, view_trace, check_openai.
Gitignored: `private/` (real CV), `reports/`, `checkpoints/`, `traces/`, `evals/results/`.

## Behaviours worth knowing
- **FreeHire:** `search_freehire` uses `/api/v1/agent/jobs/search` (the generic `/api/v1/jobs` silently ignores `q`). `FREEHIRE_*` env vars are read at call time. Only `regions=uk` (default; override with `FREEHIRE_REGIONS`, other values unverified) and `posted_within_days=30` are honoured there (`location`/`country` ignored). The trace logs `search_meta` with `ignored_params`; if the query param is ignored it raises `FreeHireIgnoredParamError`. Sources adzuna/whatjobs-uk truncate descriptions to ~500 chars upstream (no way to get the full text), so "thin description" mostly means "truncated".
- **Blank query:** rejected by the CLI (`parser.error`) and `AgentRunner.run` (`InvalidQueryError`, before any search).
- **Research escalation** (`research_policy.should_research`): no company -> skip; agency (name pattern/list: recruit*, staffing, Hays, Ocho, Michael Page, ...) -> skip (`agency`); posting says "our/my client", "the client's office", "on behalf of our client" -> skip (`agency_posting`, checked before cache and length); company already researched this run -> reuse; description >= 600 chars -> skip; else research. The 600 threshold sits in an empty gap (descriptions are <= 501 or >= 1306), so it is not sensitive. Research failure is logged and degrades to a letter without research. `search_duckduckgo` treats ddgs's "No results found" as an empty list. Ad/tracker URLs are filtered. Decisions are `research_decision` trace events and returned as `research_decisions` (in memory only; not restored on resume).
- **Structure guard** (`AgentRunner._repair_structure`, `format_rules.application_defects`): a draft with no bullets, an empty letter, or raw JSON / "generation failed" as the letter is regenerated ONCE (purpose `structure_retry`, routed to the retry model like grounding retries); still defective -> kept with a warning. Events `structure_violation/retry/flagged`. At most 3 LLM calls per job. Limits (3-4 bullets, bullet <=300 chars, letter 150-350 words) live in `format_rules.py`; the PROMPT now states tighter targets (bullet <=240 chars, letter 160-300 words) inside them, so eval and prompt cannot drift (a test checks this). Length is checked by the eval only, not at runtime. Unit-tested; replayed on 106 saved applications (1 hit = the known gpt-5.4 empty-bullets case); never triggered live.
- **Grounding guard** (`AgentRunner._generate_checked`): if the CV has figures and the draft states numbers absent from CV, posting and research text (`grounding.py`, shared with evals), regenerate ONCE with a `revision_note` naming them; if still ungrounded keep the application with `Application.warnings` (report shows "Review needed", CLI warns). Numbers only: an invented skill or employer with no figure is NOT caught (possible later: LLM-judge check).
- **Usage and cost** (Day 19): `LLMClient.usage` (`UsageTracker`) records prompt/completion/cached tokens per SUCCESSFUL call (failed attempts report no usage, so retries are undercounted) and logs `llm_usage`; calls are tagged via `llm_client.tagged(job_id=..., purpose="application"|"grounding_retry")`. `pricing.py` resolves dated snapshot ids to the base model; an unknown model is "unpriced" (excluded and flagged, never guessed). `ModelRouter` uses `--model` for everything, optional `--retry-model` for grounding retries only. `AgentRunner.run` returns `usage`; CLI prints a cost line; the report summary has it.

## Evals (`evals/`)
- `golden_dataset.json` v1.1 (20 queries: 6 standard, 4 niche, 3 broad, 4 edge, 3 agency; per-query `cv_path`, `relevance_keywords`, `min_jobs`, `expected_tools` = freehire only, `expect_failure`); keywords and `min_jobs` are hand-written guesses.
- Run-level checks: status, min_jobs, relevance (>=50% of job TITLES match keywords), search_honored, tools (FreeHire required), tool_sequence (search once and first; extra LLM calls explained by grounding retries), tool_selection, escalation_graceful, no_redundant_research, usage_recorded.
- Per-application checks (query passes only if all applications pass; `score` = share passing): format (3-4 bullets <=300 chars, 3-5 body paragraphs, 150-350 words, no raw JSON/placeholder/fallback text), addressing (names the company, or addressed to a consultant, and references the job title), grounding (numbers only; skipped without CV figures).
- `tool_scenarios.json` + `scenarios.py`: 19 hand-labelled scenarios run offline against the real AgentRunner (mutation-checked: threshold, agency detection and cache bugs make them fail).
- Mock mode (default) uses canned jobs, a fake LLM, fake research and synthetic tokens (~4 chars/token); it validates tooling, never the agent. Only `--live` measures the agent.
- Reports: `evals/results/eval_<mode>_<ts>.md/json`, `compare_<mode>_<ts>.md/json` (gitignored: they contain letters generated from a private CV). Committed record: `docs/BASELINE.md` and `docs/baselines/*.summary.json`.

## Results so far
- Current baseline (Day 21, `eval_live_20261009_132309`, 34 jobs): 18/20 as run, 19/20 re-scored; grounding 100% (guard never fired); 8/34 researched; mean latency 8.4s; $0.0005 per application. Day 18 baseline (`eval_live_20261006_123418`): 19/20, grounding 91% (niche-02 fabrication), predates the guards. Runs are not job-for-job comparable (FreeHire data changes daily). Details and limits in `docs/BASELINE.md`.
- Follow-up live (niche-02, niche-04, agency-02): 3/3; empty-result fix confirmed live; guard did not trigger.
- Earlier live runs found and led to fixes for: FreeHire ignoring the query, blank-query generating applications for random jobs, "no results" counted as failure.

## Known gaps
- Agency detection is name- plus posting-language-based (narrow regex tuned on 112 saved postings; misses postings like Talent International's "technology consultancy"); no letter-level agency eval.
- UK-only search; non-UK dataset queries are weak tests.
- Grounding covers numbers only; relevance is keyword-on-title; small, noisy live samples (one run, non-deterministic model).
- Costs are list-price estimates (pricing.json verified, 4 models only); failed attempts uncounted.
- Checkpoints do not store usage, research decisions or the research cache; resumed runs lose those.
- `tiktoken` dependency unused; `prompts.py` loop prompt unused; README clone URL (`mateador/job-hunter-agent`) not verified.
- Pagination and cross-run job deduplication are not implemented.

## Roadmap
- Week 3: 16-21 done (21 = Week 3 checkpoint, `docs/BASELINE.md`).
- Week 4: 22 pain-point doc, 23 architecture doc, 24 iteration story (good material: the silent FreeHire bug, the Day 11 feature loss, the blank-query bug), 25 engineer pitch, 26 VP pitch, 27 case study assembly, 28 final review and GitHub polish.

## Conventions and lessons
- Preserve public symbols when replacing files (the Day 11 rewrite silently dropped features; check git history before assuming a feature exists).
- Test mocks should accept `**kwargs`. Keep tests offline and isolated. Never let a test reach the network or an LLM.
- Verify claims against the code and live behaviour (the docs overclaimed for weeks; mock results hid a broken search).
- Heuristic checks need synthetic bad fixtures AND a replay against real saved data; a test caught a real flaw in a "fix" (consultant detection matched the job title).
- When a check never fails on real data, say so: it is proven only by synthetic fixtures.
- Prefer partial completion over all-or-nothing. Cover letters need human review. Single LLM provider (OpenAI) by design for now.
