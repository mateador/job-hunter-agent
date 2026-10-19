# Iteration Story: What v1 Got Wrong and How It Was Fixed

Third-person account of how the project changed between 2026-09-01 and 2026-10-19, reconstructed from the git history (hashes in brackets), the correction notes in the docs and the stored eval runs. Where the record is silent, this says so. Evidence labels as in `docs/ARCHITECTURE.md`: **Unit**, **Induced**, **Live**.

## The shape of the story

The project began as a model-driven agent with many guardrails and finished as a fixed pipeline with few guards, each one tested against the way it actually fails. The reason is not that the early design was clumsy. Most of its defects were invisible: mocks passed, tests passed, documents said "complete", and the real behaviour was different. Nearly every important fix came from running the real thing, reading its output, or breaking it on purpose.

## v1 (Sept 1-7): a model-driven agent

By Day 7 [`0e4b9f6`] the system was an LLM loop: the model chose the next tool, searched FreeHire, picked at most two promising jobs, researched at most two companies, and returned a final answer in which each match had to quote evidence from the CV (`cv_evidence`). Around it sat an input check, a step limit (8), a research budget, JSON repair, context pruning at 30,000 tokens, a Pydantic schema and an audit trail. The Day 14 README listed twelve guardrails, and the Day 14 progress report said they "prevent LLM hallucination".

Two things about that claim. Of the twelve, one concerned the truth of the content (`cv_evidence`); the others were input validation, limits, defaults and parsing. And that one was removed four days after v1 (below).

## Turning points

### 1. The Day 11 rewrite that nobody noticed (Sept 11, `1a96f6d`)
**Belief:** adding checkpointing. The commit message says only that.
**What the diff shows:** a +457/−411 rewrite of `agent_runner.py` that also removed the model-driven loop and `max_steps`, the research budget, JSON repair, context pruning, and the model's selection of jobs against the CV. Company research was disconnected (the new runner imports the search function and never calls it). The CLI lost `--cv` and `--keywords`. Most consequentially, `generate_application` was called **without the CV**, so from Day 11 to Day 14 the letters were written from a placeholder profile ("Candidate", 5 years, a generic skills list).
**What the docs said meanwhile:** the Day 14 README still showed `--cv ... --keywords ...` usage that the CLI no longer accepted, and the Day 14 progress report described tailored letters, company research, context pruning and "12 guardrails" as working. The recovery demo of Day 14 passed, because it ran on mocks.
**Found:** Day 18 (Oct 6), when the progress report was re-read against the code [`17f13d2`]. The CV reached the generator again on Day 15 [`7242aaf`]; research returned on Day 18 as a deterministic policy.
**Lesson kept:** preserve public symbols when replacing a file, and check git history before assuming a feature exists.

### 2. The search that ignored the query (Day 9 to Day 16)
**Record:** on Day 7 the search URL was `freehire.me/api/v1/agent/jobs/search`. On Day 9 [`5d7d26a`] it became `api.freehire.com/agent/jobs/search`, a different host. On Day 15 [`7242aaf`] it became `freehire.me/api/v1/jobs`, a generic endpoint that **silently ignores the `q` parameter** and returns an unfiltered feed.
**Not recorded:** whether the Day 9 host ever served results. Nothing in the history says, and no live run was made.
**Found:** the first live eval on Day 16 (Oct 6) [`da0ee5e`]. Mock mode, which uses canned jobs, had hidden it.
**Fix:** back to the agent search endpoint; the code now reads `ignored_params` from the response and raises if the query parameter is ignored; an eval check (`search_honored`) and a relevance check (job titles match the query) would fail if it happened again.

### 3. A blank query produced letters for random jobs (Oct 6, `2efff5c`)
The same unfiltered feed meant an empty query returned arbitrary jobs, and the agent wrote applications for them. It was found by reading the output of the live eval's blank-query case. The CLI and the runner now reject a blank query before any search. **Unit**, and the eval case stays in the dataset.

### 4. Every HTTP error was `UNKNOWN` (introduced Sept 8, fixed Oct 9, `da83d90`)
The classifier tested `if exception.response`. A `requests.Response` with a 4xx or 5xx status is falsy, so the status code was lost and every real HTTP error fell through to `UNKNOWN` and was never retried. A 503 from FreeHire, or a 401, was treated the same as a typo. The tests used mock responses that were truthy. It was found by reading the code while writing the failure document on Day 20. Fixed with `is not None`; the regression test uses real `Response` objects and fails without the fix. During the same review the retry gaps for 429, 5xx, connection errors and non-JSON bodies were closed.

### 5. The model invented figures (Oct 6, Day 18 baseline)
The first full live run (`eval_live_20261006_123418`) had one query, `niche-02`, where a letter claimed reductions of 40% and 25% and an Azure leadership role the CV did not support. The eval's grounding check caught it; nothing at runtime did. A runtime guard was added [`17f13d2`, `56ceffc`]: figures absent from the CV, the posting and the research trigger one regeneration, then a "Review needed" warning.
**What is known now:** over two later eval runs (68 applications) the model never triggered the guard. On Day 22 the guards were provoked on purpose with the live model: the grounding guard recovered 3 of 3 violations, one of which the model produced without being asked. The guard covers numbers only; an invented skill or employer without a figure is not caught. **Induced.**

### 6. Letters ignored the length the prompt asked for (Oct 9)
The prompt asked for 220-300 words. Across 34 letters the mean was 173 and none was inside the range. Removing the word "concise" did not help (46 letters, still none). The model does not follow numeric word targets, so the target was lowered to 160-300, which means it was moved to where the model already writes. On the Day 22 re-run, 2 of 34 letters were still under the 150-word floor. The lesson is that the target followed the behaviour, not the other way round, and the 150-word floor itself is a rule chosen by the author, not a measured quality line.

### 7. Two bugs found by breaking things on purpose (Day 22)
Organic failures were nearly absent from the live runs, so faults were injected: scripted transports raising the real exception types, against the real pipeline.
- **`--resume` skipped failed jobs.** A failed job was recorded as processed, so a resumed run never tried it again and stayed `partial`. The tests that were meant to document this passed by accident: after the fix, an `AssertionError` placed in their mock was swallowed by the runner's own error handling, so the tests passed for the wrong reason. They were rewritten.
- **A model reply with `content=None` failed the job as `UNKNOWN`,** because the fence-stripping function raised before the structure guard could see a draft. It now goes to the guard.
Both were reproduced, fixed and pinned by tests. On Day 23 the same exercise led to stopping the run on authentication or quota errors instead of making a doomed call for every remaining job.

### 8. The measuring instrument was also wrong
Two of the addressing check's failures on real letters were false positives: the company field held a slug (`foundationhealthcareers`, then `Hsogroupbv`) while the letter correctly used the trading name, and a letter addressed to a named consultant was not recognised. Each was fixed and re-scored on the same data, which is stated as a limit in the baseline, because a fix made after seeing the failures proves the check, not a fresh measurement.

### 9. The audit trail stored the CV (found and fixed on Day 26)
While preparing a security answer for the pitch, a real trace file was opened and the full prompt, CV text included, was in it: the retry layer logged its keyword arguments, and the arguments of a model call are its messages. Traces are gitignored, so nothing had leaked, but an audit trail that holds private data is not something a service could keep. It now logs only a length and a short hash for long strings and chat messages, and a test fails if the CV or the posting text reaches the trace. Traces written before the fix still contain the CV, and checkpoints and reports still hold the generated letters.

## What the failures have in common

1. **Green did not mean working.** The Day 14 demo, mock mode, truthy mock responses and the tests that asserted the resume bug all passed while the behaviour was wrong. Mock results validate the harness; only live runs measure the agent.
2. **The documents ran ahead of the code, for weeks.** Claims about guardrails, research, CV tailoring and a working CLI were written before, or after the removal of, the thing described. Correction came from re-reading the docs against the code.
3. **Defects were found by provoking, not by waiting.** Organic failure data stayed nearly empty; deliberate faults found two bugs in one session.
4. **Heuristic checks need synthetic bad cases and a replay on saved real data**, and a check that never fails on real data should be described as proven only by its fixtures.
5. **Count what is being claimed.** "12 guardrails" sounded like a defence against hallucination; one of them concerned content.

Practices adopted: label evidence as Unit, Induced or Live; report what is not proven next to what is; keep the tests offline; preserve public symbols when rewriting; and update README, PROGRESS and the architecture document in the same change as the code.

## What is still wrong

- Grounding is numbers only, and the "ship with Review needed" path for a figure has been exercised only by unit tests.
- The organic rate of fabrication and of failures is unknown: 0 in 68 eval applications, no real failed attempts in the live era.
- Whether a stronger retry model is worth its cost is unanswered.
- Agency detection is heuristic and misses some agencies; the model compensates in the cases seen.
- About 2 of 34 letters are shorter than the floor; the model ignores numeric word targets.
- Samples are small (34 jobs per run, one CV, one non-deterministic model), and the spread between two identical runs was about two queries out of twenty.
- Search is UK only, and the history before Day 15 contains no record of whether the Day 9 search host ever worked.

## Reference: the commits behind each section

| Section | Commit | Date |
|---|---|---|
| v1 complete | `0e4b9f6` | Sept 7 |
| Search host changed | `5d7d26a` | Sept 8 |
| HTTP classification bug introduced | `68682bb` | Sept 8 |
| Day 11 rewrite | `1a96f6d` | Sept 11 |
| CV restored, generic endpoint introduced | `7242aaf` | Oct 2 |
| Search fixed, ignored-param detection | `da0ee5e` | Oct 6 |
| Blank-query rejection | `2efff5c` | Oct 6 |
| Docs corrected; grounding guard begins | `17f13d2` | Oct 6 |
| Grounding guard extended | `56ceffc` | Oct 7 |
| HTTP classification fixed, structure guard, agency signal | `da83d90` | Oct 9 |
| Resume and `content=None` fixes, stress harness | `7b627e2` | Oct 19 |
