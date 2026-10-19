# Live API error probes

Generated: 20261019_165618. Prompt: "ping". No CV, no job data.

| Probe | Expected | Exception | Attempts | Category / policy | Gaps (s) |
|---|---|---|---|---|---|
| invalid key | 401 -> AUTH_ERROR / NOT_RETRYABLE, 1 attempt | AuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-inval**********test. You can | 1 | AUTH_ERROR / NOT_RETRYABLE | [] |
| unknown model | 404 -> UNKNOWN / NOT_RETRYABLE, 1 attempt (predicted from the classifier) | NotFoundError: Error code: 404 - {'error': {'message': 'The model `gpt-does-not-exist` does not exist or you do not | 1 | UNKNOWN / NOT_RETRYABLE | [] |
| 1 ms timeout | TIMEOUT / RETRY_SAME, 3 attempts, gaps about 1s then 2s | APIConnectionError: Connection error. | 3 | TIMEOUT / RETRY_SAME | [1.01, 2.01] |
| gpt-5.4 effort=minimal | 400 -> UNKNOWN / NOT_RETRYABLE (predicted), or model not available | BadRequestError: Error code: 400 - {'error': {'message': "Unsupported value: 'reasoning_effort' does not support 'min | 1 | UNKNOWN / NOT_RETRYABLE | [] |
