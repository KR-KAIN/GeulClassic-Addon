"""Avoid presenting damaged Korean item links as known items.

Conservative display placeholder only; keep the original OCR text in the record.
No guessed dictionary substitutions are attempted.
"""
from __future__ import annotations
import re

_LINK = re.compile(r'\[([^\]\n]*)\]')
_CJK = re.compile(r'[\u3400-\u9fff\u3040-\u30ff]')

def contains_uncertain_link(message: str) -> bool:
    return any(not match.group(1).strip() or _CJK.search(match.group(1))
               for match in _LINK.finditer(message))


def protect_uncertain_links(message: str) -> str:
    """Keep visible OCR characters instead of discarding the player's item.

    LinkedItemOCR and the Korean whole-row retry run before this function.
    If neither can confirm the real item, preserve the source for diagnosis.
    Never present corrupted CJK glyphs as a verified Korean item name.
    """
    return message
