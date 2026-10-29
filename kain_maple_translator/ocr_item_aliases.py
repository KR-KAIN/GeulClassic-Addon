"""Explicitly confirmed OCR-only spelling repairs for linked game items.

Unlike edit-distance autocorrection, this never guesses item names. Each
entry comes from an observed replay fixture and applies only to a complete
[bracketed link] with the exact observed spelling. Nicknames, trade content,
prices, free prose and unknown item labels are never changed.
"""
from __future__ import annotations
import re

_CONFIRMED_LINK_ALIASES = {
    "denim winkled skirt": "Denim Wrinkled Skirt",
}
_BRACKET = re.compile(r"\[[^\[\]\r\n]{1,120}\]")


def repair_confirmed_item_link(text: str) -> str:
    """Correct only known exact OCR errors in complete bracketed link names."""
    if not text or "[" not in text:
        return text

    def replacement(match: re.Match[str]) -> str:
        raw = match.group(0)
        corrected = _CONFIRMED_LINK_ALIASES.get(raw[1:-1].casefold().strip())
        return "[" + corrected + "]" if corrected is not None else raw

    return _BRACKET.sub(replacement, text)
