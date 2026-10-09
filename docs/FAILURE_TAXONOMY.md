# Failure Modes and Taxonomy

What goes wrong in this system, how it is detected, what it does about it, and what the
evidence is. Rewritten on Day 20: the Day 8 version described a design (JSON repair loop,
context pruner, research budget) that no longer exists, so it contradicted the code.

Code: `src/job_agent/failures.py` (classification), `retry.py` (retry), `agent_runner.py`
(per-job isolation, grounding guard, research degradation), `checkpoint.py` (recovery).

## How to read this

Every claim carries an evidence label:

| Label | Meaning |
|---|---|
| **Live** | Seen in a real run against the live APIs |
| **Dev** | Seen once in development traces; cause not fully recorded |
| **Unit** | Behaviour covered by offline tests only; never triggered organically |
| **None** | Not observed; the handling is design intent |

### What data exists (and its limits)

- 83 trace files: 30 in `traces/` (development, Sep 23 to Oct 2) and 53 from the live eval runs of Oct 6.
- The live eval era is clean: 53 FreeHire searches and 98 LLM calls all succeeded on the first attempt. 15 of 17 DuckDuckGo lookups succeeded; the 2 "failures" were "No results found", since reclassified as empty results. **The retry path has never been exercised by an organic failure in the live era.**
- The only large failure cluster is development: **52 `job_failed` events reading "Connection error."** across 26 sessions on 2026-09-23 and 2026-10-02. 39 were classified `UNKNOWN` and 13 `TIMEOUT` (the Day 15 change made dropped connections a timeout). The cause (network down, or a deliberate fault test) is not recorded.
- Other `job_failed` events: 3 `Job` validation errors (missing `id`, first session) and 1 test-mock bug (`process() takes no keyword arguments`, Oct 2).
- So the system has **no meaningful organic failure frequencies**. Most real problems were found by evals or by reading output, not by exceptions (see "Silent failures" below). One 20-query baseline (34 jobs) is the only quality sample.

## Part 1: Exceptions (classified and handled)

### What the classifier actually produces

The taxonomy has 8 categories. `classify_exception` emits only some of them:

| Category | Emitted today by | Retry policy (as implemented) |
|---|---|---|
| `TIMEOUT` | `TimeoutError`, `requests.Timeout`, `openai.APITimeoutError`, `openai.APIConnectionError`, HTTP 408 | `RETRY_SAME`: up to 3 attempts, backoff 1s then 2s |
| `DEAD_API` | HTTP 429/500/502/503/504, `requests.ConnectionError`, `openai.RateLimitError`, `openai.InternalServerError` | `RETRY_SAME`, as above |
| `AUTH_ERROR` | HTTP 401/403, `openai.AuthenticationError`, `PermissionDeniedError`, `RateLimitError` with `insufficient_quota` | `NOT_RETRYABLE` (quota: `MANUAL_INTERVENTION`), fails immediately |
| `MALFORMED_RESPONSE` | HTTP 400 (not retried); non-JSON body (retried like `RETRY_SAME`) | see left |
| `CONTEXT_OVERFLOW` | OpenAI error containing `context_length_exceeded` | `RETRY_MODIFIED`: one retry with the message history halved |
| `UNKNOWN` | everything else (e.g. HTTP 404, `ValueError`) | `NOT_RETRYABLE` |
| `MISSING_DATA`, `PARTIAL_COMPLETION`, `GUARDRAIL_TRIGGERED` | **nothing** (defined, never emitted) | n/a |

The three unused categories are aspirational. Their situations are handled (see Parts 2 and 3) but not
labelled with the category. `failures.py` was left unchanged for that reason.

### Bug found and fixed on Day 20

`classify_exception` tested `if exception.response`, but a `requests.Response` with a 4xx or 5xx status is
**falsy**. Every real HTTP error therefore lost its status code and fell through to `UNKNOWN` /
`NOT_RETRYABLE`. The 401/403, 502/503 and 400 branches could not run on real responses, and a 503 from
FreeHire was never retried. Nothing tested HTTP classification, so nothing noticed. Fixed with
`is not None`; `tests/test_failures.py` uses real `Response` objects and fails without the fix.
Evidence: **Unit** (found by inspection, not by a live failure).

### Retry gaps closed on Day 20

Before Day 20, FreeHire 429/500/504, `requests.ConnectionError`, `openai.RateLimitError`, OpenAI 5xx and
non-JSON bodies were all `UNKNOWN` / not retried (verified by running each exception through the classifier).
They are now retried (tests in `tests/test_failures.py`, plus an end-to-end retry through `search_freehire`).
Evidence: **Unit** only; none of these errors occurred in the live runs.

Limits of the new handling:
- Backoff is 1s then 2s. That is short for a real rate limit, and `Retry-After` is not read, so a sustained 429 will still fail the job after 3 attempts.
- `insufficient_quota` also arrives as a 429, so it is checked first and is not retried.
- The OpenAI client is built with `max_retries=0`, so only this retry layer applies (no double retrying).
- The retry only wraps the FreeHire and LLM calls. A failed job is still not retried on `--resume`.

### Failure catalogue

| # | Failure | Detection | Handling | Evidence |
|---|---|---|---|---|
| E1 | LLM unreachable / timeout (60s) | `openai` exceptions -> `TIMEOUT` | 3 attempts with backoff; if all fail, the **job** fails and is recorded in `failed_jobs`; other jobs continue; run ends `partial` (or `failed` if none succeeded) | Dev: 52 events ("Connection error."); **Live: none** |
| E2 | FreeHire unreachable, rate limited or 5xx | `requests` exceptions | 429/5xx/connection/timeout: 3 attempts with backoff. 400/401/403/404: fail at once. If search fails, the run fails with nothing to salvage | Unit; none observed |
| E3 | OpenAI auth failure | `AuthenticationError` -> `AUTH_ERROR` | Fails immediately, no retry. The CLI prints the error and a resume hint | Unit; none observed |
| E4 | Context too long | `context_length_exceeded` | One retry with history halved. A single prompt is one system plus one user message, so halving cannot shrink it: effectively unreachable | Unit; none; likely dead code |
| E5 | Job missing `id` or invalid (`Job` validation) | Pydantic `ValidationError` -> `UNKNOWN` | Job recorded as failed, run continues | Dev: 3 events |
| E6 | Company research fails or is empty | DuckDuckGo exception | Logged as `research_failed`, letter generated **without** research (never fails the job). "No results found" is an empty result, not a failure | **Live**: 2 of 17 lookups were empty, 0 real failures |
| E7 | Process killed (Ctrl-C, crash) | n/a | Checkpoint written after search and after every job; `--resume --run-id` continues. Ctrl-C prints the resume command | Unit; manual demo (`test_recovery_demo`) |
| E8 | Corrupted or missing checkpoint on resume | `CorruptedCheckpointError`, `ResumeError` | `resume_failed` event and a clear CLI error, exit 1; no silent restart | Unit |
| E9 | Blank query | CLI `parser.error`; `InvalidQueryError` before any search | Rejected, no API call | **Live**: caused the original bug (see S2); now Unit |

Gaps in recovery:

- **`--resume` does not retry failed jobs.** A failed job is added to `jobs_processed`, so a resumed run skips it. To retry E1 failures you must start a new run.
- **No cross-run recovery of partial research.** Checkpoints do not store usage, research decisions or the research cache, so a resumed run loses them (cost and escalation figures are then incomplete).
- **Failed LLM attempts report no usage**, so retries are undercounted in cost figures.

## Part 2: Silent failures (no exception, wrong output)

These matter more than Part 1: none raises an error, and each was found by an eval or by reading output.

| # | Failure | Detection | Handling | Evidence |
|---|---|---|---|---|
| S1 | **FreeHire silently ignores the query** (generic endpoint returned unrelated jobs) | `search_meta.ignored_params` in the response; eval `search_honored` and `relevance` | Switched to the agent search endpoint; `FreeHireIgnoredParamError` if the query param is ever ignored again | **Live**: found in the first live run |
| S2 | **Blank query generated applications for random jobs** | Reading output | Rejected in CLI and `AgentRunner.run` | **Live**: found once |
| S3 | **Fabricated figures** ("reduced deployment times by 40%", "25%") plus an unsupported Azure-lead claim | Eval `grounding` check; runtime guard regenerates once, then flags "Review needed" | Guard: Unit only | **Live**: 1 query of 20 (niche-02), 1 of 34 jobs; guard never triggered live |
| S4 | **Invented skill, employer or claim with no number** | Not detected | None. The grounding check covers numbers only | Known gap; the Azure claim above was caught only because it came with figures |
| S5 | **Agency treated as an employer.** Letter is addressed to a recruiter, which is researched for nothing | `research_policy`: company-name pattern, plus (Day 20) posting language such as "our client" or "the client's office" | Skipped (`agency` / `agency_posting`). The letter is still generated; no letter-level agency check exists | **Live**: 6 of 34 jobs flagged by name; "Intec Select Ltd" slipped through |
| S6 | **Truncated postings.** Two aggregator sources cut descriptions to about 500 characters | Description length | Triggers company research (cannot recover the missing role detail) | **Live**: about two thirds of sampled descriptions |
| S7 | **Search returns zero jobs** | `jobs_found == 0` | Reported as an empty result, not a failure | **Live** (Lisbon query) |
| S8 | **Non-UK queries are not searched at all.** `regions` was hard-coded to `uk` | None | Day 20: `FREEHIRE_REGIONS` env var (default `uk`). Whether FreeHire accepts other values is unverified, so non-UK behaviour is untested | Known limit |
| S9 | **Model writes a letter that fails format/addressing** (bullets, length, company name, raw JSON, placeholder text) | Eval `format` and `addressing` checks | Length: the prompt now states the limits (Day 20); eval only. Unusable output: see S11 | **Live**: 17 of 17 evaluated passed in the baseline; in the Day 19 comparison `gpt-5-nano` and `gpt-5.4` failed 4 of 12 applications each on length limits the prompt had not stated (`docs/MODEL_COMPARISON.md`) |
| S11 | **Unusable output: no CV bullets, empty letter, raw JSON or placeholder as the letter.** `application_generator` used to turn missing bullets into `[]` silently | `format_rules.application_defects` at runtime | One regeneration (`structure_retry`), then kept with a "Review needed" warning. A grounding retry that loses its bullets is warned about, not retried (at most 3 calls per job) | **Live**: 1 of 106 saved applications (`gpt-5.4`, empty bullets). Guard: Unit only, never triggered live |
| S10 | **Relevance drift** (loosely related job accepted) | Keyword match on job titles | Eval only | Known limit; keywords are hand-written guesses |

### Agency-language signal (Day 20)

Added as a second agency check in `research_policy.py`, run after the name check and before the
"already researched" and "rich description" rules. It matches singular "our/my ... client",
"the client's office/site/premises", "on behalf of our client", and "acting as an employment
agency/business". It deliberately does not match "our clients", "Client Success Team", "client projects" or
"on behalf of senior leadership".

Replay over the 112 distinct job postings in saved data: 7 companies flagged. Three were already caught by
name (GCS Recruitment, Ocho, Ocho People); **four were not** (Huxley Associates, Intec Select, SThree UK,
remotestar-team). No false positives among the other 105 postings, which include many "our clients" and
"client" uses. Known miss: Talent International UK, whose posting says "a leading technology consultancy"
without "our client". The pattern was tuned on these same 112 postings, so the zero-false-positive result
is a fit to this sample, not an out-of-sample rate. Treat it as: catches the common recruiter boilerplate;
will miss postings that avoid it and may flag an employer that happens to write "our client".

## Part 3: Design stance

1. **Isolate the job.** One job failing never stops the run; every outcome is recorded with a category.
2. **Optional steps degrade.** Research failing means a letter without research, never a failed job.
3. **Checkpoint after every unit of work**, so a crash loses at most one job.
4. **Bounded retries only**: 3 attempts, 1s then 2s backoff; `RETRY_MODIFIED` retries once.
5. **Partial results are the product**: `completed`, `partial` and `failed` are distinct end states.
6. **Do not guess**: unpriced models are excluded and flagged; ungrounded figures are flagged, not hidden.

## What is not proven

- Retry, backoff and resume recover from real faults only in unit tests and one development session. No live run has hit a real transient failure.
- The runtime grounding and structure guards have never triggered live.
- No frequencies above are rates for production use: the live sample is 20 queries, 34 jobs, one CV, one run.
- Of the 8 categories, 3 are never emitted and 1 (`CONTEXT_OVERFLOW`) is probably unreachable.
- The retry behaviour for 429/5xx/connection errors was added without a real occurrence to test against.
