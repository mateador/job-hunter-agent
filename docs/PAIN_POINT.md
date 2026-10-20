# The Pain Point, and Why AI Belongs (and Where It Does Not)

## The pain

I am looking for work, and a good application is not one task but four. I search several job sources, read each posting, research the company behind it, and match my CV against what the role asks for. Then I write a letter that says something true about me and relevant to that posting. Doing this by hand for each posting is slow and repetitive, and the quality of the tenth letter of the day is worse than the first.

<!-- TODO (author): add one or two sentences of your own numbers, e.g. how many postings you screen per week and how long one application takes. I have no measured figure for this, so none is stated here. -->

The obvious fix is to hand the whole thing to a language model. That fix has a cost, and the cost is what this project is about: a model that writes a letter will also, sometimes, invent a figure on my CV, write to a recruiter as if they were the employer, or return something broken and present it as finished. A letter sent under my name with a made-up "40% improvement" is worse than no letter.

## Why AI belongs here

Drafting a tailored letter from a CV and a posting is the one step that is real language work. Rules cannot do it, and a model does it for about $0.0005 per application (list price, `gpt-4o-mini`), with a whole query that drafts two letters (search, optional research, two LLM calls) taking about 10 seconds.

## Where AI does not belong

The first version let the model drive: an LLM loop chose which tool to call next, behind a stack of guardrails. It was removed on Day 11. What replaced it is a fixed pipeline:

search, then a rule decides whether to research the company, then draft, then check the draft, then write the report.

Control flow is deterministic and testable (for example, "skip research if the posting is from a recruiter, or already has 600+ characters of description"). The model is used only where judgement over text is needed. Each step is checkpointed and logged, so a crash resumes from the last finished job and a failed job does not discard the others.

## What makes the output trustworthy

| Risk | Mechanism | Proven live? |
|---|---|---|
| Invented figures in the letter | Grounding guard: numbers not in the CV, posting or research trigger one regeneration, then a "Review needed" warning | **Yes, induced.** 3 of 3 live violations (one not asked for) were regenerated clean; the model did not fabricate in either eval run (68 applications). The "ship with Review needed" path is unit-tested only The earlier real fabrication (Day 18, niche-02) was caught by the eval check |
| Empty or broken draft | Structure guard: one regeneration, then a warning | **Yes, induced.** 6 of 6 empty-bullet drafts recovered, 6 of 6 flagged in the report when the retry also failed; never triggered by the model on its own in 68 applications |
| Writing to a recruiter as if they were the employer | Research policy skips agencies by name and by posting language | Partly. Agencies were caught by name in both runs; the language signal fired once live (a 6,593-character recruiter posting) and missed Eden Scott and RecOps, which the model handled anyway |
| A crash or one bad job losing the run | Checkpoint after every job; partial results delivered; full JSONL audit trail | Demonstrated in development sessions |
| Not knowing whether any of it works | 20-query golden dataset, 19 offline tool-selection scenarios, live eval | Yes (see below) |

## Evidence

From the Day 21 live run and a repeat on Day 22 (`docs/BASELINE.md`): 20 queries, 34 jobs each, `gpt-4o-mini`, my real CV. The figures below are Day 21's unless stated.

| Measure | Result |
|---|---|
| Queries passing | 18/20 as run; 19/20 after fixing two false positives in my own addressing check. A repeat run on 2026-10-19 gave 17/20 as run, 18/20 after another fix to my own check (one more false positive; two letters under the 150-word floor are real), so the spread between identical runs is about two queries |
| Grounding (numbers) | 100% of 11 evaluated queries in both runs, but the guard never fired in either |
| Cost | $0.0164 total, $0.0005 per application (estimate, not billing); the repeat run was the same |
| Latency | about 10 s for a query that drafts two letters (9.8 s, then 10.6 s in the repeat; the means over all 20 queries, including 3 that return nothing, are 8.4 s and 9.1 s) |
| Research | 8 of 34 jobs researched; 5 agencies skipped by name (repeat: 10 researched, 6 skipped by name) |
| Found and fixed on the way | FreeHire silently ignoring the search query; blank queries generating letters for random jobs; `--resume` silently skipping failed jobs and an empty model reply killing a job (both found by injecting faults); HTTP errors all classed as `UNKNOWN`; letters about 50 words shorter than the prompt asked (the model ignores numeric word targets, so the target was lowered to match, which did not stop 2 of 34 letters falling under the floor in the repeat run) |

## What I do not claim

- **Every letter needs a human read.** The guards narrow the risk; they do not remove it.
- **Grounding covers numbers only.** An invented skill or employer with no figure passes.
- **The sample is small.** One run, 34 jobs, one non-deterministic model, one CV. 18/20 versus 19/20 across days is mostly noise because the postings change daily.
- **Real failure data is nearly empty.** The live eval run had no failed attempts, so the failure taxonomy rests mostly on unit tests and development sessions (`docs/FAILURE_TAXONOMY.md`).
- **Failure data is induced, not organic:** the failure taxonomy is backed by 26 deliberately provoked faults (`docs/FAILURE_TAXONOMY.md` Part 4), not by real incidents.
- **Scope:** UK-only search, a single LLM provider, no pagination, no cross-run deduplication.

The claim is narrow on purpose. The pipeline drafts quickly and cheaply, and when it goes wrong it is built to say so, not to fail quietly. Where that is only tested by synthetic cases, this document says so.
