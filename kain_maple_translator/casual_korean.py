"""Small, safe post-edit layer for free-form Maple chat.
Avoid generic machine word swaps that could change meaning or player intent.
"""
from __future__ import annotations
import re

_RULES=(
  (r'\b(?:where should we train|where do we train)\??', '어디서 사냥할까요?'),
  (r'\b(?:anyone want(s)? to party|anyone up for party)\??', '파티하실 분?'),
  (r'\b(?:could you|can you) invite me\??', '파티 초대 좀 해주세요'),
  (r'\b(?:nerfed|got nerfed)\b', '너프됐어요'),
)

_KO_CALQUES=((r'그들이\s+(.{1,32})\s*하는\s*것처럼\s*느껴져',r'걔네가 \1하는 느낌이야'),
            (r'그들은\s+(.{1,32})\s*하고\s*있습니다',r'걔네가 \1하고 있어요'),
            (r'\b버프를\s*주는\s*중입니다', '버프해 주고 있어요'),
            (r'\b너프를\s*하고\s*있습니다','너프하고 있어요'),
            (r'\b그것은\s*저의\s*','그거 제 '))


def naturalize_free_chat(source: str, translated: str)->str:
    """Only stylistic Korean rewrites with strong source evidence."""
    if not re.search('[가-힣]',translated):return translated
    if re.search(r'(?i)\b(?:c/o|a/w|s>|b>|\d+(?:\.\d+)?[kmb])\b',source):return translated
    cleaned=translated
    for p,repl in _KO_CALQUES:
        cleaned=re.sub(p,repl,cleaned)
    # No digits/items are allowed to disappear in a conversational clean-up.
    nums=lambda s:re.findall(r'\d+(?:[.,]\d+)*',s)
    return cleaned if nums(cleaned)==nums(translated) else translated
