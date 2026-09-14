# Job Hunter Agent — Progress Report (Day 14 Checkpoint)

**Project Duration:** 14 of 30 days  
**Status:** Production-ready foundation complete  
**Last Updated:** 2026-09-14

---

## Executive Summary

We've built a resilient, observable AI agent for job hunting that can survive crashes, resume from checkpoints, and deliver partial results when individual jobs fail. The agent has processed real job listings through the FreeHire API, generated tailored cover letters and CV bullets via GPT-4o-mini, and maintained a complete audit trail of every decision.

**Key achievement:** The agent can be killed mid-run (simulating OOM, network failure, or user interruption) and resume exactly where it left off, with full observability into what happened before and after the crash.

---

## What's Been Built

### Week 1: Core Agent (Days 1–7)

| Day | Feature | Files |
|-----|---------|-------|
| 1 | Agent loop with tool execution | agent_runner.py, main.py |
| 2 | FreeHire API integration | tools.py |
| 3 | DuckDuckGo research tool | tools.py |
| 4 | 12 guardrails for LLM output | agent_runner.py |
| 5 | Context pruning to prevent overflow | agent_runner.py |
| 6 | Tailored CV bullets + cover letters | application_generator.py |
| 7 | JSONL audit trail + Markdown report | audit_logger.py, report_generator.py |

**Outcome:** Working agent that searches for jobs, researches companies, and generates application materials.

### Week 2: Production Hardening (Days 8–14)

| Day | Feature | Files |
|-----|---------|-------|
| 8 | Failure taxonomy (8 categories) | failures.py, docs/FAILURE_TAXONOMY.md |
| 9 | Retry with exponential backoff | retry.py |
| 10 | Timeout enforcement on all calls | config.py |
| 11 | Checkpointing (JSONL state persistence) | checkpoint.py |
| 12 | Robust resume with validation | checkpoint.py, agent_runner.py |
| 13 | Partial completion with failure tracking | models.py, report_generator.py |
| 14 | Recovery demo + checkpoint README | tests/test_recovery_demo.py, docs/PROGRESS.md |

**Outcome:** Agent that survives crashes, resumes cleanly, and delivers partial results instead of failing entirely.

---

## Architecture Decisions

### Why JSONL for audit trails and checkpoints?

**Decision:** Use JSONL (one JSON object per line) instead of SQLite or a single JSON file.

**Tradeoffs considered:**
- SQLite: Better for queries, but adds a dependency and makes the trace harder to inspect manually
- Single JSON file: Simpler, but can't append incrementally (must rewrite entire file)
- JSONL: Append-only, human-readable, easy to grep, no dependencies

**Why JSONL won:**
1. **Append-only writes** mean we never lose data on crash (no partial writes)
2. **Human-readable** — you can `tail -f` the trace during a run
3. **No dependencies** — just Python's built-in `json` module
4. **Easy to process** — `jq`, `grep`, or Python can parse it line-by-line

### Why bounded retry (3 attempts max)?

**Decision:** Retry with exponential backoff, but cap at 3 attempts.

**Tradeoffs considered:**
- Infinite retry: Could eventually succeed, but risks infinite loops and unbounded cost
- No retry: Fast failure, but wastes work on transient errors
- Bounded retry: Balances resilience with predictability

**Why 3 attempts:**
1. Most transient errors (timeouts, 503s) resolve within 1-2 retries
2. 3 attempts with exponential backoff (1s, 2s, 4s) = ~7 seconds max wait
3. After 3 failures, it's likely a persistent issue (auth, malformed request) that won't resolve itself
4. Keeps the agent responsive — you don't want to wait 5 minutes for a job that will never succeed

### Why centralized timeout config?

**Decision:** All timeouts in `config.py`, not hardcoded in tools.

**Tradeoffs considered:**
- Hardcoded: Simpler, but hard to tune
- Per-call config: Flexible, but inconsistent
- Centralized: Single source of truth, easy to tune

**Why centralized:**
1. **Easy to tune** — change one file, all timeouts update
2. **Consistent** — no tool accidentally uses 300s timeout
3. **Observable** — you can log all timeout values at startup
4. **Testable** — tests can verify timeout values are reasonable

### Why checkpoint after every job?

**Decision:** Save checkpoint after search, after each job, and at completion.

**Tradeoffs considered:**
- Checkpoint at start only: Minimal overhead, but loses all work on crash
- Checkpoint after every job: More I/O, but survives crashes mid-run
- Checkpoint at end only: No crash recovery

**Why every job:**
1. **Survives crashes** — if job #8 fails, you don't lose jobs #1-7
2. **Enables resume** — you can pick up exactly where you left off
3. **Minimal overhead** — JSONL append is fast (< 1ms)
4. **Observable** — you can inspect checkpoint state at any time

---

## Current State

### Working Features

- Agent searches FreeHire API for jobs
- Agent researches companies via DuckDuckGo
- Agent generates tailored cover letters and CV bullets
- 12 guardrails prevent LLM hallucination
- Context pruning prevents overflow
- JSONL audit trail tracks every decision
- Markdown report consolidates results
- Failure taxonomy classifies 8 error categories
- Retry with exponential backoff (3 attempts max)
- Timeout enforcement on all external calls
- Checkpointing after every job
- Robust resume with state validation
- Partial completion (delivers results even if some jobs fail)
- Recovery demo proves kill/resume works end-to-end

### Test Coverage

- 31 tests across 5 test files
- All tests passing
- Coverage includes: retry logic, timeout classification, checkpoint save/load, resume scenarios, partial completion, full recovery cycle

### Known Limitations

- No cost tracking yet (Day 19)
- No eval harness yet (Days 15-16)
- No model routing yet (Day 19)
- Agent doesn't yet handle pagination (only first page of results)
- No deduplication of jobs across runs

---

## What's Next

### Week 3: Measure and Optimize (Days 15–21)

- **Day 15:** Golden dataset (20 real queries with expected outputs)
- **Day 16:** Eval harness (automated runner + scoring)
- **Day 17:** Correctness + format evals
- **Day 18:** Tool selection + escalation evals
- **Day 19:** Cost measurement + model routing
- **Day 20:** Failure mode documentation
- **Day 21:** CHECKPOINT — Eval report with pass rates, cost per run

### Week 4: Communicate and Defend (Days 22–28)

- **Day 22:** Pain point + why AI belongs (one-page narrative)
- **Day 23:** Architecture + decisions doc
- **Day 24:** Iteration story (what v1 got wrong, how it was fixed)
- **Day 25:** Engineer pitch rehearsal (10-min recording)
- **Day 26:** VP pitch rehearsal (5-min recording)
- **Day 27:** Case study assembly
- **Day 28:** Final review + publication to GitHub

---

## How to Run

### Quick Start

Install dependencies:

    pip install openai duckduckgo-search pydantic rich tiktoken requests pytest

Set API key:

    export OPENAI_API_KEY="your-key-here"

Run agent:

    python -m src.job_agent.main "python engineer london" --max-jobs 5

View audit trail:

    python -m src.job_agent.view_trace --narrative

List interrupted runs:

    python -m src.job_agent.main --list-interrupted

Resume from checkpoint:

    python -m src.job_agent.main "python engineer london" --resume --run-id <RUN_ID>

### Run Tests

    pytest tests/ -v

### Run Recovery Demo

Programmatic demo (no manual intervention):

    pytest tests/test_recovery_demo.py -v -s

Manual demo (interactive):

    bash scripts/demo_recovery.sh

---

## Metrics

- **Lines of code:** ~2,500 (excluding tests)
- **Test count:** 31
- **Files:** 14 Python modules, 5 test files, 2 docs
- **External dependencies:** 6 (openai, duckduckgo-search, pydantic, rich, tiktoken, requests)
- **Days elapsed:** 14 of 30
- **Days remaining:** 16

---

## Contact

This project is part of a 30-day Forward Deployed Software Engineer case study. For questions or feedback, see the full case study (coming Day 28).