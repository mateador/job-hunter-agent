# Failure Taxonomy

Every failure in this system is classified into one of eight categories.
Each category has a defined retry policy and recovery path.

This document is the single source of truth for failure handling.
Code in `src/job_agent/failures.py` implements this taxonomy.

---

## Categories

### 1. MISSING_DATA

**Definition:** A required input or expected data field is empty, None, or absent.

**Examples:**
- CV text is empty or too short
- Keywords list is empty
- FreeHire API returns zero jobs for the query
- DuckDuckGo returns no results for a company
- A job object lacks a `company` or `position` field

**Retry Policy:** `RETRY_MODIFIED` — retry with different parameters if possible (e.g., broader keywords). If the input itself is bad, `NOT_RETRYABLE`.

**Recovery:** Log the specific missing field. If input validation failed, stop. If a tool returned empty, the agent may try a modified query.

---

### 2. MALFORMED_RESPONSE

**Definition:** A response was received but does not match the expected schema or format.

**Examples:**
- LLM returns text that cannot be parsed as JSON
- LLM returns `tool_arguments` as a list instead of a dict
- LLM omits a required field in the final answer
- FreeHire returns valid JSON but with unexpected nesting

**Retry Policy:** `RETRY_SAME` — feed the error back to the LLM for self-correction (JSON repair loop). For tool responses, `RETRY_MODIFIED`.

**Recovery:** The JSON repair loop handles LLM malformation. For tool malformation, log the raw response and attempt normalisation.

---

### 3. DEAD_API

**Definition:** An external service is unreachable, returning errors, or rate-limiting.

**Examples:**
- FreeHire returns HTTP 500 or 502
- FreeHire returns HTTP 429 (rate limited)
- DuckDuckGo blocks the request
- DNS resolution failure
- Connection refused

**Retry Policy:** `RETRY_SAME` with exponential backoff (Day 9). Bounded to 3 attempts.

**Recovery:** If all retries fail, mark the tool call as failed and let the agent decide whether to proceed without the data or stop.

---

### 4. TIMEOUT

**Definition:** An operation exceeded its allocated time budget.

**Examples:**
- LLM call exceeds 60 seconds
- HTTP request to FreeHire exceeds 20 seconds
- DuckDuckGo search exceeds 15 seconds

**Retry Policy:** `RETRY_SAME` with backoff. Bounded to 2 attempts.

**Recovery:** Enforce hard timeouts on every external call (Day 10). Log the timeout duration and threshold.

---

### 5. PARTIAL_COMPLETION

**Definition:** Some steps succeeded and some failed. The system has useful partial results.

**Examples:**
- Job 1 application generated successfully, Job 2 generation failed
- FreeHire search succeeded, DuckDuckGo research failed
- Cover letter generated, tailored CV bullets failed

**Retry Policy:** `RETRY_MODIFIED` — retry only the failed sub-step, not the entire run.

**Recovery:** Checkpoint the completed sub-steps (Day 11). Resume from the last successful checkpoint (Day 12). Include partial results in the final report with clear annotations (Day 13).

---

### 6. GUARDRAIL_TRIGGERED

**Definition:** The system deliberately stopped or modified execution to enforce a safety constraint.

**Examples:**
- Max-step limit reached
- Research budget exceeded (2 company research calls)
- Context window pruned due to token limit
- Input validation rejected bad data

**Retry Policy:** `NOT_RETRYABLE` — the guardrail is the correct behaviour. Do not retry.

**Recovery:** Log the guardrail trigger. Return whatever partial results exist. This is not a failure — it is the system working as designed.

---

### 7. CONTEXT_OVERFLOW

**Definition:** The context window exceeded the configured token limit.

**Examples:**
- Token count exceeds 30,000
- Message history too large for the model

**Retry Policy:** `RETRY_MODIFIED` — prune the context and retry.

**Recovery:** The context pruner (Day 4) handles this automatically. If pruning is insufficient, stop with partial results.

---

### 8. AUTH_ERROR

**Definition:** Authentication or authorisation failed for an external service.

**Examples:**
- OpenAI returns HTTP 401 (invalid API key)
- OpenAI returns HTTP 403 (insufficient permissions)
- API key has been revoked

**Retry Policy:** `MANUAL_INTERVENTION` — the user must fix their credentials. Do not retry.

**Recovery:** Stop immediately with a clear error message directing the user to check their `.env` file.

---

## Decision Matrix

| Category | Retry? | Backoff? | Max Attempts | Human Action? |
|----------|--------|----------|-------------|---------------|
| MISSING_DATA | Modified | No | 1 | Only if input is bad |
| MALFORMED_RESPONSE | Same | No | 2 (repair loop) | No |
| DEAD_API | Same | Exponential | 3 | No |
| TIMEOUT | Same | Exponential | 2 | No |
| PARTIAL_COMPLETION | Modified | No | 1 (failed sub-step) | No |
| GUARDRAIL_TRIGGERED | No | No | 0 | No |
| CONTEXT_OVERFLOW | Modified | No | 1 (prune + retry) | No |
| AUTH_ERROR | No | No | 0 | Yes — fix credentials |

---

## Design Principles

1. **Classify before you handle.** Never catch a bare `except Exception` without mapping it to a category.
2. **Bounded retries.** Every retry loop has a maximum attempt count. No infinite loops.
3. **Structured failure records.** Every failure is logged as a `FailureRecord` with category, retry policy, source, and original error type.
4. **Partial results are valuable.** A run that fails on step 4 of 6 still has 3 steps of useful data. Never discard it.
5. **Guardrails are not failures.** A system that stops itself at the right moment is working correctly.