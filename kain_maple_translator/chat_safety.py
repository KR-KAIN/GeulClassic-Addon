"""Protect URLs, actual item names, and badly OCR'd text from speculative MT.

A game chat OCR capture can contain parts of web links, incomplete fragments
and nicknames. English-to-Korean MT routinely corrupts these. These rules are
conservative: intact URL strings remain literal, without translating 'meso'
inside a domain or changing k/m suffixes to money.
"""
from __future__ import annotations
import re

_LINKISH = re.compile(r'(?ix)(?:https?\s*:\s*/\s*/|www\s*\.|\b[a-z0-9-]+\.(?:gg|com|net|org|kr|io|co)\b)')


def has_url_or_domain(text: str) -> bool:
    return bool(_LINKISH.search(str(text)))


def should_keep_untranslated(text: str) -> bool:
    value=str(text).strip()
    if has_url_or_domain(value):
        return True
    # A nonsensical lone punctuation fragment should not become a random
    # Korean phrase after greedy glossary / offline MT processing.
    if not re.search(r'[A-Za-z가-힣]',value):
        return True
    return False
