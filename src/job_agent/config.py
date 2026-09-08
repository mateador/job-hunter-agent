"""
Day 10: Centralized timeout configuration.

All timeout values in seconds. These are per-attempt timeouts;
the retry mechanism (Day 9) handles total elapsed time across attempts.
"""

# LLM calls can be slow on long prompts or high load
LLM_TIMEOUT = 60.0

# FreeHire API: moderate payload, should respond quickly
FREEHIRE_TIMEOUT = 15.0

# DuckDuckGo search: web search, usually fast
DUCKDUCKGO_TIMEOUT = 10.0
