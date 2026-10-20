# Evaluation Baselines

Three live runs. The **Day 22 re-run** is the current one because it is the latest and matches the prompt of that time (the prompt lost a hardcoded personal sentence on Day 28, see the note below); the Day 21 checkpoint and the Day 18 baseline are kept as the record and predate later changes (see below).

---

> **Note on the prompt (Day 28).** Until Day 27 the generation prompt contained one hardcoded sentence about the author (location and work authorisation). It was removed so the repository holds no personal details; the same facts can now be supplied with `--candidate-note` or `CANDIDATE_NOTE`. All results below were produced with the old prompt. Runs made after this change are not strictly comparable with them, which matters little for the pass-rate and cost figures but is stated here for honesty. No re-run was made.

# Day 22 induced-guard experiment (live, real model)

`python -m evals.stress.guards` (user's terminal, 2026-10-19, `gpt-4o-mini`, the author's real CV, 5 scenarios x 3 queries x 2 jobs = 30 job runs, **$0.019 estimated**). Each scenario appends an explicit "break the rule" instruction to the first draft prompt (G2 and G4 also to the retry prompt). Table: `docs/baselines/stress_guards_20261019.md`. **This is induced.** It shows detection and recovery with a live model; it does not give a failure rate.

| What was exercised | Live result |
|---|---|
| Structure guard, recovery (G3: empty bullets on the first draft) | **6 of 6 drafts** flagged `no CV bullets`, regenerated once, final drafts clean |
| Structure guard, flag path (G4: empty bullets on draft and retry) | **6 of 6** kept with `No CV bullets. Check before sending.`; the Markdown report shows "Review needed" for them |
| Grounding guard, recovery | **3 of 3** violations (`25`, `40`, `75`) regenerated once; the final letters contain none of those figures (checked independently of the guard, against CV and posting) |
| Retry-model routing (G5: `--retry-model gpt-4.1-mini`) | The grounding retry really ran on `gpt-4.1-mini-2025-04-14` and the draft on `gpt-4o-mini`; the retry came back clean (n=1) |
| Grounding guard, flag path (both drafts fabricate, G2) | **Not exercised**: the retry never fabricated again |

**What this does not show.**
- The fabrication instruction mostly did not work: 2 of the 18 provoked jobs (G1, G2, G5) produced an ungrounded figure. `gpt-4o-mini` mostly reused figures that are in the CV, which are grounded. G1 produced none, and G2 produced one although the retry was provoked too.
- **One violation was not provoked.** In G3 (`solutions engineer`, Dynatrace) the instruction only broke the structure, yet the regenerated draft contained an invented `75`. The guard caught it and the retry removed it. It is the first ungrounded figure seen live since the Day 18 baseline, and it came from a draft written with a revision note, not the normal prompt. One event; it does not change the organic rate estimate (now 1 in about 100 live applications, from two runs plus this one), but it shows the guard earns its place.
- The grounding flag path (a letter shipped with "Review needed" for a figure) is still proven only by unit tests.
- Recovery means the final draft has no ungrounded numbers and passes the structure rules. Whether the second letter is a better letter is not measured.
- G5 compares nothing about retry-model quality: n=1, the retry model fixed it, `gpt-4o-mini` fixed the same kind of case in G2 and G3. The retry-model question stays open.

---

# Day 22 re-run (current)

Same command and dataset as Day 21, run after the prompt change (no "concise", letter target 160-300 words). Purpose: measure that change and see how much a repeat run moves.

- **Run:** `eval_live_20261019_162521`, 2026-10-19, `gpt-4o-mini`, 2 jobs per query, the author's real CV. Summary: `docs/baselines/eval_live_20261019_162521.summary.json`.
- **Reproduce:** `python -m evals.runner --live --max-jobs 2`.

## Result

**17 of 20 queries passed (85%) as run; 18 of 20 after correcting the addressing check.** 19/19 offline scenarios passed. Standard 5/6, niche 3/4, broad 2/3, edge 4/4, agency 3/3. Format 88%, addressing 94%, grounding 100% (11 evaluated), relevance 100%.

Cost: 34 calls, 92,429 tokens, **$0.0162 estimated, $0.0005 per application** (list price, not billing). Mean latency 9.06s over all 20 queries (the 17 that drafted letters averaged 10.6s; max 15.57s). 10 of 34 jobs researched, 0 failed.

## The three failures

- **`std-01` addressing: a false positive of the check, not a letter fault.** FreeHire's company field is the slug `Hsogroupbv`; the letter correctly says "HSO". Day 21 had a similar slug case (`foundationhealthcareers`), which the check now handles by prefix; `hsogroupbv` does not prefix-match "HSO". The check now also strips trailing corporate suffixes (group, bv, ltd, plc, ...) from a one-word slug and accepts the remaining stem (3+ characters) as a whole word in the letter; a different company, a longer word ("HSOX") and suffix-free names still fail (tested). `python -m evals.rescore` gives **18/20**. As on Day 21, the fix was made after seeing the failure and re-scored on the same data, so 18/20 is a statement about the check, not a fresh measurement.
- **`niche-02` and `broad-03` format: real. Letters of 139 and 138 words** against the 150 floor.

## Letter length under the new target (the question this run was for)

| | Day 21 run (target 220-300) | This run (target 160-300) |
|---|---|---|
| Letters | 34 | 34 |
| Mean words | 173 | 173 |
| Range | 146-199 | 138-205 |
| Inside the prompt's target | 0 | 29 of 34 (85%) |
| Under 150 (fails the check) | 1 | 2 |

**Reading:** the mean did not move. The model writes about 173 words regardless of the number in the prompt, as the Day 21 follow-up found. Lowering the target to 160 therefore "fixed" length only by moving the goalpost to where the model already is. 5 of 34 letters (15%) are still under 160 and 2 are under the 150 floor, so this prompt wording does not prevent short letters. Pooled with Day 21, 80 letters average about 174 words. Whether a short letter is actually worse is not established: the 150-word floor is a rule I chose, not a measured quality threshold.

## What this run shows and does not show

- **Guards still did not fire organically.** Grounding retries 0, structure retries 0, structure flags 0, in 34 applications: two live eval runs (68 applications) with no activation. They were later exercised on purpose (section above).
- **`agency_posting` fired live for the first time**, once: `remotestar-team` on `broad-02` (a 6,593-character posting; the rich-description rule would have let it through without a name match). One live hit, not a measurement of recall.
- **A miss:** on `agency-02` the company "RecOps" was not recognised as an agency (the name has no "recruit"), and the posting (498 characters) was researched as `thin_description`. The model still addressed the letter to "RecOps Recruitment Team" and called it a consultancy, so the letter was fine; the policy was not. Same pattern as Eden Scott in Day 21: the model compensates for what the policy misses.
- **Day 21 and Day 22 are not job-for-job comparable** (FreeHire postings change daily). 19/20 re-scored versus 17/20 as run, with a different mix of failure causes (Day 21: two check false positives and one short letter; Day 22: one check false positive and two short letters), shows the spread you get from re-running the same code. It says little about which version is better.
- Same limits as Day 21 (below): small sample, non-deterministic model, keyword relevance, numbers-only grounding, UK only, one CV.

---

# Day 21 checkpoint (superseded by Day 22 for the prompt, kept for the record)

Full live run after the Day 19-20 work: 20 golden queries, 34 jobs, real FreeHire and OpenAI calls.

- **Run:** `eval_live_20261009_132309`, 2026-10-09, model `gpt-4o-mini`, 2 jobs per query, the author's real CV (private; only the summary is committed in `docs/baselines/eval_live_20261009_132309.summary.json`)
- **Code state:** with the runtime grounding guard, the structure guard, the agency-language signal, retry classification fixes and cost tracking. The prompt at run time still said "concise" and asked for 220-300 words (changed afterwards: "concise" removed, target now 160-300; see below).
- **Reproduce:** `python -m evals.runner --live --max-jobs 2`. Re-score a saved run with the current checks, offline: `python -m evals.rescore <eval json>`.

## Result

**18 of 20 queries passed (90%) as run; 19 of 20 after correcting the addressing check.** All 19 offline tool-selection scenarios passed.

| Category | Queries | Pass rate |
|---|---|---|
| standard | 6 | 100% |
| niche | 4 | 75% |
| broad | 3 | 67% |
| edge case | 4 | 100% |
| agency | 3 | 100% |

| Check | Evaluated | Pass rate |
|---|---|---|
| status / search_honored / tools | 20 | 100% |
| min_jobs | 19 | 100% |
| relevance (job titles match keywords) | 16 | 100% |
| format | 17 | 94% |
| addressing | 17 | 88% |
| grounding | 11 | 100% |
| tool_selection / usage_recorded | 17 | 100% |
| tool_sequence | 19 | 100% |
| no_redundant_research | 7 | 100% |

**Cost (new, measured):** 34 LLM calls, 94,592 tokens (82,536 prompt, of which 43,008 cached; 12,056 completion), **$0.0164 estimated in total: $0.0005 per application, $0.0008 per query**. These are list-price estimates (`pricing.json`, verified by the user for four models), not billing; the author's `gpt-4o-mini` usage is currently free. Failed attempts report no usage, but this run had none.

**Latency:** mean 8.4s per query over all 20 queries, including 3 that return no jobs (the 17 queries that drafted two letters averaged 9.8s; maximum 12.7s), against 10.0s on Day 18. One query is mostly the sequence search, up to two LLM calls and any research.

**Escalation:** 8 of 34 jobs researched via DuckDuckGo (0 failed). The rest: 20 had a rich description, 5 were agencies recognised by name (Hunter Bond, Ocho, Ocho People, GCS Recruitment twice), 1 company was already researched.

## What this run shows and does not show

**Not comparable job by job with Day 18.** FreeHire returns different postings on different days, so 19/20 against 18/20 is mostly noise: one job moves a query by 50 points, and each query that failed here had two jobs.

**The new mechanisms did not fire live, so this run does not validate them.**
- Grounding guard: 0 of 34 applications regenerated. Grounding went from 91% to 100%, but only because the model did not invent figures this time (as in the Day 18 follow-up). It says nothing about whether the guard works; that is covered by unit tests only.
- Structure guard: 0 retries, 0 flags.
- Agency-language signal: the `agency_posting` reason never appeared. All five agency skips were by name.

**The two addressing failures were false positives in the check, not faults in the letters** (from reading the first ~700 characters of each letter):
- `niche-03`: FreeHire's company field was the slug `foundationhealthcareers`; the letter correctly says "Foundation Health".
- `broad-01`: the company is Eden Scott, a recruiter. The model recognised it from the text and addressed the letter to a named consultant about the end client, which is what the prompt asks. The check only accepted a greeting containing "consultant" or "recruiter". **Neither the name pattern nor the language signal flagged Eden Scott**: the research decision was `rich_description`, and the language check runs before that rule, so the full posting contained none of the phrases. The start of the posting describes the end client in the third person ("You'll be joining Rhea Space Activity"). The model handled it; the research policy did not.
- The check now matches a slug by prefix and accepts a named-person greeting (with tests, including a wrong-company letter that must still fail). Re-scoring the saved run gives 19/20. A named-person greeting can now mask a letter that never names the company; the rule excludes team/company greetings ("Dear Globex Corp") but cannot tell a real person from a two-word company name it has not seen.

**One real defect: `broad-01` had a 146-word letter** (the check wants 150-350). The prompt had asked for 220-300 words, and this was not luck of one letter: **none of the 34 letters was inside 220-300** (mean 173, range 146-199). The bullet limit worked (longest 231 characters, none over 240). On the same six standard queries the Day 19 comparison had averaged 226 words, so adding the explicit targets, with "concise" still in the prompt, coincided with shorter letters. The jobs differ, so this is suggestive, not proof. After this run "concise" was removed from the prompt and six standard queries were re-run (`eval_live_20261009_133140`, 12 letters, 6/6 passed): mean 179 words (160-202), still none inside 220-300. Pooled over both runs: 46 letters, mean 175, standard deviation 14, none inside 220-300. So `gpt-4o-mini` does not follow a numeric word target; the prompt target was then lowered to 160-300 to match what it writes and still cap verbose models. That last change is not re-measured.

## Limits

- **Small and noisy.** 34 jobs, one run, a non-deterministic model; categories of three or four queries.
- **Keyword relevance on titles; keywords and `min_jobs` are hand-written guesses.**
- **Grounding covers numbers only**; an invented skill or employer without a figure passes.
- **UK-only search** (`FREEHIRE_REGIONS` exists but non-UK values are unverified), so edge-04 still tests the empty path.
- **One CV; mock mode is not evidence.**
- **Agency detection is heuristic** (name pattern plus a narrow language pattern). Eden Scott shows it misses agencies that describe the end client in the third person.
- **The check fix was made after seeing the failures**, on the same data it was then re-scored on. The re-scored 19/20 is a statement about the check, not a fresh measurement.

---

# Day 18 baseline (superseded, kept for the record)

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
- **A policy gap showed up.** "Intec Select Ltd" is a technology recruitment firm (the research summary says it matches candidates with roles, and the posting refers to "the client's office"), but its name matches none of the agency patterns, so it was researched. Agency detection is name-based only. Posting language such as "our client" or "the client's office" is now a second signal (Day 20, `agency_posting`); it has not been re-measured in a live run.
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
