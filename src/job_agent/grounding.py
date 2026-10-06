"""Number grounding: figures in a generated application must come from the supplied sources.

Used at runtime to catch invented metrics before they reach the report, and by the evals to
score the same property. It checks numbers only: an invented employer or skill without a
figure attached is not detected.
"""
import re
from typing import Iterable, List, Optional, Set

_NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
_NUMBER_WORDS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60",
                      "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100"})
# Digits not glued to letters ("1st", "2m" are skipped); a trailing % is allowed and ignored.
_NUMBER = re.compile(r"(?<![\w.,])\d[\d,]*(?:\.\d+)?(?!\w)")


def extract_numbers(text: Optional[str]) -> Set[str]:
    """Numeric values in text, normalised: '1,000' -> '1000', '30%' -> '30', 'eighteen' -> '18'."""
    if not text:
        return set()
    found = {m.group().replace(",", "").rstrip(".") for m in _NUMBER.finditer(text)}
    found = {n[:-2] if n.endswith(".0") else n for n in found}
    found |= {_NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", text.lower()) if w in _NUMBER_WORDS}
    return found


def ungrounded_numbers(output_text: str, sources: Iterable[Optional[str]]) -> List[str]:
    """Numbers in output_text that appear in none of the source texts, smallest first."""
    allowed: Set[str] = set()
    for source in sources:
        allowed |= extract_numbers(source)
    return sorted(extract_numbers(output_text) - allowed, key=lambda n: (len(n), n))
