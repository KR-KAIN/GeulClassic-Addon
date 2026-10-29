"""High-confidence classic Maple market chat interpreter.

Conservative: preserve all quantities, named items, suffixes, and uncertainty.
Unmatched text continues to the offline model. Does not guess missing prices.
"""
from __future__ import annotations
from decimal import Decimal
import re
from .glossary import money_ko, scroll_label
from .expanded_terms import exact_label
from .scroll_context import scroll_reference
from .scroll_intelligence import scroll_name

_SPACE = re.compile(r'\s+')
_MARKET = re.compile(r'^\s*(?:(?:\[.*?\]\s*)?)(S\s*>|B\s*>|WTS\b|WTB\b|SELLING\b|BUYING\b)\s*(.+)$', re.I)
_PRICE = r'(\d+(?:\.\d+)?\s*[kmb])'
_ITEM_NAMES = {
    'tobi':'토비 표창', 'tobis':'토비 표창', 'fame':'인기도',
    'meba':'메바', 'cromi':'크로미', 'wg':'노가다 목장갑', 'gfa':'장갑 공격력 주문서',
    'race queen uniform':'레이스 퀸 유니폼', 'snail':'달팽이',
    'tourist t':'관광객 티셔츠', 'cherry layered t':'체리 레이어드 티셔츠',
    'orange hooded vest':'오렌지 후드 조끼', 'iron ores':'철광석',
    'iron ore':'철광석', 'inv slots':'인벤토리 슬롯',
    'inv slot':'인벤토리 슬롯', 'mask':'마스크',
    'sp reset':'SP 초기화권', 'sp resets':'SP 초기화권',
    'sp reset scroll':'SP 초기화권', 'skill point reset':'SP 초기화권',
    'white beanie':'흰색 비니', 'pink bunny sweater':'분홍 토끼 스웨터',
    'red check rider':'빨간 체크 라이더',
    'michael wings':'마이클 날개', 'frameless glasses':'무테 안경',
    'ragged top':'해진 상의', 'ink and wash name tag':'잉크 앤 워시 이름표',
    'starlight heart scepter':'스타라이트 하트 셉터',
    'gentlemans mustache':'신사의 콧수염',
    "gentleman's mustache":'신사의 콧수염',
    'mustache':'콧수염', 'beanie':'비니', 'ears':'귀', 'black suit pants':'검은 정장 바지',
    'wooden top':'나무 상의', 'nine dragons':'나인 드래곤즈',
    'nx':'캐시 아이템', 'trash nx':'잡캐시템', 'junk nx':'잡캐시템',
    'mokbi':'목비', 'mokbi throwing stars':'목비 표창',
    'wooden tops':'나무팽이 표창', 'wooden top':'나무팽이 표창',
    'black blazer':'검은 블레이저', 'bunny earmuffs':'토끼 귀마개',
    'slingshot':'새총', 'kumbi':'금비 표창', 'kumbis':'금비 표창',
    'nx trash':'잡캐시템',
    'claw 60%':'아대 공격력 주문서 60%',
    'glove atk 60%':'장공 60% 주문서',
    'glove att 60%':'장공 60% 주문서',
    'gfa 60%':'장공 60% 주문서',
    'earring luk':'귀고리 럭',
    'nordic steel helm':'노르딕 강철 투구',
    'shoes speed lesser 100% scroll':'신발 이동속도 하급 주문서 100%',
    'shoe speed lesser 100% scroll':'신발 이동속도 하급 주문서 100%',
    'shoe speed 100%':'신발 이동속도 주문서 100%',
    'shoes speed 100%':'신발 이동속도 주문서 100%',
    'shoes speed lesser':'신발 이동속도 하급',
    'starlight heart scepter p':'스타라이트 하트 셉터',
    'heart scepter':'하트 셉터',
    'white choco bunny':'화이트 초코 버니',
    'choco bunny':'초코 버니',
    'pink bunny':'핑크 버니',
    'cute mouse ears':'귀여운 쥐 귀',
    'gentlemans mustache':'신사의 콧수염',
    'aura mystery fashion crate':'오로라 미스터리 패션 상자',
    'inkwash thought bubble':'잉크 앤 워시 말풍선',
    'ink and wash thought bubble':'잉크 앤 워시 말풍선',
    'korean fan':'태극부채',
    'baby wings':'아기 날개', 'serpent\'s tongue':'장팔사모',
    'toy hammer':'장난감 망치',
    'kitty shoes':'고양이 신발',
}


def _money(value: str) -> str:
    """Display exact Maple mesos in Korean units, never round prices."""
    cleaned=re.sub(r'\s+','',value).lower()
    match=re.fullmatch(r'(\d+(?:\.\d+)?)([kmb])',cleaned)
    if not match:return money_ko(cleaned) or value
    amount=Decimal(match.group(1))*{'k':1000,'m':1000000,'b':1000000000}[match.group(2)]
    if amount!=amount.to_integral_value():return money_ko(cleaned) or value
    remaining=int(amount)
    parts=[]
    for unit,word in ((100000000,'억'),(10000,'만'),(1000,'천')):
        n,remaining=divmod(remaining,unit)
        if n:parts.append(f'{n:,}{word}')
    if remaining:parts.append(f'{remaining:,}')
    return ' '.join(parts or ['0'])+' 메소'


def _item(text: str) -> str:
    """Only replace known equipment; unknown items keep their original name."""
    t=_SPACE.sub(' ',text.strip())
    if not t:return ''
    if re.fullmatch(r'\[[^\[\]\n]*[가-힣][^\[\]\n]*\]',t):
        return t
    # User-imported, authorized catalog takes precedence over guessed names.
    from .item_catalog import current_catalog
    authorized=current_catalog().lookup(t)
    if authorized:
        return authorized
    # The [Korean item title] supplied by the game is authoritative text.
    # Never strip the brackets or translate its Korean name through MT.
    if re.fullmatch(r'\[[^\[\]\n]*[가-힣][^\[\]\n]*\]',t):
        return t
    # Explicit weapon-attack stat bonus on a scroll. Distinguish "+2" from
    # an item's upgrade count and preserve the percentage; do not reinterpret
    # arbitrary OCR words as a specific scroll.
    bonus_scroll = re.fullmatch(
        r'(?:one[\s-]*handed\s+sword|1h\s*sword)\s+(?:wa|watk|atk|att)\s*\+\s*(\d{1,2})\s+'
        r'(100|70|60|30|10)\s*%\s*(?:scr|scroll)', t, re.I)
    if bonus_scroll:
        return f'한손검 공격력 +{bonus_scroll.group(1)} {bonus_scroll.group(2)}% 주문서'
    scroll = scroll_name(t) or scroll_reference(t) or scroll_label(t)
    if scroll:return scroll + (' 주문서' if '주문서' not in scroll else '')
    exact=exact_label(t)
    if exact:return exact
    lower=t.casefold()
    # Percentage must be tied to known scroll labels.
    scroll_pct=re.fullmatch(r'gfa\s*(\d{1,3})\s*%',t,re.I)
    if scroll_pct:return f'장공 {scroll_pct.group(1)}% 주문서'
    if lower in _ITEM_NAMES:return _ITEM_NAMES[lower]
    # OCR sometimes writes "60 %" or "Glove atk"; normalize just the
    # equipment label, not prices, upgrade slots or player names.
    tight=re.sub(r'\s+%', '%',lower)
    if tight in _ITEM_NAMES:return _ITEM_NAMES[tight]
    # 'BOW 60%' in a trade listing denotes the bow attack scroll, not
    # an unspecified bow with 60% stats. Do not change bare 'bow' in prose.
    bow_scroll = re.fullmatch(r'(bow|crossbow|xbow)\s+(10|30|60|70|100)\s*%', tight)
    if bow_scroll:
        label = '활' if bow_scroll.group(1) == 'bow' else '석궁'
        return f'{label} 공격력 주문서 {bow_scroll.group(2)}%'
    if re.fullmatch(r'claw\s+(?:10|30|60|70|100)\s*%',tight):
        return f'아대 공격력 주문서 {re.search(r"\d+",tight).group()}%'
    if re.fullmatch(r'(?:glove|gloves)\s+(?:atk|att)\s+(?:10|30|60|70|100)\s*%',tight):
        return f'장공 {re.search(r"\d+",tight).group()}% 주문서'

    equip=re.fullmatch(r'(?:lv|lvl|level)\s*(\d{1,3})\s+(thief|warrior|mage|bowman|archer)\s+(dex|str|int|luk)\s+(?:equips?|gear)',lower,re.I)
    if equip:
        role={'thief':'도적','warrior':'전사','mage':'마법사','bowman':'궁수','archer':'궁수'}[equip.group(2).lower()]
        stat={'dex':'덱스','str':'힘','int':'인트','luk':'럭'}[equip.group(3).lower()]
        return f'{equip.group(1)}레벨 {role}용 {stat} 장비'
    if re.fullmatch(r'(?:all|any)\s+iron\s+ores?', lower):
        return '철광석 전부'
    # Explicit scroll combinations: do not manufacture a nonexistent single
    # scroll for a plus sign joining unrelated attributes.
    multi=re.fullmatch(r'(claw\s+\d{1,3}\s*%)\s+(earring\s+luk\s*\+\s*crit\s+\d{1,3}\s*%)',tight)
    if multi:
        return _item(multi.group(1))+' / 귀고리 럭+크리티컬 '+re.search(r'\d{1,3}\s*%$',multi.group(2)).group().replace(' ','')
    # Multi-item offers preserve separators and each known item name.
    # A slash can separate two known sale items, e.g. Mokbi/Wooden Tops.
    # Do not split arbitrary stats like STR/DEX or unknown product names.
    if '/' in t:
        bits=[chunk.strip() for chunk in t.split('/')]
        # Slash-separated names all explicitly recognized; do not assume
        # arbitrary slashes are delimiters (e.g. STR/DEX or a URL).
        if (2 <= len(bits) <= 5 and
            all(chunk.casefold() in _ITEM_NAMES for chunk in bits)):
            return ' / '.join(_ITEM_NAMES[chunk.casefold()] for chunk in bits)
    if ' & ' in t:
        return ' & '.join(_item(bit) for bit in t.split(' & '))
    # Comma-delimited names are separate listings, not a single unknown item.
    if ', ' in t:
        return ', '.join(_item(bit) for bit in t.split(', '))
    for key,kor in sorted(_ITEM_NAMES.items(),key=lambda e:-len(e[0])):
        if lower.startswith(key+' '):
            return kor+t[len(key):]
    return t


def _notes(value: str) -> str:
    """Extract recognized annotations without interpreting the main item."""
    return value


def priced_item_list(source: str) -> str | None:
    """Translate only clearly segmented item+price lists, preserving each price."""
    market = _MARKET.match(_SPACE.sub(' ',source).strip())
    if not market:return None
    tag,tail=market.groups()
    # Market listings with bids/buyout go through the existing dedicated path.
    if re.search(r'(?i)\b(?:c\s*/\s*o|a\s*/?\s*w|h\s*/\s*o|res)\b',tail):
        return None
    linked_chain=re.fullmatch(r'\s*((?:\[[^\]\n]+\]\s+\d+(?:\.\d+)?\s*[kmb]\s*){2,8})\s*',tail,re.I)
    if linked_chain:
        parts=re.findall(r'(\[[^\]\n]+\])\s+(\d+(?:\.\d+)?\s*[kmb])\b',tail,re.I)
        if len(parts)>=2:
            action='팝니다' if tag.lower().replace(' ','') in ('s>','wts','selling') else '삽니다'
            return ', '.join(f'{_item(name)} {_money(price)}' for name,price in parts)+' '+action
    segments=re.split(r'\s*[,|]\s*|\s+/\s+',tail.rstrip(' ,'))
    if len(segments)<2:
        # Classic sellers omit commas: "trash NX 18k mustache 80k ...".
        # Parse only a fully consumed chain of explicit names and prices.
        pattern=re.compile(r'\s*([A-Za-z][A-Za-z0-9\s\x27+\-]{1,66}?)\s+(\d+(?:\.\d+)?\s*[kmb])\b',re.I)
        matches=list(pattern.finditer(tail))
        if not 2<=len(matches)<=8:return None
        cursor=0
        for match in matches:
            if tail[cursor:match.start()].strip():return None
            if re.match(r'(?i)(?:and|or|for|then|offers?)\b',match.group(1).strip()):return None
            cursor=match.end()
        if tail[cursor:].strip():return None
        names=[f'{_item(m.group(1))} {_money(m.group(2))}' for m in matches]
        action='팝니다' if tag.lower().replace(' ','') in ('s>','wts','selling') else '삽니다'
        return ', '.join(names)+' '+action
    if len(segments)>8:return None
    names=[]
    for segment in segments:
        match=re.fullmatch(r'\s*([A-Za-z0-9][A-Za-z0-9\s\x27+\-()]{1,66}?)\s+(\d+(?:\.\d+)?\s*[kmb])(?:\s+mesos?)?(?:\s+(ea|each))?[.,!]*\s*',segment,re.I)
        if match:
            name=match.group(1)
            if not re.search('[A-Za-z]',name):return None
            name=re.sub(r'(?i)(?<=\d)\s*slots?\b',' 슬롯',name)
            names.append(f'{_item(name)} '+('개당 ' if match.group(3) else '')+_money(match.group(2)))
        else:
            # Remaining wishlists, clauses, and bid instructions should not
            # be guessed; use the standard translation path instead.
            return None
    if len(names)<2:return None
    action='팝니다' if tag.lower().replace(' ','') in ('s>','wts','selling') else '삽니다'
    return ', '.join(names)+' '+action


_LOCATION_PAIR = re.compile(
    r'(?i)(?<![A-Za-z0-9_])(?:'
    r'ch\s*(\d{1,3})\s*[,/;|\-]?\s*fm\s*(?:room\s*)?(\d{1,3})'
    r'|fm\s*(?:room\s*)?(\d{1,3})\s*[,/;|\-]?\s*ch\s*(\d{1,3})'
    r')\s*[.!~]*$'
)


_LOCATION_PARTIAL = re.compile(
    r'(?i)(?<![A-Za-z0-9_])ch\s*(\d{1,3})\s*[,/;|\-]?\s*fm(?![A-Za-z0-9_])\s*[.!~]*$'
)

def split_market_location(source: str) -> tuple[str, str] | None:
    """Parse explicit CH+FM coordinates without confusing SP/item numbers.

    CH31 FM17 == 31채널 자유시장 17번 방 (different numbers).
    """
    reverse_partial=re.search(r'(?i)[,;\s]+(?:in\s+)?fm\s+ch\s*(\d{1,3})[.!\s]*$',str(source or ''))
    if reverse_partial and int(reverse_partial.group(1))>0:
        return str(source)[:reverse_partial.start()].rstrip(' ,;'), f'{int(reverse_partial.group(1))}채널 자유시장 (방 번호 미기재)'
    match = _LOCATION_PAIR.search(str(source or '').strip())
    if match is None:
        partial = _LOCATION_PARTIAL.search(str(source or '').strip())
        if partial is None or int(partial.group(1)) < 1:
            return None
        base = str(source).strip()[:partial.start()].strip(' ,;@-')
        return base, f'{int(partial.group(1))}채널 자유시장 (방 번호 미기재)'
    if match.group(1) is not None:
        channel, room = int(match.group(1)), int(match.group(2))
    else:
        channel, room = int(match.group(4)), int(match.group(3))
    if channel < 1 or room < 1:
        return None
    base = str(source).strip()[:match.start()].strip(' ,;@-')
    return base, f'{channel}채널 자유시장 {room}번 방'



# Listing fragments without S>/WTS still appear inside a megaphone.
# Parse only an explicit equipment + attack + remaining-slots pattern;
# unrecognized items keep their original name and no price is invented.
_EQUIP_NO_SLOTS = re.compile(
    r"(?ix)^\s*(?:S\s*>\s*|WTS\s+|SELLING\s+)?"
    r"(?P<item>[A-Za-z][A-Za-z'\"\u2019\u201c\u201d\s-]{2,65}?)\s+"
    r"(?P<attack>\d{2,3})\s*(?:공격력|(?:weapon\s*)?(?:atk|att|attack|watk))\s*"
    r"(?P<bonus>[+\uff0b]\s*\d{1,2})\s*"
    r"(?:no\s+slots?\s+left|(?:0|zero)\s+slots?\s+(?:left|remaining))\s*$"
)

def equipment_no_slots_override(source: str) -> str | None:
    """Equipment sale without explicit S>: preserve all observed numbers.

    A bare FM (no room ID) must stay underspecified, not FM 13 just
    because CH 13 was found. Never infer whether +4 is base or bonus ATK.
    """
    raw = _SPACE.sub(' ', str(source or '')).strip()
    location = split_market_location(raw)
    base, location_label = location if location is not None else (raw, '')
    m = _EQUIP_NO_SLOTS.fullmatch(base)
    if m is None:
        return None
    attack = int(m.group('attack'))
    bonus = int(m.group('bonus').replace(' ','').replace('＋','+'))
    if attack < 1 or bonus < 0:
        return None
    item_name = m.group('item')
    # Small quote duplication/shape errors are common in fixed-size Maple OCR.
    # Normalize only this verified equipment name, not arbitrary item names.
    item_name = re.sub(r"(?i)\bserpent\s*['\"’“”]{1,3}\s*s\s+tongue\b",
                       "Serpent's Tongue", item_name)
    item = _item(item_name)
    result = f'{item} · 공격력 {attack}, 추가 표기 +{bonus} · 남은 업그레이드 횟수 0회'
    if location_label:
        result += f' · {location_label}'
    return result


def trade_override(source: str) -> str | None:
    """Generate Korean for clearly recognized market posts, no partial MT fragments."""
    s = _SPACE.sub(' ',source).strip()
    if not s:return None
    # S< may be a genuine nonstandard marker OR OCR reading S> incorrectly.
    # Translate its *certain* item/price fields, but never invent the direction.
    uncertain_sale = re.fullmatch(
        r'S\s*<\s*tons\s+of\s+(?:junk|trash)\s+nx\s+(\d+(?:\.\d+)?\s*[kmb])\s*[.!?]*',
        s, re.I)
    if uncertain_sale:
        return f'S< · 잡캐시템 다량 · 가격 {_money(uncertain_sale.group(1))} (거래 방향 확인 필요)'
    match=_MARKET.match(s)
    if not match:
        # Bare item + explicit best-offer text, typical high-frequency spam.
        return None
    verb, tail=match.groups()
    action='팝니다' if verb.lower().replace(' ','') in ('s>','wts','selling') else '삽니다'
    tail=tail.strip()
    # Missing-item fragment. The price's unit (each/total) isn't stated,
    # so it must never be rendered as an invented per-item amount.
    fragment = re.fullmatch(
        r'for\s+(\d+(?:\.\d+)?\s*[kmb])\s+need\s+(\d+)\s+more\s+'
        r'(?:only\s+)?(?:pm|pm\s+me|pmo)\s*[.!?]*', tail, re.I)
    if action == '삽니다' and fragment:
        return (f'품목 미표기 · {int(fragment.group(2))}개 더 삽니다. '
                f'제시 가격 {_money(fragment.group(1))} (개당 여부 미표기). 귓말만 주세요')
    # The remaining clause has a preposition/quantity without a known
    # item. Let the original safe translation path handle it rather than
    # treating every English word as an equipment title.
    if re.match(r'(?i)^for\s+\d', tail) or re.search(r'(?i)\bneed\s+\d+\s+more\b',tail):
        return None
    # Many sellers repeat their item with a best-offer suffix.
    offer_note = bool(re.search(r'\b(?:best\s+offer|highest\s+(?:offer|wins)|taking\s+offers|offers\s+welcome)\b',tail,re.I))
    tail=re.sub(r'\s*\b(?:best\s+offer|highest\s+(?:offer|wins)|taking\s+offers|offers\s+welcome)\b\s*', ' ', tail,flags=re.I).strip()
    contact=bool(re.search(r'\b(?:pmo|pm\s*me|pm|whisper\s*me)\b',tail,re.I))
    tail=re.sub(r'\s*\b(?:pmo|pm\s*me|pm|whisper\s*me)\b\s*', ' ',tail,flags=re.I).strip()
    tail=re.sub(r'(?i)\b(?:pls|plz|please)\b',' ',tail).strip()
    notes=[]
    only_price=re.search(r'(?i)(\d+(?:\.\d+)?\s*[kmb])\s+only[.!]*$',tail)
    if only_price:
        tail=tail[:only_price.start()]+only_price.group(1)
        notes.append('이 가격에 거래')
    bulk=bool(re.search(r'\bbulk\b',tail,re.I))
    if bulk:
        tail=re.sub(r'(?i)\bbulk\b',' ',tail).strip()
    # eq45k is treated as an annotated offer price, NOT automatically 'per item'.
    eqprice=re.search(r'(?i)\beq\s*'+_PRICE+r'\b',tail)
    if eqprice:
        notes.append(f'가격 {_money(eqprice.group(1))}')
        tail=(tail[:eqprice.start()]+' '+tail[eqprice.end():]).strip()
    bids=re.findall(r'(?i)\b(c\s*/\s*o|a\s*/?\s*w|h\s*/\s*o|res)\s*[:=]?\s*'+_PRICE+r'\b',tail)
    for tag, val in bids:
        clean=re.sub(r'\s+','',tag.lower())
        name={'c/o':'현재 최고 제시가','a/w':'즉시 구매가','aw':'즉시 구매가',
              'h/o':'최고 제시가','res':'최소 판매가'}[clean]
        notes.append(f'{name} {_money(val)}')
    tail=re.sub(r'(?i)\b(?:c\s*/\s*o|a\s*/?\s*w|h\s*/\s*o|res)\s*[:=]?\s*'+_PRICE+r'\b',' ',tail).strip()
    qty=re.search(r'(?i)\b(\d+)\s*(?:available|left|in\s+stock)\b',tail)
    if qty:
        notes.append(f'재고 {int(qty.group(1))}개')
        tail=(tail[:qty.start()]+' '+tail[qty.end():]).strip()
    each=re.search(r'(?i)\b'+_PRICE+r'(?:\s+mesos?)?\s*(?:ea|each)\b',tail)
    if each:
        notes.insert(0,f'개당 {_money(each.group(1))}')
        tail=(tail[:each.start()]+' '+tail[each.end():]).strip()
    elif not bids:
        # Plain trailing price, but do not consume equipment levels like +1.
        at_end=re.search(r'(?i)(?<![\w+])'+_PRICE+r'\s*$',tail)
        if at_end:
            notes.insert(0,f'가격 {_money(at_end.group(1))}')
            tail=tail[:at_end.start()].strip()
    # Remove polite fillers without swallowing the item or its price.
    tail=re.sub(r'(?i)\b(?:pls|plz|please)\b',' ',tail).strip()
    tail=tail.strip(' ,;/~')
    tail=re.sub(r'(?i)\b(lvl|level)\s*(\d+)\b',r'레벨 \2',tail)
    tail=re.sub(r'(?i)\bblunt\s+2h\b','양손둔기',tail)
    if not tail:return None
    # Prevent accidental price guesses and malformed outputs for junk OCR.
    if len(tail)>130 or not re.search(r'[A-Za-z가-힣]',tail):return None
    target=_item(tail)
    if not target:return None
    from .market_item_terms import replace_market_items
    target=replace_market_items(target)
    # Preserve exact upgrade count and 'clean' without letting model invent
    # another item. If title itself is unknown leave it in source wording.
    target=re.sub(r'(?i)\bclean\b', '미강화', target)
    result=f'{target} '+('대량으로 ' if bulk else '')+action
    if notes:result += '. ' + ', '.join(notes)
    if offer_note:result += '. 가격 제안 받습니다'
    if contact:result += '. 귓말 주세요'
    return result


def general_chat_override(source: str) -> str | None:
    """Only entire, unambiguous phrases; unknown conversations use the AI."""
    stripped=source.strip()
    normalized=re.sub(r'[!?.~]+$','',stripped).strip().casefold()
    phrases={
        'u scammed me':'너 나한테 사기 쳤잖아',
        'u funny my guy':'너 웃긴다, 친구야',
        'i feel so weak':'저 너무 약한 것 같아요',
        'im so weak':'저 진짜 약해요',
        "i'm so weak":'저 진짜 약해요',
        'i am so weak':'저 진짜 약해요',
        'we are so weak':'우리 너무 약한데요',
        'are they weak':'걔네 약해요?',
        'they are so weak':'걔네 진짜 약하네요',
        'nerfing bow':'활 너프하는 중이에요',
        'they nerfed bow':'활이 너프됐어요',
        'bow got nerfed':'활이 너프됐어요',
        'i hate this nerf':'이번 너프 진짜 별로네요',
        'they buffed it':'그거 버프됐어요',
        'need more dex':'덱스 더 필요해요',
    }
    exact=phrases.get(normalized)
    if exact:return exact
    amount=re.fullmatch(r'over\s+(\d+(?:\.\d+)?\s*[kmb])\s+is\s*crazy',stripped,re.I)
    if amount:return amount.group(1)+' 넘는 건 너무하네'
    amount=re.fullmatch(r'looking\s+for\s+(\d+(?:\.\d+)?\s*[kmb])\s+mesos?',stripped,re.I)
    if amount:return _money(amount.group(1))+' 구하고 있어요'
    if re.fullmatch(r'ok(?:ay|ie)?e*',normalized):return '알겠어'
    nick=re.fullmatch(r'naw\s+([A-Za-z][A-Za-z0-9_]{1,23})',stripped,re.I)
    if nick:return '아니야, '+nick.group(1)
    # Explicit exchange phrasing only. A standalone 'fame' or player name
    # must not be turned into a trading instruction.
    if re.fullmatch(r'fame\s*(?:for|[-–]\s*)\s*fame(?:\s+and\s+trade)?', normalized):
        return '인기도 맞교환합니다'
    if re.fullmatch(r'(?:i\s+)?(?:think\s+)?they(?:\s+are|\x27re)?\s+nerfing\s+bow\s+and\s+buffing\s+sin',normalized):
        return '활은 너프하고 표도는 버프하는 것 같아요' if normalized.startswith('i ') else '활은 너프하고 표도는 버프하는 중이네요'
    if re.fullmatch(r'i\s+(?:feel|think)\s+like\s+they\s+are\s+weak',normalized):
        return '걔네 좀 약한 것 같은데요'
    # A bracketed tag/name is left intact; do not translate it as a monster.
    tagged=re.fullmatch(r'(\[[^\]\n]{1,50}\])\s+are\s+nerfing\s+bow\s+and\s+buffing\s+sin',stripped,re.I)
    if tagged:
        return f'{tagged.group(1)}은 활을 너프하고 표도를 버프하는 중이에요'
    return None


def normalize_maple_market_name(text: str) -> str:
    """MapleStory's Free Market is always 자유시장, never 무료시장.

    Apply this to translated body text (not nicknames); retain all numbers,
    channel IDs, and other item names. Avoid replacing FM inside words.
    """
    value = str(text)
    for pattern in (
        r'(?i)(?<![\w])free[\s\-]+market(?![\w])',
        r'(?i)(?<![\w])fm(?![\w])',
        r'무료\s*시장',
        r'프리\s*마켓',
        r'자유\s+시장',
    ):
        value = re.sub(pattern, '자유시장', value)
    return value


def polish_meso_units(text: str) -> str:
    """Normalize clearly marked meso amounts without guessing trade prices.

    Maple OCR/MT often emits '130 천 mesos' or '1.8 백만 메소'. These
    expressions have unambiguous numeric values; preserve the exact amount.
    A bare number lacking a meso unit is intentionally left unchanged.
    """
    def amount_ko(amount: Decimal) -> str:
        if amount != amount.to_integral_value():
            return str(amount)
        amount = int(amount)
        remaining = amount
        pieces = []
        for scale, label in ((100000000, '억'), (10000, '만'), (1000, '천')):
            count, remaining = divmod(remaining, scale)
            if count:
                pieces.append(f'{count:,}{label}')
        if remaining:
            pieces.append(f'{remaining:,}')
        return ' '.join(pieces or ['0'])

    raw = str(text)
    # A formatted amount like "1,000만 메소" must be consumed WHOLE, not
    # misread as "000만 메소" after its comma (v0.4.4 regression).
    tagged = re.compile(r'(?i)(?<![\w.,])((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(k|m|b|천|만|백만|억)\s*(mesos?|메소)\b')
    multiplier = {'k':1000, 'm':1000000, 'b':1000000000,
                  '천':1000, '만':10000, '백만':1000000, '억':100000000}
    def replace(match):
        units=match.group(2).casefold()
        value=Decimal(match.group(1).replace(',', '')) * multiplier[units]
        return amount_ko(value)+' 메소'
    output = tagged.sub(replace, raw)
    # An isolated English currency name should never survive into the final
    # Korean chat row; other untranslated English names are left intact.
    output = re.sub(r'(?i)\bmesos?\b', '메소', output)
    return normalize_maple_market_name(output)
