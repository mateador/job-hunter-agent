# Evaluation Baseline (Day 18)

First full live evaluation with every check in place: 20 golden queries, 34 jobs, real FreeHire and OpenAI calls.

- **Run:** `eval_live_20261006_123418`, 2026-10-06, model `gpt-4o-mini`, 2 jobs per query
- **Dataset:** `evals/golden_dataset.json` v1.1 (6 standard, 4 niche, 3 broad, 4 edge case, 3 agency)
- **CV:** the author's real CV (kept private; only the summary is committed in `docs/baselines/`)
- **Code state:** before the empty-search-result fix and the runtime grounding guard described below

Reproduce with `python -m evals.runner --live --max-jobs 2`. Raw results are written to `evals/results/` (gitignored, because they contain letters generated from a private CV).

## Result

**19 of 20 queries passed (95%).** All 14 offline tool-selection scenarios passed.

| Category | Queries | Pass rate |
|---|---|---|
| standard | 6 | 100% |
| niche | 4 | 75% |
| broad | 3 | 100% |
| edge case | 4 | 100% |
| agency | 3 | 100% |

| Check | Evaluated | Pass rate |
|---|---|---|
| status | 20 | 100% |
| min_jobs | 19 | 100% |
| relevance (job titles match keywords) | 16 | 100% |
| format | 17 | 100% |
| addressing (names company and role) | 17 | 100% |
| grounding (figures come from CV, posting or research) | 11 | **91%** |
| search_honored | 20 | 100% |
| tools / tool_sequence | 20 / 19 | 100% |
| tool_selection | 17 | 100% |
| no_redundant_research | 8 | 100% |
| escalation_graceful | 2 | 100% |

Mean latency was 10.0s per query (maximum 15.4s). Token usage and cost are not measured yet (Day 19).

**Escalation:** 11 of 34 jobs were researched via DuckDuckGo. The rest were skipped: 16 had a rich description, 6 were agencies, and 1 company was already researched.

## What the baseline found

**1. One real fabrication (niche-02).** For a Cloud Infrastructure Engineer role the model wrote that it "reduced deployment times by 40%" and "reduced configuration errors by 25%", and claimed to have led Azure infrastructure deployments. Neither figure is in the CV, the posting or the research, and the CV says Azure at foundational level. The grounding check caught it only because the model attached numbers; the invented claim itself would not have been detected without them.

**2. "No results" was counted as a research failure.** Both reported research failures were the search library's `No results found` exception, which is an empty result, not an outage. The 2/11 failure rate in the run is therefore overstated.

**3. "Thin posting" mostly means "truncated posting".** Roughly two thirds of sampled descriptions are cut at exactly 500 characters and end in an ellipsis. They come from two aggregator sources (`adzuna`, `whatjobs-uk`), and neither a parameter nor a detail endpoint returns the full text. All 11 researched jobs were under 502 characters and every other job was 1,306 or longer, so the 600-character threshold is not sensitive: any value from 502 to 1,300 makes identical decisions. Research adds company context but not the missing role details, so the model still writes from half a posting.

**4. Earlier live runs found two bugs that this baseline depends on being fixed.** The first live run showed FreeHire silently ignoring the query (the code called the generic endpoint instead of the agent search endpoint), and a blank query generated applications for unrelated jobs. Both are fixed and covered by tests.

## Changes made in response

| Finding | Change |
|---|---|
| Fabricated figures | Runtime grounding guard: an application whose figures are not in the CV, posting or research is regenerated once with the offending figures named. If it still fails, it is kept and flagged "Review needed" in the report. |
| "No results" as failure | `search_duckduckgo` returns an empty list for that exception; other errors still raise. |
| Truncated postings | No change. The behaviour is correct (research when the posting is short); documented here. |

These changes have unit tests. A small follow-up live run (see below) checked them against the real APIs.

## Follow-up run (`eval_live_20261006_130312`)

Three queries rerun after the fixes: niche-02, niche-04 and agency-02 (6 jobs). All passed.

- **Empty search results are fixed live.** The company "107632 Capital Markets Operations" returned no results again, but is now recorded as an empty result with 0 failures, instead of a failed research call.
- **The grounding guard did not trigger (0 of 6 regenerated).** The niche-02 fabrication did not recur, but that is not evidence the guard works: the model is non-deterministic and simply did not invent figures this time. The guard's behaviour is covered only by unit tests with a scripted LLM so far. Demonstrating it live needs either repeated runs or a case where the model fabricates again.
- **A policy gap showed up.** "Intec Select Ltd" is a technology recruitment firm (the research summary says it matches candidates with roles, and the posting refers to "the client's office"), but its name matches none of the agency patterns, so it was researched. Agency detection is name-based only. Posting language such as "our client" or "the client's office" would be a second signal; that is not implemented.
- **Latency was higher (mean 15.4s)** because all 6 jobs were researched, against about a third of jobs in the full baseline. Six jobs are too few to put a figure on the cost of research; Day 19 should measure it per job.

## Limits of this baseline

- **Small and noisy.** 34 jobs, one run, a non-deterministic model. One odd job moves a query's result by 50 points, and a rerun can differ.
- **Grounding covers numbers only.** An invented skill or employer without a figure passes.
- **Relevance is keyword-based on titles.** It catches unrelated jobs but accepts loosely related ones (for example generic "Cloud Infrastructure Engineer" for "agent infrastructure engineer").
- **Keywords and `min_jobs` are hand-written guesses** and have not been tuned against more than this run.
- **UK-only search.** The Lisbon query returns no jobs by design of the filter, so it exercises the empty-result path, not multilingual handling.
- **One CV.** Results say nothing about other candidates' profiles.
- **Mock mode is not evidence.** `python -m evals.runner` without `--live` validates the harness only.

The per-query summary is in `docs/baselines/eval_live_20261006_123418.summary.json`.
