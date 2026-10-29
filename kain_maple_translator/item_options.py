"""Options a seller typed next to an item link (R19).

'[Work Gloves] S> 8 att 3 slots 9m'  -> {'incWAT': 8, 'slots': 3}
'S> 6ATT WG 2.6m'                   -> {'incWAT': 6}
'[Earrings] +3 luk +2 crit clean'    -> {'incLUK': 3, 'incCRT': 2, 'clean': True}

Numbers are the totals the seller claims (what the game tooltip would
show), never prices ('luk 50k', '60% INT scroll' are not stats).
"""
from __future__ import annotations

import re

# stat word -> item-info key (Classic World uses incWAT/incMAT for attack)
_WORDS = [
    (r'(?:w\.?\s*)?att(?:ack)?|atk|w\.?atk|watk|wa', 'incWAT'),
    (r'm\.?\s*att(?:ack)?|matk|m\.?atk|matt|ma|magic\s+att(?:ack)?', 'incMAT'),
    (r'str', 'incSTR'), (r'dex', 'incDEX'), (r'int', 'incINT'), (r'luk|luck', 'incLUK'),
    (r'(?:max\s*)?hp|mhp', 'incMHP'), (r'(?:max\s*)?mp|mmp', 'incMMP'),
    (r'w\.?\s*def|wdef|def(?:ense)?', 'incPDD'), (r'm\.?\s*def|mdef', 'incMDD'),
    (r'acc(?:uracy)?', 'incACC'), (r'avoid(?:ability)?|avoi|eva(?:sion)?', 'incEVA'),
    (r'speed|spd', 'incSpeed'), (r'jump', 'incJump'),
    (r'crit(?:ical)?\s*(?:dmg|damage)|cd', 'incCRD'), (r'crit(?:ical)?|cri|crt', 'incCRT'),
]
_STAT = '|'.join(f'(?P<k{i}>{p})' for i, (p, _) in enumerate(_WORDS))
# number BEFORE the word ('8 att', '+3 luk', '8atk') or AFTER it ('att 8', 'luk+3')
_BEFORE = re.compile(r'(?<![\w.%/])\+?\s*(?P<n>\d{1,4})\s*(?P<w>' + _STAT + r')(?![a-z%])', re.I)
_AFTER = re.compile(r'(?<![a-z])(?P<w>' + _STAT + r')\s*[:=+]?\s*(?P<n>\d{1,4})(?![\d.]|\s*[kmb%]\b|\s*%|[a-z])', re.I)
_SLOTS = re.compile(r'(?<![\d.])(?P<n>\d{1,2})\s*(?:slots?|upgrades?|upg|tuc)\b(?:\s*(?:left|remaining|avail(?:able)?))?', re.I)
_NO_SLOTS = re.compile(r'\b(?:no|0)\s*slots?\b|\bno\s+upgrades?\b', re.I)
_CLEAN = re.compile(r'\bclean\b|노작', re.I)


def _key_of(match) -> str | None:
    for i, (_, key) in enumerate(_WORDS):
        if match.group(f'k{i}'):
            return key
    return None


def _plausible(key: str, n: int) -> bool:
    if key in ('incMHP', 'incMMP'):
        return 1 <= n <= 2000
    if key in ('incCRT', 'incCRD'):
        return 1 <= n <= 100
    return 1 <= n <= 300


def seller_options(text: str) -> dict:
    """Stats the seller wrote, plus 'slots' (upgrades left) and 'clean'."""
    out: dict = {}
    if not text:
        return out
    # prices, percentages and channel/room numbers are never stats
    body = re.sub(r'\d+(?:\.\d+)?\s*[kmb]\b', ' ', text, flags=re.I)
    body = re.sub(r'\d+\s*%', ' ', body)
    body = re.sub(r'\b(?:ch|cc|fm)\s*\d+', ' ', body, flags=re.I)
    body = re.sub(r'\b(?:lv|lvl|level)\s*\.?\s*\d+', ' ', body, flags=re.I)
    for rx in (_BEFORE, _AFTER):
        for m in rx.finditer(body):
            key = _key_of(m)
            n = int(m.group('n'))
            if key and key not in out and _plausible(key, n):
                out[key] = n
    m = _SLOTS.search(body)
    if m:
        out['slots'] = int(m.group('n'))
    elif _NO_SLOTS.search(body):
        out['slots'] = 0
    if _CLEAN.search(text):
        out['clean'] = True
    return out


def options_for_label(original: str, label_index: int) -> dict:
    """Options written for the hovered item only: the text after its link up
    to the next link (a post can sell several items)."""
    text = original or ''
    spans = list(re.finditer(r'\[[^\[\]\n]+\]', text))
    if not spans:
        return seller_options(text)
    if not 0 <= label_index < len(spans):
        label_index = 0
    start = spans[label_index].end()
    end = spans[label_index + 1].start() if label_index + 1 < len(spans) else len(text)
    part = text[start:end]
    if len(spans) == 1:
        part = text[:spans[0].start()] + ' ' + part
    return seller_options(part)
