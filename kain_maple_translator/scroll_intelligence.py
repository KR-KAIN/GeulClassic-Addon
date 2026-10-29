"""Conservative Classic World scroll interpreter.

Only unambiguous gear + attribute + success rate expressions are classified as
scrolls. Corrupted OCR and named equipment are NEVER silently turned into a
scroll. No network access or machine translation needed for recognized labels.
"""
from __future__ import annotations

import re
from .expanded_terms import scroll_label
from .glossary import money_ko

_SPACE = re.compile(r'\s+')
_PERCENT = re.compile(r'(?<![\w.])(?P<rate>100|70|60|30|10|1)\s*%')
_TIERS = {'lesser':'100', 'intermediate':'60', 'greater':'10'}
_GEARS = {
    'pet equip':'펫 장비', 'pet equipment':'펫 장비', 'pet equips':'펫 장비',
    'pet gear':'펫 장비', 'pet item':'펫 장비', '애완 동물':'펫 장비',
    '애완동물':'펫 장비', '펫 장비':'펫 장비',
    'shoe':'신발', 'shoes':'신발', 'glove':'장갑', 'gloves':'장갑',
    'hat':'모자', 'helmet':'투구', 'earring':'귀고리', 'earrings':'귀고리',
    'helm':'투구', 'helms':'투구', 'helmets':'투구', 'hats':'모자',
    'cape':'망토','shield':'방패','top':'상의','topwear':'상의',
    'bottom':'하의','bottomwear':'하의','pants':'하의',
    'overall':'전신갑옷', 'overall armor':'전신갑옷',
    'claw':'아대','dagger':'단검','spear':'창','bow':'활',
    'crossbow':'석궁','xbow':'석궁','staff':'스태프','wand':'완드',
    'polearm':'폴암','pole arm':'폴암','1h sword':'한손검',
    '2h sword':'두손검', '1h axe':'한손도끼', '2h axe':'두손도끼',
}
_STATS = {
    'speed':'이동속도','spd':'이동속도','이동 속도':'이동속도','이동속도':'이동속도',
    'jump':'점프력','jumping':'점프력','att':'공격력','atk':'공격력',
    'attack':'공격력','atack':'공격력','weapon attack':'공격력',
    'm.att':'마력','matk':'마력','magic att':'마력','magic attack':'마력',
    'def':'방어력','defense':'방어력','str':'힘', 'dex':'민첩',
    'int':'지력','luk':'행운','hp':'체력','mp':'마나',
    'strength':'힘','dexterity':'민첩','intelligence':'지력','luck':'행운',
    'max hp':'체력','max mp':'마나',
    'crit rate':'치명타 확률','crit. rate':'치명타 확률',
    'crit damage':'치명타 피해','crit. damage':'치명타 피해',
    'evasion':'회피율','accuracy':'명중률',
    '속도':'이동속도', '공격력':'공격력',
}
_GEAR_RE = '|'.join(sorted((re.escape(x) for x in _GEARS),key=len, reverse=True))
_STAT_RE = '|'.join(sorted((re.escape(x) for x in _STATS),key=len, reverse=True))
_PRICE = r'(\d+(?:\.\d+)?\s*[kmb])'
_DEAL_RE = re.compile(r'^\s*(s\s*>|b\s*>|wts\b|wtb\b|selling\b|buying\b|sell\b|buy\b)\s*(.*?)\s*$',re.I)
_CONTACT_RE = re.compile(r'\s+(?:pmo|pm\s*me|whisper\s*me|whisper)\s*$',re.I)


def _clean(value: str) -> str:
    value = str(value).replace('％','%').replace('＞','>')
    value = value.strip()
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1].strip()
    value = re.sub(r'\s*%\s*','%',value)
    value = re.sub(r'\s*[:;,]\s*',' ',value)
    return _SPACE.sub(' ',value).strip()


def scroll_name(text: str) -> str | None:
    """Full-match only: unknown words/modifiers may not be discarded."""
    s=_clean(text).casefold()
    if not s:
        return None
    # Keep the established Korean term catalog before attempting variants.
    known=scroll_label(s)
    if known:
        return re.sub(r'^(.*?)(?:\s+)주문서\s+(\d{1,3}%)$', r'\1 \2 주문서', known)
    if s in ('gfa','gma'):
        return ('장공' if s == 'gfa' else '장마')+' 주문서'
    # In Classic the common shorthand 60% GFA and GFA 60% are equivalent.
    m=re.fullmatch(r'(100|70|60|30|10|1)%\s*(gfa|gma)',s)
    if m:
        return ('장공' if m.group(2)=='gfa' else '장마')+f' {m.group(1)}% 주문서'
    # Tier names are official on the 2026 Classic client for the 100/60/10%
    # scroll types; 'Chaos' is deliberately NOT mapped to 10% because of
    # additional item-destruction mechanics.
    tier=re.search(r'(?:\bscroll\b\s*)?(?:lesser|intermediate|greater)\s*$',s)
    tier_rate=None
    if tier:
        word=s[tier.start():].split()[-1]
        tier_rate=_TIERS.get(word)
        s=s[:tier.start()].strip()
    rate_match=_PERCENT.search(s)
    rate=rate_match.group('rate') if rate_match else tier_rate
    if rate_match:
        s=(s[:rate_match.start()]+' '+s[rate_match.end():]).strip()
    if rate and tier_rate and rate!=tier_rate:
        return None
    # Alternative official / historic catalog word orders.
    s=re.sub(r'^scroll\s+for\s+', '', s)
    s=re.sub(r'^scroll\s+of\s+', '', s)
    s=re.sub(r'\bfor\s+(?=(?:'+_STAT_RE+r')\b)', '', s)
    s=re.sub(r'\bscroll\b', '', s)
    s=re.sub(r'\s*\.(?=\s|$)', ' ', s)
    s=_SPACE.sub(' ',s).strip()
    m=re.fullmatch(r'('+_GEAR_RE+r')\s+('+_STAT_RE+r')',s,re.I)
    if not m:
        # Stat-first shorthand is accepted ONLY if an explicit scroll or rate
        # identified the expression; avoid changing ordinary adjective text.
        if not rate and 'scroll' not in text.casefold():
            return None
        m2=re.fullmatch(r'('+_STAT_RE+r')\s+('+_GEAR_RE+r')',s,re.I)
        if not m2:
            return None
        stat,gear=m2.group(1),m2.group(2)
    else:
        gear,stat=m.group(1),m.group(2)
    gear_name=_GEARS.get(gear.casefold())
    stat_name=_STATS.get(stat.casefold())
    if not gear_name or not stat_name:
        return None
    # The gear+attribute pair is a scroll when an explicit rate/scroll/tier
    # is present; an item can otherwise merely have +Speed/+Attack stats.
    if not (rate or tier_rate or re.search(r'\bscroll\b|주문서',text,re.I)):
        return None
    return f'{gear_name} {stat_name} {rate}% 주문서' if rate else f'{gear_name} {stat_name} 주문서'


def scroll_trade(text: str) -> str | None:
    """Translate a *complete* unambiguous sale/buy scroll line."""
    m=_DEAL_RE.fullmatch(str(text))
    if not m:
        return None
    verb,body=m.groups()
    action='팝니다' if verb.lower().replace(' ','') in ('s>','wts','selling','sell') else '삽니다'
    body=re.sub(r'[!~.]+\s*$','',body).strip()             # 'S>60% bow atk 95k!'
    body=re.sub(r'\s+[A-Za-z]$','',body)                     # one-letter crumb: '... magic att 60% u'
    contact=bool(_CONTACT_RE.search(body))
    body=_CONTACT_RE.sub('',body).strip()
    price=''
    price_match=re.search(r'\s+'+_PRICE+r'(?:\s+mesos?)?\s*$',body,re.I)
    if price_match:
        # same unit style as other trade lines: '95k' -> '9만 5천 메소'
        from .natural_trade import _money
        raw=price_match.group(1).replace(' ','')
        value=money_ko(raw) and _money(raw)
        if value:
            price=value
            body=body[:price_match.start()].strip()
    name=scroll_name(body)
    if not name:
        return None
    phrase=f'{name} {price}에 {action}' if price else f'{name} {action}'
    if contact:
        phrase += '. 귓말 주세요'
    return phrase


def polish_scroll_result(text: str) -> str:
    """Repair narrow known mistranslations, without guessing unknown items."""
    # This particular phrase is reliably a PET EQUIPMENT scroll, not a pet
    # itself. Only rewrite when the full attribute+rate pattern is present.
    result=re.sub(r'애완\s*동물\s*(?:장비\s*)?(?:이동\s*)?속도\s*(100|70|60|30|10|1)\s*%\s*(?:주문서)?',
                  lambda m: f'펫 장비 이동속도 {m.group(1)}% 주문서',str(text))
    return result
