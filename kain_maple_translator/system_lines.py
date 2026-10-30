"""The game's own English status lines in the chat area (R20.3).

They have no speaker. OCR may still cut 'Your' into a fake nickname 'You'
(the row splitter takes the gap before 'r' for the name delimiter) or append
the line to the message above it. Matched on letters only, so
'You : pet is ...' and 'Your pet is ...' are the same line.
"""
from __future__ import annotations

import re

_SYSTEM_LINES = (
    (re.compile(r'\bpet is running low on the allotted (hp|mp) potions?\b'),
     lambda m: f'펫에게 지급한 {m.group(1).upper()} 물약이 얼마 남지 않았습니다.'),
    (re.compile(r'\bpet ran out of the allotted (hp|mp) potions?\b'),
     lambda m: f'펫에게 지급한 {m.group(1).upper()} 물약을 다 썼습니다.'),
)


def system_line(text: str) -> str | None:
    """Korean for a known game status line, or None for anything else."""
    letters = re.sub(r'[^a-z]+', ' ', str(text).lower()).strip()
    for pattern, korean in _SYSTEM_LINES:
        m = pattern.search(letters)
        if m:
            return korean(m)
    return None
