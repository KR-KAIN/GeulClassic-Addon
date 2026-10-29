"""Whole-message game intents and explicit trade structure, before generic MT.

Unknown names and unqualified numbers remain literal. Never guess a missing
trade direction, currency multiplier, stat percentage, or item name.
"""
from __future__ import annotations
import re
from .chat_safety import has_url_or_domain


def emoticon_tail(text):
    """Only detach unambiguous trailing faces; do not alter names or numbers."""
    match=re.fullmatch(r'(.+?)\s+(\^\s*[_-]?\s*\^|<3)',text)
    if match is None:
        # Video OCR may close the gap in "ty <3". Require a textual core
        # so a numeric comparison like 2<3 is never treated as a heart.
        match=re.fullmatch(r'([A-Za-z][A-Za-z\s]*)(<3)',text)
    return (match.group(1),match.group(2)) if match else None


def linked_price(text):
    """A link followed only by a price states no buy/sell direction."""
    match=re.fullmatch(r'(\[[^\]\n]+\])\s+(\d+(?:\.\d+)?\s*[kmb])[.!]*',text,re.I)
    if match:
        from .natural_trade import _money
        from .megaphone_item_translation import localized_item_text
        return localized_item_text(match.group(1))+' · 가격 '+_money(match.group(2))
    return None


def attention_tail(text):
    """Detach only repeated trailing @ decorations; preserve emails/mentions."""
    if has_url_or_domain(text):
        return None
    match=re.search(r'(?:\s*@){3,}\s*$',text)
    if match and match.start()>0:
        return text[:match.start()].rstrip(),text[match.start():].strip()
    return None


def party_intent(text):
    value=re.sub(r'\s+',' ',text.strip()).strip(' .!?~≈').casefold()
    original=value
    face=re.search(r'\s*([\^_*]+(?:\s*[_^*]+)*)$',value)
    decoration=''
    if face:
        decoration=' '+face.group(1)
        value=value[:face.start()].rstrip()
    match=re.fullmatch(r'j\s*>?\s*(pq|pt)(?:\s*(rush|bonus))?',value)
    if match:
        target='파티 퀘스트' if match.group(1)=='pq' else '파티'
        tail={'rush':' 연속 진행','bonus':' 보너스 구간',None:''}[match.group(2)]
        return target+tail+' 참가 원해요'+decoration
    if original!='gz' and re.fullmatch(r'gz{1,12}(?:\s*\*+)?',original):
        return '축하해요!'
    return None


def announcement_intent(text):
    """Complete announcement grammars seen in the video; keep named slots."""
    match=re.fullmatch(r'(\[[^\]\n]+\]\s*)?GRATZ\s+ON\s+([A-Za-z][A-Za-z0-9_]*)\s+'
        r'LVL\s+(\d+)\s+BEST\s+GUILD\s+LEADER\s+EVER\s+(?:PLS|please)\s+BUY\s+ME\s+(.+)',text,re.I)
    if match:
        link,name,level,wanted=match.groups()
        return (link or '')+f'{name} {level}레벨 달성 축하해요! 최고의 길드장이에요. {wanted} 사주세요'
    match=re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)\s+obtained\s+(\[[^\]\n]+\])\s+'
        r'from\s+the\s+(.+?)!\s+Congrats!',text,re.I)
    if match:
        name,item,box=match.groups()
        from .megaphone_item_translation import localized_item_text
        return f'{name}: {box}에서 {localized_item_text(item)} 획득! 축하해요!'
    return None


def mixed_trade_parts(text):
    """Split independent B>/S>/T> clauses outside immutable linked labels."""
    from .trade_memory import split_clauses
    if len(split_clauses(text))>1 or len(re.findall(r'\[[^\]\n]*\]',text))>1:
        return None
    masked=re.sub(r'\[[^\]\n]*\]',lambda m:' '*len(m.group()),text)
    matches=list(re.finditer(r'(?<![A-Za-z0-9])([SBT])\s*>',masked,re.I))
    if len(matches)<2 or len({m.group(1).upper() for m in matches})<2:
        return None
    if masked[:matches[0].start()].strip():
        return None
    starts=[0]+[m.start() for m in matches[1:]]+[len(text)]
    return [text[a:b].strip(' ,;') for a,b in zip(starts,starts[1:])]


def trade_tail(text):
    if not re.match(r'^(?:\[[^\]\n]+\]\s*)?(?:[SBT]\s*>|WT[SB]\b)',text,re.I):
        return None
    match=re.fullmatch(r'(.+?)[.!\s-]+(?:PM\s+ME\s+(?:w|with)\s+offers?|(?:BUY\s*/\s*)?OFFER\s+ME)[.!\s]*',text,re.I)
    if match:
        return match.group(1).strip(),'가격 제안 주세요'
    # 'just message or ask me price' / 'msg me or ask price'
    match=re.fullmatch(r'(.+?)[,.!\s-]+(?:just\s+)?(?:message|msg|pm|whisper|w)(?:\s+me)?\s+or\s+ask'
                       r'(?:\s+me)?(?:\s+for)?(?:\s+the)?\s+prices?[.!\s]*',text,re.I)
    if match:
        return match.group(1).strip(' ,'),'귓말이나 가격 문의 주세요'
    match=re.fullmatch(r'(.+?)[,.!\s-]+(?:just\s+)?ask(?:\s+me)?(?:\s+for)?(?:\s+the)?\s+prices?[.!\s]*',text,re.I)
    if match:
        return match.group(1).strip(' ,'),'가격 문의 주세요'
    match=re.fullmatch(r'(.+?)\s+(?:please|plese)\s+be\s+patient\s+when\s+tr\s*ading[.!\s]*',text,re.I)
    if match:
        return match.group(1).strip(),'거래할 때 조금만 기다려 주세요'
    match=re.fullmatch(r'(.+?)[.!\s]+(?:DM\s+M\s*E|PM\s+M\s*E)[.!\s]*',text,re.I)
    if match:
        return match.group(1).strip(' ,;'),'귓말 주세요'
    # A contact suffix after market coordinates otherwise prevents the
    # CH/FM parser from seeing the coordinates at the end of the listing.
    match=re.fullmatch(r'(.+?\bFM\s+(?:room\s*)?\d+)\s+PMO[.!\s]*',text,re.I)
    if match:
        return match.group(1).strip(),'귓말 주세요'
    match=re.fullmatch(r'(.+?\d+(?:\.\d+)?\s*[kmb])\s+right\s+away[.!\s]*',text,re.I)
    if match:
        return match.group(1),'바로 거래 원해요'
    return None


def explicit_trade(text):
    from .natural_trade import _item, _money
    from .market_item_terms import replace_market_items
    def item(v):
        # 'T> my Cat Soul for Evil Skull': no 'my', and every known name in Korean
        v=re.sub(r'(?i)^(?:my|your|ur)\s+','',v.strip())
        out=replace_market_items(_item(v))
        try:
            from .classic_item_index import current_index
            out=current_index().replace_verified(out)
        except Exception:
            pass
        return out
    # These are entire trade structures, not token substitutions in prose.
    # Keep unknown item names literal and attach each price to its option.
    from .trade_stats import alternative_stat_offers
    options=alternative_stat_offers(text)
    if options is not None:
        return options
    match=re.fullmatch(r'B\s*>\s*Looking\s+for\s+(.+?)[.!]*',text,re.I)
    if match:
        names=re.split(r'\s+or\s+',match.group(1),flags=re.I)
        return ' 또는 '.join(item(name) for name in names)+' 삽니다'
    match=re.fullmatch(r'B\s*>\s*(.+?)\s+(\d+(?:\.\d+)?\s*[kmb])\s+NEED\s+(\d+)[.!]*',text,re.I)
    if match:
        name,price,count=match.groups()
        return f'{item(name)} {count}개 삽니다. 제시 가격 {_money(price)} (개당 여부 미표기)'
    match=re.fullmatch(r'(S\s*>|B\s*>|sell|buy)\s*(100|70|60|30|10|1)\s*%\s+scro{1,2}ll?s[.!]*',text,re.I)
    if match:
        action='팝니다' if match.group(1).casefold().replace(' ','') in ('s>','sell') else '삽니다'
        return match.group(2)+'% 주문서 '+action
    match=re.fullmatch(r'B\s*>\s*(?:lvl?|level)\s*(\d+)\s+(?:assasin|assassin)\s+top/chest/bottoms[.!]*',text,re.I)
    if match:
        return match.group(1)+'레벨 어쌔신 상의/가슴 방어구/하의 삽니다'
    match=re.fullmatch(r'(S\s*>|B\s*>)\s*(Pet\s+Speed\s+(?:100|70|60|30|10|1)\s*%)\s*(\(\d+\))[.!]*',text,re.I)
    if match:
        action='팝니다' if match.group(1).upper().replace(' ','')=='S>' else '삽니다'
        # Parenthesized number remains a source annotation; no invented unit.
        rate=re.search(r'\d+\s*%',match.group(2)).group().replace(' ','')
        return f'펫 장비 이동속도 {rate} 주문서 {match.group(3)} {action}'
    # A ratio is a ratio, not a meso price. Preserve source quantity and order.
    match=re.fullmatch(r'(\[[^\]\n]+\]\s*)?T\s*>\s*(.+?)\s+for\s+(.+?)(?:,\s*(firm))?[.!]*',text,re.I)
    if match:
        label,offered,wanted,firm=match.groups()
        ratio=re.search(r'\s+(\d+\s*:\s*\d+)\s*$',wanted)
        ratio_text=''
        if ratio:
            wanted=wanted[:ratio.start()];ratio_text=' ('+re.sub(r'\s+','',ratio.group(1))+')'
        if offered.casefold()=='this' and label:
            offered=label.strip();label=''
        prefix=(label.strip()+' · ') if label else ''
        return prefix+item(offered)+' → '+item(wanted)+' 교환'+ratio_text+('. 조건 고정' if firm else '')
    # Bare 60 ea is explicitly per-unit, but has no currency unit in source.
    match=re.fullmatch(r'(S\s*>|B\s*>|WTS|WTB)\s*(.+?)\s*,?\s+(\d+)\s*(mesos?)?\s*(ea|each)[.!]*',text,re.I)
    if match:
        verb,name,amount,currency,_=match.groups()
        action='팝니다' if verb.upper().replace(' ','') in ('S>','WTS') else '삽니다'
        # No unit in the source: keep the bare price (never invent mesos),
        # without the awkward '(단위 미표기)' note.
        return item(name.strip(' ,'))+' '+action+'. 개당 '+amount+(' 메소' if currency else '')
    return None
