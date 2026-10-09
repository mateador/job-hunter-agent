# Model Comparison (Day 19, run on 2026-10-09)

Four OpenAI models on the same first 6 golden queries (2 jobs each, 12 applications per model), live,
with the same checks. Run by the user in their own terminal with `LLM_TIMEOUT=180`. Source reports are
in `evals/results/compare_live_*.md` (gitignored: they contain letters generated from a private CV).

## Results

| Model | Queries passed | Grounding | Format | Failed jobs | Est. cost / app | vs `gpt-4o-mini` | Mean latency |
|---|---|---|---|---|---|---|---|
| `gpt-4o-mini` (reference) | 6/6 (both runs) | 100% | 100% | 0 | $0.0005 | 1x | 9.0s / 9.8s |
| `gpt-4.1-mini` | 6/6 | 100% | 100% | 0 | $0.0014 | 2.85x | 15.7s |
| `gpt-5-nano` (effort `minimal`) | 3/6 | 100% | 50% | 0 | $0.0003 | 0.58x | 17.6s |
| `gpt-5.4` (effort `low`) | 3/6 | 100% | 50% | 0 | $0.0149 | 32.1x | 23.2s |

Costs are list-price estimates (`pricing.json`, verified by the user for these four models), not billing. The
numbers come from two runs: `gpt-4o-mini`, `gpt-4.1-mini` and `gpt-5-nano` from the 4-model run
(`compare_live_20261009_120258`), `gpt-5.4` and a second `gpt-4o-mini` run from `..._121313`.
`gpt-4o-mini` scored 6/6 in both and cost $0.0060 and $0.0056, so run-to-run cost noise is small.

## What the data says

1. **`gpt-4o-mini` is the best default on this sample.** It passes everything, is the fastest, and is among the cheapest. Nothing here supports changing the default. The user's `gpt-4o-mini` is currently free, so these figures are for comparison, not what they pay.
2. **`gpt-4.1-mini` matches its quality at 2.85x the cost.** No quality gain was visible, so there is no case for it either.
3. **The reasoning models failed on length, not on content.** I re-ran the harness's own format check on the saved applications. Each failed 4 of 12 applications:
   - `gpt-5-nano`: 4 bullets over 300 characters, 1 letter of 365 words.
   - `gpt-5.4`: 3 bullets over 300 characters, 2 letters over 350 words, and **1 application with no CV bullets at all**.
   - Letters averaged 226 words (`gpt-4o-mini`) and 248 (`gpt-4.1-mini`), against 304 (`gpt-5-nano`) and 313 (`gpt-5.4`).
4. **The prompt never states those limits.** It asks for "a concise cover letter (3-4 paragraphs)" and "3-4 bullet points". The 300-character bullet and 150-350 word limits exist only in the eval (`evals/scoring.py`). So this tests "does the model happen to be short", not "does it follow the instructions". It is a real defect in the harness/prompt pairing and it is unfair to the verbose models. It is not evidence that they are worse writers.
5. **`gpt-5.4`'s cost is mostly its price, not hidden thinking.** At effort `low` it used about 64 reasoning tokens per call (about 650 completion tokens against about 440). The 32x comes from the list price ($2.50/$15 against $0.15/$0.60 per 1M tokens).
6. **One `gpt-5.4` application had empty bullets and was accepted.** `application_generator` turns missing bullets into `[]` without complaint. Only the eval's format check caught it. In a real run that would be shipped as a report with an empty bullet section.

## What it cannot say

- **The retry-model question is unanswered.** No model produced an ungrounded figure and no grounding retry happened (0 retries, 0 flagged for every model). Whether a stronger model helps on retries remains untested. Grounding at 100% everywhere also means this run gives no quality signal on fabrication.
- **Reasoning effort is a confound.** `gpt-5-nano` ran at `minimal`, `gpt-5.4` at `low`. `gpt-5.4` rejected `minimal` with a 400 ("Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'"), and that first attempt failed all 12 jobs in 2 seconds. Values differ by model, so one `--reasoning-effort` for a mixed list cannot be right for all of them.
- **Small and single-run.** 6 queries, one run per model, a non-deterministic model, one CV. A single query is 17 points. Only large gaps count.
- **`gpt-5-nano` hit a 60s timeout earlier** (about 5.9k completion tokens and 49s per call at its default effort) and needed `LLM_TIMEOUT=180`; with `minimal` it ran at 17.6s. Latency depends on effort, so the latency column is not comparable across effort settings.
- Failed attempts report no usage, so failed-run costs are missing. Trace files in `evals/results/compare/<model>/` accumulate across runs, so aggregating them mixes runs; use the reports.

## Follow-ups

Done on 2026-10-09 (after this run, so these results predate them):
- The generation prompt now states the limits (bullets at most 240 characters, letter first 220-300 words, then 160-300 after `gpt-4o-mini` ignored the first target; see `docs/BASELINE.md`), taken from the shared `src/job_agent/format_rules.py`, which the eval also uses. Whether `gpt-5-nano` and `gpt-5.4` now pass the format check is **not yet measured**; the rows above are for the old prompt.
- Empty or unusable output is now caught at runtime by the structure guard (one regeneration, then a "Review needed" flag).

Still open:

- Re-run the comparison with the new prompt (at least `gpt-4o-mini` and the two reasoning models at one common effort, `low`) to see whether the length failures were the prompt. The 20-query baseline must also be re-run, which is the Day 21 live run.
- If a retry model is still of interest, test it on a case that forces a grounding retry.
