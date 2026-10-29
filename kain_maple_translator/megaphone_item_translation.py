"""Conservative item-first localization for GMS Classic megaphone trade text.

The ordinary sentence model should never decide item names or item stat
numbers.  Accept only explicit trading markers, bracketed item links and
unambiguous equipment shorthand.  Unknown names and OCR fragments stay visible
rather than being guessed as official Korean titles.
"""
from __future__ import annotations

import re

_TRADE_MARKERS = re.compile(r'(?<![A-Za-z0-9_])([SB])\s*[>＞〉](?=\s|\[|[A-Za-z가-힣]|$)', re.I)
_OFFER_REQUEST = re.compile(
    r'^\s*(?:pm\s*(?:me\s*)?(?:offers?|offer|price)?|pmo|whisper\s*(?:me\s*)?(?:offers?|offer)?|offer\s*(?:pm|pmo))\s*[.!?]*\s*$',
    re.I,
)
_BRACKETED_PRICED_SALE = re.compile(
    r'^\s*(\[[^\]\r\n]{2,100}\])\s+for\s+(\d+(?:\.\d+)?\s*[kmb])'
    r'(?:[.!]?\s*(?:also\s+have|also\s+got)\s+(.+))?\s*[.!]?\s*$', re.I,
)
_KOREAN_BUY_SELL = re.compile(r'^\s*([A-Za-z][A-Za-z0-9 \'-]{1,85})\s+(팝니다|삽니다)\s*[.!]?\s*$',re.I)
_BRACKETED_ITEM_OFFER = re.compile(
    r'^\s*(\[[^\[\]\r\n]{2,100}\])\s+(.*?)\s*$', re.S
)
_EQUIPMENT_STATS = re.compile(
    r'(?<!\w)(?:lv|lvl|level)\.?\s*(\d{1,3})\s+'
    r'(archer|bowman|warrior|thief|mage|magician|pirate)\s+'
    r'(gloves?|shoes?|boots?|hats?|helmets?|caps?|capes?|tops?|pants?|bottoms?|overalls?|weapons?|gears?|equips?)'
    r'\s+([1-9]\d?)\s*(dex|str|int|luk)\s+([1-9]\d?)\s*(crit|critical)(?!\w)',
    re.I,
)
_ROLE = {'archer':'궁수','bowman':'궁수','warrior':'전사','thief':'도적',
         'mage':'마법사','magician':'마법사','pirate':'해적'}
_GEAR = {'glove':'장갑','shoe':'신발','boot':'신발','hat':'모자','helmet':'투구',
         'cap':'모자','cape':'망토','top':'상의','pant':'하의','bottom':'하의',
         'overall':'전신갑옷','weapon':'무기','gear':'장비','equip':'장비'}
_STAT = {'dex':'민첩','str':'힘','int':'지력','luk':'행운'}


def localize_equipment_stats(message: str) -> str:
    """Only an exact level / class / equipment / stat sequence is rewritten."""
    def change(m: re.Match) -> str:
        role=_ROLE[m.group(2).lower()]
        gear=m.group(3).lower()
        singular=gear[:-1] if gear.endswith('s') else gear
        # "shoes"->"shoe", "pants"->"pant". No guesses for other nouns.
        gear_ko=_GEAR.get(singular)
        if gear_ko is None:
            return m.group(0)
        return (f'{m.group(1)}레벨 {role} {gear_ko} '
                f'({_STAT[m.group(5).lower()]} +{m.group(4)}, 크리티컬 +{m.group(6)})')
    return _EQUIPMENT_STATS.sub(change, message)


def localized_item_text(text: str) -> str:
    """Manual catalog > synced matching item ID > independent known names.

    Operates only on item/title snippets. Never run it on an entire chat line
    where a player nickname could be mistaken for an item.
    """
    from .item_catalog import current_catalog
    from .classic_item_index import current_index
    from .market_item_terms import replace_market_items
    from .item_link_protection import protect_hangul_links
    from .scroll_intelligence import scroll_name
    # Resolve COMPLETE labels before substring dictionaries. Otherwise
    # "Gloves Attack Scroll: Intermediate" becomes a half-translated Korean
    # link which later protection correctly refuses to modify.
    parts=re.split(r'(\[[^\[\]\r\n]+\])',protect_hangul_links(text))
    for i,part in enumerate(parts):
        if i%2:
            if re.search('[가-힣]',part):continue
            exact=current_catalog().lookup(part[1:-1])
            if exact:
                parts[i]='['+exact+']';continue
            scroll=scroll_name(part)
            if scroll:
                parts[i]='['+scroll+']';continue
        result=current_catalog().replace(part)
        result=current_index().replace_verified(result)
        parts[i]=replace_market_items(result)
        # TradeMemory/PMO paths also need complete English scroll links. This
        # helper parses only known labels and never enters item catalogs again.
        from .trade_stats import known_scroll_link
        parts[i]=re.sub(r'\[[^\[\]\r\n]+\]',lambda m:known_scroll_link(m.group()),parts[i])
    return ''.join(parts)


def translate_announcement_trade(message: str) -> str | None:
    """Return deterministic Korean for supported trade forms, else None.

    User-imported/ID-matched names are used before curated aliases. Incomplete
    OCR text stays intact. Everything else may use the existing translation.
    """
    source=str(message or '').strip()
    if not source or len(source)>260 or re.search(r'https?://|www\.',source,re.I):
        return None

    # [화이트 초코 버니] for 450k. Also have Blank Eye Patc E
    # Keep the price exact and the OCR fragment visible rather than
    # hallucinating a complete item that was never read from the screen.
    priced = _BRACKETED_PRICED_SALE.fullmatch(source)
    if priced:
        from .natural_trade import _money
        label=localized_item_text(priced.group(1))
        result=f'{label} {_money(priced.group(2))}에 팝니다'
        extra=(priced.group(3) or '').strip(' .!')
        if extra:
            extra_name=localized_item_text(extra)
            result+=f'. {extra_name}도 있습니다'
        return result

    # MEBA 삽니다: Korean verbs must not prevent item names being localized.
    plain=_KOREAN_BUY_SELL.fullmatch(source)
    if plain:
        label=localized_item_text(plain.group(1))
        if label != plain.group(1):
            return f'{label} {plain.group(2)}'

    # [Gentleman's Mustache] PM offer / [신사의 콧수염] PMO
    match = _BRACKETED_ITEM_OFFER.fullmatch(source)
    if match and _OFFER_REQUEST.fullmatch(match.group(2)):
        name=match.group(1)
        # A bracketed label is the player's explicit item name. If there is
        # no verified Korean counterpart, leave the English item intact.
        localized=localized_item_text(name)
        return f'{localized} 가격 제안은 귓말로 주세요'

    # Two or more trade tags on one megaphone: s> item A s> item B.
    # Also support OCR prefix fragments before the FIRST marker; retain the
    # prefix as-is rather than hallucinating that it is a sellable item.
    markers=list(_TRADE_MARKERS.finditer(source))
    if not markers:
        return None
    if len(markers)==1 and markers[0].start()==0 and not _EQUIPMENT_STATS.search(source):
        return None  # Keep all established single-S> routes unless they need stat parsing.

    from .natural_trade import trade_override
    parts=[]
    prefix=source[:markers[0].start()].strip(' ,;|')
    if prefix:
        parts.append(prefix)
    converted=0
    for i,marker in enumerate(markers):
        end=markers[i+1].start() if i+1<len(markers) else len(source)
        payload=source[marker.end():end].strip(' ,;|')
        if not payload:
            continue
        # No punctuation is invented. The stats are only translated when all
        # slots match an explicit 35 archer gloves 3 dex 2 crit type shape.
        payload=localize_equipment_stats(payload)
        if payload.strip() == '페어리 윙':
            payload='요정의 날개'  # Already-MT'd form of one exact item, not a fuzzy match.
        payload=localized_item_text(payload)
        action=marker.group(1).lower()
        translated=trade_override(action.upper()+'> '+payload)
        if translated is None:
            translated=payload+(' 팝니다' if action=='s' else ' 삽니다')
        parts.append(translated)
        converted+=1
    return ' · '.join(parts) if converted else None
