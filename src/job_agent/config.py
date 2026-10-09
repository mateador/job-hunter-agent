"""
Day 10: Centralized timeout configuration.

All timeout values in seconds. These are per-attempt timeouts;
the retry mechanism (Day 9) handles total elapsed time across attempts.
"""

import os

# LLM calls can be slow on long prompts or high load. Reasoning models (gpt-5 family) spend
# tens of seconds thinking before they write, so the default can be raised with the LLM_TIMEOUT
# environment variable (seconds). Read when the client is built, like the FREEHIRE_* settings.
LLM_TIMEOUT = 60.0


def get_llm_timeout() -> float:
    raw = os.getenv("LLM_TIMEOUT")
    try:
        value = float(raw) if raw else LLM_TIMEOUT
    except ValueError:
        return LLM_TIMEOUT
    return value if value > 0 else LLM_TIMEOUT

# FreeHire API: moderate payload, should respond quickly
FREEHIRE_TIMEOUT = 15.0

# DuckDuckGo search: web search, usually fast
DUCKDUCKGO_TIMEOUT = 10.0
