# VP Pitch (5 minutes of speech)

Audience: the VP of a Core AI Services team for a Senior Software Engineer role: AI-enabling platform services, agentic workflows and public APIs and SDKs that are "secure, reliable, cloud-native" on Azure, "agentic systems and harness engineering", Kubernetes, REST API design and versioning, OAuth2/OIDC/RBAC and privacy-by-design, in a Scrum team with mentoring. The ask is: hire me. Plain paragraphs are spoken (about 130 words a minute). Lines starting with `>` are stage directions. Every number comes from `docs/BASELINE.md`, `docs/FAILURE_TAXONOMY.md` or `docs/baselines/` and is marked as measured, induced or estimated.

## Before recording

> **One visual:** `docs/pitch_vp_slide.html`. Open it in a browser, full screen, and keep it up for the whole talk. It shows the pipeline on the left and the evidence on the right. No demo and no terminal: five minutes is for the argument.
>
> **Do not say** anything about time saved (no figure was measured), about the company's products, or about security certification. The project is a prototype for one user.
>
> **Stay inside what the project shows.** It has no Azure, Kubernetes, REST API or SDK, OAuth2/OIDC/RBAC, .NET or Scrum evidence. The pitch says so in one breath (see "The honest part") and does not try to cover those with the project. If you want to speak to them, do it from your real experience, in your own words, and not from this repository.
>
> **Optional line, your call:** the posting values AI-assisted development tools. This project was built with an AI coding assistant. If you want to say that, add one sentence to "What I built" and be ready to say how you reviewed what it produced (tests, induced faults, reading diffs). I left it out because I can't speak for how you want to describe your use.

## 0:00 to 0:45 — What I built and why it is relevant

I built a system that writes tailored job applications. The domain is small. The problem is one your team has every day: a model produces text a person will act on, and a mistake costs more than silence. A cover letter with an invented number under my name is worse than no letter.

So I treated it as a platform problem, not a prompt. Your posting says harness engineering, and that is what this is: the harness around the model. It makes the workflow observable, lets it survive failure, makes it say when it can't be trusted, and measures it. I built it over several weeks and wrote down what I got wrong.

## 0:45 to 1:45 — How it works

> **DO:** point to the left side of the slide.

It is a fixed pipeline, not a free-running agent. Code decides the order; the model writes the draft. I chose that after my first version, where the model chose its own tools, proved hard to checkpoint, hard to test, and different on every run.

For each job, a rule decides whether to research the company. The model drafts. Then two checks run: one for broken output, one that compares every figure in the letter with the CV and the posting. If a check fails, the draft is regenerated once. If it still fails, it is kept with a warning that a person sees. Every step is logged, and state is saved after every job, so a crash resumes where it stopped.

The reusable pieces for a platform team are the retry layer, checkpoint and resume, the check-and-flag pattern, and the evaluation and fault-injection harnesses.

## 1:45 to 3:15 — The evidence

> **DO:** point to the right side of the slide.

Cost. About a twentieth of a cent per application. That is a list-price estimate on a small model, not billing. A thousand drafts is roughly fifty cents. In an earlier model comparison, larger models cost up to thirty times more and did not do better on this task, though that was before I changed the prompt. So cost per draft is a lever I can measure.

Quality. On a twenty-query live test set, seventeen to nineteen passed across runs. Identical runs differ by about two, so I read little into one point.

Reliability. I provoked twenty-six failures on purpose, with the real error types: rate limits, timeouts, bad keys, a process killed mid-run. All twenty-six behave as designed. They are induced tests. I saw no real failures in the live evaluation runs, so I won't give you a real failure rate.

Safety. When I told the live model to break each rule, the checks caught and corrected it every time: three of three for invented figures, six of six for empty output. In sixty-eight live applications, the model never triggered them on its own. So the controls work; I don't know how often they are needed.

## 3:15 to 4:15 — The honest part

Here is where it stops. The figure check covers numbers only; an invented skill without a number gets through. The test sample is small and from one CV. Every letter still needs a human to read it. And it is a command-line prototype. No public API or SDK, no Azure or Kubernetes, no OAuth or role-based access, no privacy review. Those are what your team builds, and this project doesn't show them.

What I can show is how I behave when something is wrong. A rewrite of mine silently dropped CV tailoring for four days, and my own documents said it worked. Tests I wrote passed for the wrong reason. A check I wrote flagged correct letters. In each case I found the cause, fixed it, and wrote it down with the commit.

## 4:15 to 5:00 — Why me

> **DO:** leave the slide up; look at the camera.

For a team building foundations that other products depend on, I would bring three habits. I build for failure first, because the error path is where trust is lost. I measure, and I label what is measured, what is induced and what is only estimated. And I correct myself in the open.

I would like to join your team and apply that to services other teams build on. Thank you.

## Q&A prep (not part of the 5 minutes)

| Question | Short answer | Evidence and limit |
|---|---|---|
| Why should a platform team care about a job-application tool? | The domain is incidental. It is a full agentic workflow with retries, state, checks, evals and cost tracking, built and tested end to end | One user, one provider, a CLI. It shows the patterns, not production scale |
| What drives cost, and how do you control it? | Model choice and retries. Routing sends every call to one small model; retries are bounded (at most 3 calls per job) and an optional second model handles retries | List-price estimates for 4 models; failed attempts report no usage |
| How do you know it is safe? What happens when it is wrong? | Checks regenerate once and then flag; the human sees the warning. Auth or quota errors stop the run instead of burning calls | Numbers only. Induced tests, not an organic rate. Every letter still needs review |
| Security and privacy? Do you know OAuth2, OIDC, RBAC? | In this project: the CV is gitignored and read from a local file; the key comes from the environment. Nothing was security-reviewed or designed against a threat model | The CV is sent to the model provider. The audit trail used to store full prompts, CV included; I found that and fixed it, and it now logs only lengths and a hash. Checkpoints and reports still hold the generated letters. Identity, access control and privacy-by-design are **not** in this project. Answer from your real experience, not from this repo |
| Would this scale to a platform with public APIs and SDKs? | The pieces transfer: one place for model calls, a retry and classification layer, checkpoint and resume, evals. What changes: a real store instead of files, concurrency (it is sequential now), a versioned REST API and SDK, auth, tenancy, deployment on Azure and Kubernetes | None of that was built, so none of it is proven here |
| Azure, Kubernetes, .NET? | Not in this project; it is Python on a laptop. Answer from your CV. Be careful: the repo's CV lists Azure at a foundational level, and the model once invented an Azure-lead claim from it, so do not overstate it | The project cannot back this up either way |
| Mentoring and code quality? Scrum? | Not evidenced by the project. What it does show: decisions written down as records, a rule that every claim is labelled, code that is easy to review. Give mentoring and Scrum examples from your real experience | |
| What is "harness engineering" to you? | The code around the model that makes it dependable: orchestration, checks, retries, state, evals, fault injection, cost tracking. Here, that is most of the code; the model call is one function | The term is the posting's; this is my reading of it |
| How do you test something non-deterministic? | Three layers: unit tests with fakes, a live eval set with deterministic checks, and induced faults for the failure paths. Each result is labelled with how it was obtained | The eval set is small and its keywords were hand-written; identical runs differ by about two queries |
| What did you get wrong? | Four days of letters written without the CV after a rewrite, a search that ignored the query for days while mocks passed, every HTTP error filed as unknown, tests that passed for the wrong reason | All documented in `docs/ITERATION_STORY.md` with commits |
| Why not an agent framework? | The work is a fixed sequence over a list of jobs; the only judgement is the text. A framework would add moving parts I would still have to test | I did not benchmark a framework, so this is a design judgement |
| Which model, and why? | A small model, because it passed my checks at the lowest cost in my comparison | The comparison predates a prompt change; the question of a stronger retry model is open |
| What would you do first on this team? | Learn the existing services and their failure modes, then add what I have found useful here: tracing, evals and a way to inject faults | An intention, not evidence |

## Timing table (fill in during rehearsal)

| Segment | Target | Run 1 | Run 2 |
|---|---|---|---|
| What I built and why it is relevant | 0:45 | | |
| How it works | 1:00 | | |
| The evidence | 1:30 | | |
| The honest part | 1:00 | | |
| Why me | 0:45 | | |
