# Project Log

A day-by-day record of what was built, reconstructed from the git history and the other documents. It replaces the Day 14 progress report, which described features the code no longer had (see `docs/ITERATION_STORY.md`). For the current design read `docs/ARCHITECTURE.md`; for the argument read `docs/CASE_STUDY.md`.

How to read the dates: "Day N" is the project's numbering. Calendar dates are the dates of the commits, so several days often share one date, and there is an 18-day gap between Day 14 (Sept 14) and Day 15 (Oct 2). Commits from Sept 1 to Sept 7 cover Days 1 to 7 and are not mapped to single days.

## Week 1: Build the loop (Days 1-7), Sept 1-7

| Day | What happened | Outcome today |
|---|---|---|
| 1-3 | A model-driven agent: the model chose tools in a loop, searched FreeHire and researched companies, with a step limit and several guardrails (`9b4d767`, `d205b61`, `7153280`) | The loop was removed on Day 11. The `regions=uk` and `posted_within_days=30` search defaults remain |
| 4 | Context management: token counting and pruning (`f77c550`) | Removed on Day 11; the `tiktoken` dependency was dropped on Day 23 |
| 5 | JSONL audit trail and trace viewer (`9db89bf`) | Kept. Prompts were redacted from it on Day 26 |
| 6 | Application generation: tailored CV bullets and cover letters, consolidated Markdown report (`e6af5f9`) | Kept |
| 7 | Week 1 checkpoint (`0e4b9f6`) | Recorded as complete; the Day 11 rewrite changed what "complete" meant |

## Week 2: Make it survive failure (Days 8-14), Sept 8-14

| Day | What happened | Outcome today |
|---|---|---|
| 8 | Failure taxonomy: categories and retry policies (`572a691`) | Reduced to the 6 categories the code emits (Day 23) |
| 9 | Bounded retry with exponential backoff, 3 attempts (`5d7d26a`). The search URL also changed in this commit (see Day 16) | Kept; backoff measured against the real API on Day 22 (1.01 s, then 2.01 s) |
| 10 | Timeouts on all external calls (`68682bb`). The HTTP-error classification bug was introduced in this commit | Timeouts kept; the bug was fixed on Day 20 |
| 11 | Checkpointing after every job (`1a96f6d`). **The same commit silently replaced the model loop with a fixed pipeline and disconnected the CV, research and job selection** | The fixed pipeline is the current design. The CV reached the generator again on Day 15 and research on Day 18 |
| 12 | Robust resume: state validation, interrupted-run detection (`783d59f`) | Kept. Resume skipped failed jobs until Day 22 |
| 13 | Partial completion: failed jobs recorded, run continues | Kept |
| 14 | End-to-end recovery demo and progress report (`54f912d`) | The demo ran on mocks and the report overclaimed (corrected on Day 18) |

## Week 3: Measure (Days 15-21), Oct 2-9

| Day | Date | What happened | Evidence |
|---|---|---|---|
| 15 | Oct 2 | Golden dataset of 20 queries in 5 categories; `--cv` and `--keywords` restored and the CV passed to the generator again (`244c5de`, `7242aaf`) | Unit |
| 16 | Oct 6 | Eval harness (mock and live) and scoring. The first live run showed FreeHire was ignoring the search query; fixed, with a check that raises if it happens again (`da0ee5e`). Blank queries rejected (`2efff5c`) | Live |
| 17 | Oct 6 | Per-application checks: format, addressing, number grounding (`e456fd8`) | Unit and live |
| 18 | Oct 6 | Deterministic research policy with 19 hand-labelled scenarios; first live baseline (19/20) caught one real fabrication; runtime grounding guard added; docs corrected (`17f13d2`, `56ceffc`) | Unit; live |
| 19 | Oct 7-9 | Token and cost tracking, model router, four-model comparison (`56ceffc`, `da83d90`) | Live |
| 20 | Oct 9 | Failure taxonomy rewritten with evidence labels; agency-language signal; HTTP classification bug fixed and more errors made retryable; structure guard (`da83d90`) | Unit |
| 21 | Oct 9 | Week 3 checkpoint: live baseline, 18/20 as run, 19/20 re-scored, about $0.0005 per application (`docs/BASELINE.md`) | Live |

## Week 4: Communicate and defend (Days 22-28), Oct 19 onward

| Day | What happened | Evidence |
|---|---|---|
| 22 | `docs/PAIN_POINT.md`. Live re-run (17/20 as run, 18/20 re-scored). Induced faults and a live guard experiment found and fixed two bugs: resume skipped failed jobs, and an empty model reply killed a job (`7b627e2`) | Live; induced |
| 23 | `docs/ARCHITECTURE.md`. Auth and quota errors stop the run, real attempt counts, OpenAI 400/404 classified, unused code and categories removed (`45ea120`) | Unit; induced |
| 24 | `docs/ITERATION_STORY.md` (`45ea120`) | n/a |
| 25 | `docs/PITCH_ENGINEER.md`, a 10-minute script. A README audit led to a fix: `--resume` now works without repeating the query, and refuses to resume a CV run without `--cv` (`9bb5fb3`) | Unit |
| 26 | `docs/PITCH_VP.md` and one slide, tailored to the target job description. Found and fixed: the audit trail stored the full prompt, CV included (`43ccc3a`) | Unit |
| 27 | `docs/CASE_STUDY.md`, this log rewritten, README as a landing page, consistency pass | n/a |
| 28 | Final review: personal details removed from the prompt (optional `--candidate-note`), fictional example CV, MIT licence, CI workflow, packaging metadata, clean-copy install and test run, headline numbers recomputed from the saved results (one latency figure corrected) | Unit; verified on a clean copy |

## Current state

The headline numbers, with how each was obtained, are in the table in `docs/CASE_STUDY.md`. The detail is in `docs/BASELINE.md` (live runs), `docs/FAILURE_TAXONOMY.md` (failures) and `docs/baselines/` (committed result tables). Setup and commands are in `README.md`.
