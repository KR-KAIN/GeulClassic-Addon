"""Small independently curated in-game item glossary from user examples.

Not an official Korean localized catalog, and not a scraped third-party DB.
Exact, longer titles first; no single generic words like 'thought' or 'hammer'.
"""
from __future__ import annotations
import re

MARKET_NAMES={
    'meba': '메바',
    'fairy wing': '요정의 날개',
    "gentleman's mustache": '신사의 콧수염',
    'gentlemans mustache': '신사의 콧수염',
    'ink and wash thought bubble': '잉크 앤 워시 말풍선',
    'inkwash thought bubble': '잉크 앤 워시 말풍선',
    'ink and wash name tag': '잉크 앤 워시 이름표',
    'inkwash name tag': '잉크 앤 워시 이름표',
    'korean fan': '태극부채',
    'baby wings': '아기 날개',
    'toy hammer': '장난감 망치',
    'kitty shoes': '고양이 신발',
    'michael wings': '마이클 날개',
    'white choco bunny': '화이트 초코 버니',
    'black cat beanie': '검은 고양이 비니',
    'white beanie': '흰색 비니',
    'frameless glasses': '무테 안경',
    'starlight heart scepter': '스타라이트 하트 셉터',
    'cherry layered t': '체리 레이어드 티셔츠',
    'angel halo': '천사 헤일로',
    'slime slippers': '슬라임 슬리퍼',
    'ink and wash bubble': '잉크 앤 워시 말풍선',
    'black pig': '검은 돼지',
    'steely throwing knives': '뇌전 수리검',
    'tobi throwing stars': '토비 표창',
    'ilbi throwing stars': '일비 표창',
    'mokbi throwing stars': '목비 표창',
    'kumbi throwing stars': '금비 표창',
    'gloves attack scroll': '장갑 공격력 주문서',
    'glove attack scroll': '장갑 공격력 주문서',
    'one-handed sword attack': '한손검 공격력',
    'one handed sword attack': '한손검 공격력',
    'one-handed sword wa': '한손검 공격력',
    'one handed sword wa': '한손검 공격력',
}
_RX=re.compile(r'(?<!\w)(?:'+ '|'.join(re.escape(w) for w in sorted(MARKET_NAMES,key=len,reverse=True)) +r')(?!\w)',re.I)


def replace_market_items(value: str) -> str:
    """Replace known exact item titles only, never nicknames and URLs."""
    from .chat_safety import has_url_or_domain
    if has_url_or_domain(value):
        return value
    return _RX.sub(lambda m: MARKET_NAMES.get(m.group(0).casefold(),m.group(0)),value)
