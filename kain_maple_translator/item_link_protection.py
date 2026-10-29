"""Preserve game-native bracket labels across mixed-language market translation."""
from __future__ import annotations
import re
BRACKETED_KOREAN = re.compile(r"\[[^\[\]\r\n]*[가-힣][^\[\]\r\n]*\]")

_MIXED_SCROLL=re.compile(
    r'\[\s*(장갑|아대|단검|한손검|두손검|창|폴암|활|석궁|망토|방패|신발|투구|귀고리|전신갑옷)\s*'
    r'(magic\s*attack|m\.?\s*att|matk|attack|atack|att|atk)\s*주문서'
    r'\s*(?:([:：])?\s*(초급|중급|상급|혼돈|lesser|intermediate|greater|chaos|\d{1,3}\s*[%％]))?\s*\]',re.I)


def normalize_mixed_scroll_link(link: str) -> str:
    """Repair only a complete mixed-script scroll template, never item guesses.

    Atack is the exact missing-letter form reported in the user screenshot.
    Existing native Korean labels and mixed bonus labels stay verbatim.
    """
    match=_MIXED_SCROLL.fullmatch(link)
    if not match:return link
    gear,stat,colon,tier=match.groups()
    stat='마력' if re.match(r'(?i)m',stat) else '공격력'
    suffix=''
    if tier:
        tier={'lesser':'초급','intermediate':'중급','greater':'상급','chaos':'혼돈'}.get(tier.casefold(),tier)
        tier=re.sub(r'\s+(?=[%％])','',tier).replace('％','%')
        suffix=(':' if colon or not tier.endswith('%') else ' ')+tier
    return '['+gear+' '+stat+' 주문서'+suffix+']'

def protect_hangul_links(text: str) -> str:
    """Normalize a single full-width bracket only when already properly paired.

    Never translate or guess the text inside a Hangul item link. OCR-damaged
    or unbalanced brackets remain unchanged for the existing separate retry.
    """
    # Unicode fullwidth brackets sometimes arrive from the OCR engine.
    text=re.sub(r'［([^［］\r\n]*[가-힣][^［］\r\n]*)］',
                lambda m:'['+m.group(1)+']',text)
    return BRACKETED_KOREAN.sub(lambda m:normalize_mixed_scroll_link(m.group()),text)
