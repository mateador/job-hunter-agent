# Engineer Pitch (10 minutes of speech)

Audience: a senior engineer who has not heard the story. Plain paragraphs are what is said aloud (about 130 words a minute). Lines starting with `>` are stage directions, not spoken. Every number below comes from `docs/BASELINE.md`, `docs/FAILURE_TAXONOMY.md` or `docs/baselines/`, and is marked with how it was obtained: measured live, induced, or tested with fakes.

## Before recording

> **Pre-flight (5 minutes).** Venv active (`source .venv/bin/activate`), `OPENAI_API_KEY` set, network up, `python -m pytest tests -q` green (289 tests). Three terminals: A for the demo commands, B showing `docs/ARCHITECTURE.md` (the mermaid diagram rendered on GitHub or in the editor), C empty for a fallback. Clear `reports/` so the report you open is the new one. Increase the terminal font. Do one dry run of the live command below; it costs about $0.001 and sends the CV to OpenAI.
>
> **Live command:** `python -m src.job_agent.main "python engineer london" --cv private/alexandre_cv.md --max-jobs 2`, then `python -m src.job_agent.view_trace --narrative`. Skip `--cv` and the letters will come from a placeholder profile. That is exactly the bug from Days 11 to 14.
>
> **Fallback if the network or FreeHire fails on camera:** say so, switch to terminal C and run only the offline demo (`python -m evals.stress.faults --only B6,B7a,B3b`). It is deterministic and takes a few seconds.
>
> **Stay inside what the project shows.** The target role asks for Azure, Kubernetes, REST API and SDK design and versioning, OAuth2/OIDC/RBAC, privacy-by-design, .NET, Scrum and mentoring. This project has none of that. The limits section says so in one sentence, and the Q&A rows below give design intent clearly marked as not built. Answer experience questions from your real background, not from this repository.
>
> `tests/scripts/demo_recovery.sh` is an interactive kill and resume demo from Day 14. It does not pass `--cv`, so do not use it as is.

## 0:00 to 1:00 — The problem and the claim

I want to show you a system I built to write job applications, and mostly I want to tell you how I came to trust it, and where I still don't.

The task is real. A good application means searching several sources, reading the posting, researching the company, matching my CV, and writing a letter that says something true. A language model can do the writing. What it can also do is invent a figure on my CV, address a recruiter as if they were the employer, or hand back something broken and call it finished.

The word for the interesting part is harness engineering: the code around the model that makes it dependable, which here is most of the code.

So the claim is narrow on purpose. This pipeline drafts quickly and cheaply, and when it can't be trusted it says so, instead of failing quietly. The rest of the talk is the evidence for that sentence, and what the evidence doesn't cover.

## 1:00 to 3:00 — The design

> **DO:** show the pipeline diagram in `docs/ARCHITECTURE.md`.

This is a fixed pipeline, not an agent loop. Code runs one search, then goes through the jobs one at a time. For each job a deterministic rule decides whether to look the company up. Then one model call drafts the letter and CV bullets. Then two checks run. Then the state is saved.

The model never chooses a tool or the order of anything. I had an LLM-driven loop first, with a long list of guardrails. I removed it, and the reasons are practical. Checkpointing needs a clear unit of work, one job. The research decision and the checks need to be testable without a model. And a loop makes every run a different sequence.

The research rule is simple: skip agencies, skip postings that already have enough text, skip duplicates, otherwise look the company up. Nineteen hand-labelled scenarios test it offline, and I checked they fail when I break the rule. It is a heuristic, and I'll show you where it's wrong later.

The two checks do the same thing. A structure check catches an empty letter or missing bullets. A grounding check compares every number in the draft with the CV, the posting and the research. If either fails, the draft is regenerated once with a note saying what was wrong. If it still fails, the draft is kept with a warning in the report. So the cost is bounded at three model calls a job, and a person sees the problem.

## 3:00 to 5:00 — Failure handling

Failures are classified by cause, and only causes that can clear on their own are retried. Timeouts, rate limits, server errors and dropped connections get three attempts with a one second and then a two second wait. A bad key, a rejected request, or an exhausted quota is never retried.

I measured the waits against the real API: one point zero one and two point zero one seconds. Those are real, not mocked.

If a job fails after its retries, it is recorded with its category and real attempt count, and the run continues. You get partial results. The one exception is authentication or quota. Every remaining job would fail the same way, so the run stops, keeps what it has, and prints the command to resume.

State is a JSONL checkpoint after every job. Resume reloads it, skips finished jobs, and retries the failed ones. I'll come back to that last part, because it was a bug.

Where does this evidence come from? Real failures were almost absent. Across the live evaluation runs there wasn't one failed attempt. So I provoked them: twenty-six faults, using the real exception types from the OpenAI client and the HTTP library against the real pipeline. Twenty-six of twenty-six now match what I wrote down beforehand. They are induced, and I want to be clear that they say nothing about how often these failures happen.

## 5:00 to 7:00 — Live demo

> **DO:** terminal A. Run the live command. Narrate while it runs; it takes about 10 seconds for two jobs.

This is one search, two jobs, using my real CV. While it runs: it searches, decides per job whether to research, drafts, runs both checks, saves. At the end it prints the cost, here a fraction of a cent, and any warnings.

> **DO:** when it finishes, open the report in `reports/`. Show one letter and any "Review needed" line. Then run `python -m src.job_agent.view_trace --narrative`.

Here's the report: a letter, the bullets, and any warning. And here is the trace, which records every attempt and every decision, including why it did or didn't research each company. Nothing here is hidden.

> **DO:** now the offline demo. Run `python -m evals.stress.faults --only B6,B7a,B3b`.

Now three induced faults. The first kills the process with kill minus nine in the middle of job three of four, then resumes. It keeps jobs one and two, doesn't search again, finishes three and four, and creates no duplicates. The second is a job that failed once. On resume it is retried and the run completes. The third is a bad key on job two of three. The run stops after two calls instead of making a pointless call for every job.

## 7:00 to 9:00 — What went wrong

I want to be specific about how this went wrong, because I think it's the most useful part.

First. When I added checkpointing, I rewrote the runner. That commit also removed the model loop, the research step and the CV matching. And for the next four days of work, the letters were written without my CV, from a placeholder profile. The README still described CV tailoring as working. A demo passed, because it ran on mocks. I only saw the full extent of it later, when I compared the old and new code line by line.

Second. The search was pointed at a generic endpoint that silently ignores the query. You get an unfiltered feed back. Mock mode hid it, because mock mode uses canned jobs. The first live evaluation found it. Now the code reads the response's ignored-parameter list and raises if the query is ignored.

Third. For weeks, every HTTP error was classified as unknown. The code tested whether the response was truthy, and a response with a 4xx or 5xx status is falsy. So a rate limit was never retried. The tests used mock responses that were truthy. They passed.

Fourth, and my favourite. When I later fixed the resume bug, two old tests that were supposed to cover it still passed. They passed because an assertion inside a mock was swallowed by the runner's own error handling. They were green for the wrong reason.

The pattern is that green didn't mean working, and the fixes came from running the real thing, reading output, or breaking it on purpose.

## 9:00 to 10:00 — Limits and next

Here is what I don't claim. The grounding check covers numbers only, so an invented skill without a figure gets through. The guards worked every time I provoked them with the live model, but in sixty-eight evaluation applications the model never triggered them on its own, so I can't give you a real rate. Agency detection is a heuristic. The pass rate moves by about two queries of twenty between identical runs. And every letter still needs a human to read it. It is also a command-line prototype: no REST API or SDK, no authentication or access control, no privacy review, and nothing on Azure or Kubernetes. Preparing this talk I found that the audit trail stored every prompt in full, my CV included. That is fixed: it now logs lengths and a hash. The generated letters still sit in the checkpoint and report files.

What I'd do next is turn it into a service: a versioned API, authentication, redacted tracing and concurrency. And an LLM-judge check for invented claims that have no figure, with a larger live sample for a real failure rate.

The whole thing is about two thousand seven hundred lines of Python, two hundred eighty-nine tests, a failure document where every row says how it was observed, and a record of every mistake in this talk. Thank you.

## Q&A prep (not part of the 10 minutes)

| Question | Short answer | Evidence and limit |
|---|---|---|
| Why not an agent framework or tool-calling loop? | The work is a fixed sequence over a list; the only judgement is text. A loop adds nondeterminism and removes the clear unit of work checkpointing needs | The first version was a loop. It was replaced on Day 11. The cost is nothing adapts |
| How do you know the guards work? | Unit tests, replay on saved data, and on Day 22 the real model was told to break each rule | Structure: 6/6 recovered, 6/6 flagged in the report. Grounding: 3/3 recovered. Not proven: the "ship with Review needed" path for a figure, and the organic rate |
| What stops it fabricating? | Nothing absolute. A numeric grounding check plus a prompt rule, plus a human reading | Numbers only. One real fabrication was caught by the eval, not at runtime, before the guard existed |
| Why `gpt-4o-mini`? | It passed 6/6 in the Day 19 comparison at the lowest cost; `gpt-4.1-mini` also passed at 2.85 times the cost, the gpt-5 models 3/6 | The comparison predates a prompt change; the retry-model question is open |
| What does it cost? | About $0.0005 per application at list price | An estimate, not billing; failed attempts report no usage |
| What happens at 1,000 jobs? Would it work as a platform service? | Not tested. It is sequential at roughly 5 seconds a job (about 10 seconds for a search that drafts two letters), and the search takes one page of results. As a service the first changes are concurrency, a job queue, a real store instead of JSONL files, and tenancy | No pagination, no deduplication across runs. None of the service parts is built |
| How would you expose it as a REST API? | Design intent, not built: `POST /v1/applications` accepting a search and a CV reference, returning a job id; `GET /v1/applications/{id}` for status and results; idempotency keys; an OpenAPI spec; a version in the path and a deprecation policy; async because a run takes seconds to minutes | The checkpoint state and the result object already look like the resource. No API code exists |
| How would you secure it (OAuth2, OIDC, RBAC)? | Design intent, not built: OIDC for users, OAuth2 client credentials for service-to-service, roles per tenant, the CV never stored by default, prompts redacted in traces, retention limits | Today: the CV is gitignored and the key is an environment variable. The audit trail used to store full prompts, CV included; it now logs only lengths and a hash (tested). Checkpoints and reports still hold the generated letters, and there are no retention rules, no access control and no threat model |
| Azure, Kubernetes, .NET? | Not in this project: Python on a laptop. Answer from your CV and say so plainly | The repo's CV lists Azure at a foundational level, and the model once invented an Azure-lead claim from it, so do not overstate it |
| What is "harness engineering"? | The code that makes a model dependable: orchestration, checks, retries, state, evals, fault injection, cost tracking | The term is the posting's. This is my reading of it |
| How did you use AI coding tools, and how did you verify the output? | Answer in your own words. The checkable evidence is in the repo: tests, induced faults, the bugs caught in review and the decision records | Don't claim a process you didn't follow |
| Mentoring, code review, Scrum? | Not evidenced by the project. What it shows: decisions written as records and every claim labelled, which is what a reviewer needs | Give examples from your real experience |
| Why JSONL and not a database? | Append-only survives a crash, readable with `tail` and `grep` | No queries; fine at this scale |
| How do you handle rate limits? | Retry with 1s and 2s backoff, three attempts | `Retry-After` is not honoured, so a sustained rate limit still fails the job |
| Why is the research rule so simple? | It is cheap, explainable and testable; the threshold sits in an empty gap in the data | It missed two agencies (Eden Scott, RecOps); the model compensated in both cases. A weak spot, not a solved one |
| How good are your evals? | A 20-query dataset, per-application checks, a mock mode, and a rescore tool. 17/20 as run, 18/20 after fixing a check on the latest run | Small samples; keywords and thresholds are hand-written; two checks had false positives that I fixed after seeing the failures |
| What was the hardest bug? | The tests that passed for the wrong reason | After the resume fix, tests that should have caught the bug swallowed an assertion in a mock |
| What would you change first? | Cover invented claims without figures, and measure the organic failure rate on a larger live sample | Both are listed as open |

## Timing table (fill in during rehearsal)

| Segment | Target | Run 1 | Run 2 |
|---|---|---|---|
| Problem and claim | 1:00 | | |
| Design | 2:00 | | |
| Failure handling | 2:00 | | |
| Live demo (speaking) | 2:00 | | |
| What went wrong | 2:00 | | |
| Limits and next | 1:00 | | |
