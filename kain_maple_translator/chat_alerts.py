"""Chat keyword alerts (R18): tell the player when a watched word appears.

Words are matched in the original line AND the translation, ignoring case
and spaces, so '노가다 목장갑' also fires on 'S> Work Gloves 11att'.
The same message is announced once, even when the megaphone repeats.
"""
from __future__ import annotations

import re
import time


def _norm(text: str) -> str:
    return re.sub(r'\s+', '', str(text or '')).casefold()


def parse_keywords(text: str) -> list[str]:
    """One keyword per line or comma; blanks and duplicates dropped."""
    out = []
    for part in re.split(r'[\n,]+', str(text or '')):
        word = part.strip()
        if len(_norm(word)) >= 2 and word not in out:
            out.append(word)
    return out[:100]


class KeywordAlerts:
    def __init__(self, keywords=(), repeat_after: float = 120.0, clock=time.monotonic):
        self.keywords: list[str] = []
        self.repeat_after = float(repeat_after)
        self.clock = clock
        self._seen: dict[str, float] = {}
        self.set_keywords(keywords)

    def set_keywords(self, keywords):
        self.keywords = [k for k in (keywords or []) if len(_norm(k)) >= 2]
        self._keys = [(k, _norm(k)) for k in self.keywords]

    def check(self, nickname: str, original: str, translated: str) -> str | None:
        """The first keyword found, or None (also None for a recent repeat)."""
        if not self._keys:
            return None
        hay = _norm(original)+'\n'+_norm(translated)
        hit = next((word for word, key in self._keys if key in hay), None)
        if hit is None:
            return None
        now = self.clock()
        seen_key = _norm(nickname)+'|'+_norm(original)[:120]
        last = self._seen.get(seen_key)
        if last is not None and now-last < self.repeat_after:
            return None
        self._seen[seen_key] = now
        if len(self._seen) > 500:
            cutoff = now-self.repeat_after
            self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}
        return hit
