"""Format limits for generated applications, shared by the prompt, the runtime guard and the evals.

The eval's format check used to hold limits that the generation prompt never stated, so a verbose
model failed rules it had not been given (Day 19 comparison). The limits now live here: the evals
enforce the hard limits, and the prompt asks for targets that sit inside them, so a model that
follows the prompt passes the check with margin.
"""
from typing import Any, List

# Hard limits (what the eval enforces).
MIN_BULLETS, MAX_BULLETS = 3, 4
MAX_BULLET_CHARS = 300
MIN_WORDS, MAX_WORDS = 150, 350

# Targets stated in the prompt: strictly inside the hard limits.
PROMPT_BULLET_CHARS = 240
# 220-300 was tried first and ignored: gpt-4o-mini wrote 173-179 words on average (46 letters, none
# inside 220-300, with or without "concise" in the prompt). The target now brackets what that model
# produces while still capping the verbose reasoning models (about 305-313 words on average).
PROMPT_MIN_WORDS, PROMPT_MAX_WORDS = 160, 300


def application_defects(bullets: Any, letter: Any) -> List[str]:
    """Defects that make an application unusable, as opposed to merely too long.

    These are worth a regeneration: missing bullets (a model that omitted the field), an empty
    letter, raw JSON or a code fence in place of a letter (the parse-failure fallback), or the
    "generation failed" placeholder.
    """
    problems: List[str] = []
    if not isinstance(bullets, list) or not any(str(b).strip() for b in bullets):
        problems.append("no CV bullets")
    text = str(letter or "")
    if not text.strip():
        problems.append("empty cover letter")
    else:
        if text.lstrip().startswith(("{", "```")):
            problems.append("cover letter is raw JSON or a code fence")
        if "generation failed" in text.lower():
            problems.append("cover letter is a failure placeholder")
    return problems
