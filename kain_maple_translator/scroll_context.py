"""Context-aware Classic World scroll label parsing.

Only parse a COMPLETE recognized scroll name. Do not infer an item from a
corrupted fragment, a player's nickname, or a generic equipment description.
The suffix tier names/odds are aligned with the Classic World item database.
"""
from __future__ import annotations

import re

_SCROLL_ITEMS = {
    'pet equip': '펫 장비', 'pet equipment': '펫 장비',
    'pet eq': '펫 장비', 'pet equips': '펫 장비',
    'shoes': '신발', 'shoe': '신발',
    'gloves': '장갑', 'glove': '장갑',
    'overall': '전신갑옷', 'overall armor': '전신갑옷',
    'helmet': '투구', 'helm': '투구', 'earring': '귀고리', 'earrings': '귀고리',
    'cape': '망토', 'shield': '방패', 'claw': '아대', 'dagger': '단검',
    'spear': '창', 'polearm': '폴암', 'pole arm': '폴암',
    'wand': '완드', 'staff': '스태프', 'bow': '활',
    'crossbow': '석궁', 'xbow': '석궁',
    '1h sword': '한손검', '2h sword': '두손검',
    'one-handed sword': '한손검', 'two-handed sword': '두손검',
    '1h bw': '한손둔기', '2h bw': '두손둔기',
    '1h axe': '한손도끼', '2h axe': '두손도끼',
}
_STATS = {
    'speed': '이동속도', 'spd': '이동속도', 'jump': '점프력',
    'att': '공격력', 'atk': '공격력', 'attack': '공격력',
    'magic att': '마력', 'magic attack': '마력',
    'm.att': '마력', 'matk': '마력', 'magic attack': '마력',
    'def': '방어력', 'defense': '방어력',
    'str': '힘', 'dex': '민첩', 'int': '지력', 'luk': '행운',
    'hp': '체력', 'mp': '마나',
}
_TIER = {'lesser': '100', 'intermediate': '60', 'greater': '10'}
_ALIAS = {'gfa': ('장공', '공격력'), 'gma': ('장마', '마력')}
_RATE = re.compile(r'(?<!\w)(100|70|60|30|10|1)\s*%(?!\w)', re.I)


def scroll_reference(text: str) -> str | None:
    """Return Korean scroll label only for an unambiguous full scroll expression.

    Example: 'Pet Equip Speed Scroll: Intermediate' ->
        '펫 장비 이동속도 주문서 60%'.
    """
    raw = str(text).strip().strip('[]')
    if not raw or re.search(r'[가-힣]', raw):
        return None  # Already Korean item names must not be overwritten.
    # Some classic listings retain the older 'Scroll for X for ATT 60%'
    # syntax. This is an exact scroll context, not a global word replacement.
    raw = re.sub(r'(?i)^scroll\s+for\s+', '', raw)
    raw = re.sub(r'(?i)\s+for\s+(?=(?:m\.att|matk|magic\s+att(?:ack)?|att|atk|str|dex|int|luk|hp|mp|speed|jump)\b)', ' ', raw)
    s = re.sub(r'\s+', ' ', raw).strip().lower()
    # Clear OCR typographical spacing while refusing to hallucinate scrambled terms.
    s = re.sub(r'\s+%', '%', s)
    s = re.sub(r'\s*:\s*', ' ', s)
    explicit = _RATE.search(s)
    explicit_rate = explicit.group(1) if explicit else None
    if explicit:
        s = (s[:explicit.start()] + ' ' + s[explicit.end():]).strip()
    s = re.sub(r'\b(?:scrolls?|scrol1)\b', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    tier_match = re.search(r'\b(lesser|intermediate|greater|chaos)\s*$', s)
    tier = tier_match.group(1) if tier_match else None
    if tier:
        s = s[:tier_match.start()].strip()
    if not explicit_rate and not tier and 'scroll' not in str(text).lower() and s not in _ALIAS:
        # A generic 'glove attack' could be gear, not a scroll; explicit
        # percent, tier, or word 'scroll' establishes scroll context.
        return None
    if tier in _TIER and explicit_rate and _TIER[tier] != explicit_rate:
        return None  # Contradictory OCR, do not manufacture a success rate.
    rate = explicit_rate or _TIER.get(tier)
    if s in _ALIAS:
        base = _ALIAS[s][0]
    else:
        keys = sorted(_SCROLL_ITEMS, key=len, reverse=True)
        match = next(((item, s[len(item):].strip()) for item in keys if s.startswith(item + ' ')), None)
        if match is None:
            return None
        item, stat = match
        if stat not in _STATS:
            return None
        base = _SCROLL_ITEMS[item] + ' ' + _STATS[stat]
    if s in _ALIAS:
        name = base + ((' ' + rate + '%') if rate else '') + ' 주문서'
    else:
        name = base + (' 혼돈' if tier == 'chaos' else '') + ' 주문서'
        if rate:
            name += ' ' + rate + '%'
    return name
