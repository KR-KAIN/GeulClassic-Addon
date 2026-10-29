"""Korean trade and party posts -> MapleStory chat English (R19).

    노가다 목장갑 8공 3작 900만에 팝니다      -> S> Work Gloves 8 att 3 slots 9m
    장갑 공격력 60% 주문서 12만 메소에 팝니다  -> S> Glove ATT 60% 120k
    맑은 물 개당 750에 삽니다                 -> B> Pure Water 750 ea
    커닝 파퀘 30레벨 이상 2명 모집해요         -> R> KPQ need 2 lv30+

Only a line whose intent is clear (sell / buy / trade / recruit / join) is
rewritten here, piece by piece: item names from the game's own Korean name
tables, scrolls, upgrade options, prices, channel and contact words. Any other
line still goes to the sentence model. A piece that no table knows is passed
to ``fallback`` (the sentence model) on its own, so the post keeps its shape.
"""
from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from typing import Callable

# ------------------------------------------------------------------ words
_SELL = r'(?:팝니다|팔아요|팔게요|팔아용|팔아|팜|팔겠습니다|판매(?:합니다|해요|중|함|요)?|처분(?:합니다|해요)?|넘깁니다|넘겨요)'
_BUY = r'(?:삽니다|사요|살게요|사용|삼|사겠습니다|구매(?:합니다|해요|중|함|요)?|매입(?:합니다|해요)?|구합니다|구해요|구함|찾습니다|찾아요|사고\s*싶어요)'
_TRADE = r'(?:교환(?:해요|합니다|원해요|하실\s*분|함|요)?|트레이드)'

_PQ = [(r'커닝\s*(?:시티\s*)?파(?:티\s*)?퀘(?:스트)?|커파퀘|커파|kpq', 'KPQ'),
       (r'루디(?:브리엄)?\s*파(?:티\s*)?퀘(?:스트)?|루파퀘|루파|lpq', 'LPQ'),
       (r'오르비스\s*파(?:티\s*)?퀘(?:스트)?|오파퀘|opq', 'OPQ'),
       (r'길드\s*(?:파티\s*)?퀘(?:스트)?|길퀘|gpq', 'GPQ'),
       (r'파티\s*퀘스트|파퀘|pq', 'PQ')]

_GEARS = [(r'펫\s*장비', 'Pet Equip'), (r'전신\s*갑옷|전신', 'Overall'), (r'한손\s*검', '1H Sword'),
          (r'두손\s*검', '2H Sword'), (r'한손\s*도끼', '1H Axe'), (r'두손\s*도끼', '2H Axe'),
          (r'한손\s*둔기', '1H BW'), (r'두손\s*둔기', '2H BW'), (r'장갑', 'Glove'), (r'투구|모자', 'Helm'),
          (r'귀고리|귀걸이|귀', 'Earring'), (r'신발', 'Shoe'), (r'망토', 'Cape'), (r'방패', 'Shield'),
          (r'상의', 'Top'), (r'하의', 'Bottom'), (r'아대', 'Claw'), (r'단검', 'Dagger'), (r'폴암', 'Polearm'),
          (r'석궁', 'Crossbow'), (r'활', 'Bow'), (r'스태프|스탭', 'Staff'), (r'완드', 'Wand'), (r'창', 'Spear')]
_STATS = [(r'공격력|공', 'ATT'), (r'마력|마', 'MATT'), (r'힘', 'STR'), (r'민첩|덱스|덱', 'DEX'),
          (r'지력|인트', 'INT'), (r'행운|럭', 'LUK'), (r'방어력|방어', 'DEF'), (r'이동\s*속도|이속', 'Speed'),
          (r'점프력|점프', 'Jump'), (r'체력|HP', 'HP'), (r'마나|MP', 'MP'), (r'명중률|명중', 'ACC'),
          (r'회피율|회피', 'AVOID')]
_GEAR_RX = '|'.join(f'(?:{p})' for p, _ in _GEARS)
_STAT_RX = '|'.join(f'(?:{p})' for p, _ in _STATS)

# Names the game tables lack, and the community's short names
_NAMES = {
    '노목': 'Work Gloves', '노가다목장갑': 'Work Gloves', '노가다 장갑': 'Work Gloves', '목장갑': 'Work Gloves',
    '월비': 'Wolbis', '월비표창': 'Wolbis', '토비': 'Tobis', '토비표창': 'Tobis', '일비': 'Ilbis',
    '일비표창': 'Ilbis', '표창': 'stars', '장어구이': 'Unagi', '장어': 'Unagi', '엘릭서': 'Elixir',
    '엘릭': 'Elixir', '파엘': 'Power Elixir', '맑물': 'Pure Water', '하포': 'White Potion',
    '파포': 'Blue Potion', '빨포': 'Red Potion', '주포': 'Orange Potion', '마엘': 'Mana Elixir',
    '천사의 헤일로': 'Angel Halo', '천사 헤일로': 'Angel Halo', '헤일로': 'Angel Halo',
    '철 원석': 'Iron Ore', '철광석': 'Iron Ore', '원석': 'ore', '광석': 'ore',
    '사우나 가운': 'Sauna Robe', '가운': 'Sauna Robe', '태부': 'Kfan', '태극부채': 'Kfan',
    '장공': 'GFA', '장마': 'GMA', '캐시템': 'NX', '캐시 아이템': 'NX items', '잡캐시템': 'junk NX',
    '인기도': 'fame', '슬롯': 'slots', '주문서': 'scrolls', '혼줌': 'chaos scroll',
    '흑수정': 'Black Crystal', '흑수정 원석': 'Black Crystal Ore', '미스릴 원석': 'Mithril Ore',
    '오팔 원석': 'Opal Ore', '레드 크로스링': 'Red Cross Earrings',
}
_JOBS = {'전사': 'warrior', '법사': 'mage', '마법사': 'mage', '궁수': 'archer', '도적': 'thief',
         '해적': 'pirate', '클레릭': 'cleric', '프리스트': 'priest', '비숍': 'bishop', '헌터': 'hunter',
         '어쌔신': 'sin', '표도': 'sin', '바이퍼': 'bucc', '힐러': 'healer'}


@lru_cache(maxsize=1)
def _game_names() -> dict:
    try:
        from .item_info import _korean_names
        return _korean_names()
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _nospace_names() -> dict:
    """'맑은물' / '노가다목장갑': the same tables keyed without spaces."""
    out = {}
    try:
        from .classic_item_index import current_index
        for en, ko in current_index().by_en.values():
            if ko and re.search('[가-힣]', ko):
                out.setdefault(re.sub(r'\s+', '', ko), en)
    except Exception:
        pass
    try:
        from .market_item_terms import MARKET_NAMES
        for en, ko in MARKET_NAMES.items():
            out[re.sub(r'\s+', '', ko)] = en
    except Exception:
        pass
    return out


def _english_name(ko: str) -> str:
    ko = re.sub(r'\s+', ' ', ko).strip(' ,.')
    if not ko or not re.search('[가-힣]', ko):
        return ''
    for key in (ko, ko.replace(' ', '')):
        if key in _NAMES:
            return _NAMES[key]
    try:
        from .item_info import _key
        en = _game_names().get(_key(ko), '') or _nospace_names().get(ko.replace(' ', ''), '')
    except Exception:
        en = ''
    if en and en == en.lower():
        en = ' '.join(w[:1].upper() + w[1:] for w in en.split())   # 'korean fan' -> 'Korean Fan'
    return en


def _items(phrase: str, fallback: Callable[[str], str] | None) -> str:
    """Korean item words -> English names: the whole phrase, else the
    longest known runs of words; unknown runs go to the fallback."""
    words = phrase.split()
    out, i = [], 0
    while i < len(words):
        for j in range(len(words), i, -1):
            en = _english_name(' '.join(words[i:j]))
            if en:
                out.append(en)
                i = j
                break
        else:
            # one unknown word: keep collecting until a known run starts
            k = i + 1
            while k < len(words) and not any(_english_name(' '.join(words[k:m])) for m in range(len(words), k, -1)):
                k += 1
            chunk = ' '.join(words[i:k])
            if re.search('[가-힣]', chunk) and fallback:
                try:
                    chunk = fallback(chunk).strip(' .')
                except Exception:
                    pass                    # stays Korean: the caller then declines the line
            out.append(chunk)
            i = k
    return ' '.join(x for x in out if x)


# ------------------------------------------------------------------ money
def _plain(n: Decimal) -> str:
    text = format(n, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _won(value: Decimal) -> str:
    """Mesos -> 120k / 9m / 1.5m / 750."""
    if value >= 1_000_000:
        return _plain(value / Decimal(1_000_000)) + 'm'
    if value >= 1000:
        return _plain(value / Decimal(1000)) + 'k'
    return _plain(value)


# '1억 2천만', '6만5천', '1백만', '900만', '2천', '1천5백', '1.5m', '750'
_UNITS = {'억': 100_000_000, '천만': 10_000_000, '백만': 1_000_000, '만': 10_000, '천': 1000, '백': 100}
_KR_NUM = r'(?:\d+(?:\.\d+)?\s*(?:억|천만|백만|만|천|백)\s*)+(?:\d+(?!\s*[%개명렙채작공]))?'
_PRICE_RX = re.compile(rf'(?<![\d%+.])(?:{_KR_NUM}|\d+(?:\.\d+)?\s*[kKmM](?![a-zA-Z가-힣])'
                       r'|\d{2,}(?=\s*(?:메소|메|원|에|씩|$|[,/·]|\s)))\s*(?:메소|메|원)?\s*(?:에|씩)?')


def _parse_money(text: str) -> Decimal | None:
    t = re.sub(r'\s+|메소|메|원|에$|씩$', '', text)
    m = re.fullmatch(r'(\d+(?:\.\d+)?)([kKmM])', t)
    if m:
        return Decimal(m.group(1)) * (1000 if m.group(2) in 'kK' else 1_000_000)
    total, rest = Decimal(0), t
    for num, unit in re.findall(r'(\d+(?:\.\d+)?)(억|천만|백만|만|천|백)', t):
        total += Decimal(num) * _UNITS[unit]
    rest = re.sub(r'\d+(?:\.\d+)?(?:억|천만|백만|만|천|백)', '', t)
    if rest and not re.fullmatch(r'\d+', rest):
        return None
    if rest:
        total += Decimal(rest)
    return total if total > 0 else None


# ------------------------------------------------------------------ pieces
def _scrolls(s: str) -> tuple[str, list[str]]:
    found = []

    def gear_of(word):
        return next(en for p, en in _GEARS if re.fullmatch(p, word))

    def stat_of(word):
        return next(en for p, en in _STATS if re.fullmatch(p, word))

    def repl_a(m):
        found.append(f'{gear_of(m.group(1))} {stat_of(m.group(2))} {m.group(3)}%')
        return f' ⟦S{len(found) - 1}⟧ '

    def repl_b(m):
        found.append(f'{gear_of(m.group(2))} {stat_of(m.group(3))} {m.group(1)}%')
        return f' ⟦S{len(found) - 1}⟧ '
    s = re.sub(rf'({_GEAR_RX})\s*({_STAT_RX})\s*(\d{{1,3}})\s*%\s*(?:주문서|작)?', repl_a, s)
    # '귀 인트 60 5만': the rate without '%' (only the game's own rates)
    s = re.sub(rf'({_GEAR_RX})\s*({_STAT_RX})\s*(10|30|60|70|100)(?![\d.%만천억백])\s*(?:주문서|작)?', repl_a, s)
    s = re.sub(rf'(\d{{1,3}})\s*%\s*({_GEAR_RX})\s*({_STAT_RX})\s*(?:주문서|작)?', repl_b, s)
    s = re.sub(r'(장공|장마)\s*(\d{1,3})\s*%', lambda m: (found.append(f'{_NAMES[m.group(1)]} {m.group(2)}%'), f' ⟦S{len(found) - 1}⟧ ')[1], s)
    s = re.sub(r'(\d{1,3})\s*%\s*(장공|장마)', lambda m: (found.append(f'{_NAMES[m.group(2)]} {m.group(1)}%'), f' ⟦S{len(found) - 1}⟧ ')[1], s)
    s = re.sub(r'(\d{1,3})\s*%\s*주문서', lambda m: (found.append(f'{m.group(1)}% scroll'), f' ⟦S{len(found) - 1}⟧ ')[1], s)
    return s, found


_OPTION_RULES = [
    (r'(?<![\d.])(\d+)\s*공(?!격)', r'\1 att'), (r'(?<![\d.])(\d+)\s*마(?![력나법])', r'\1 matt'),
    (r'(?<![\d.])(\d+)\s*(?:작|업)(?!그|횟)', r'\1 slots'),
    (r'업(?:그레이드)?\s*(?:가능\s*)?(?:횟수\s*)?(\d+)\s*회?', r'\1 slots'),
    (r'(\d+)\s*슬롯', r'\1 slots'),
    (r'\+\s*(\d+)\s*(?:힘)', r'+\1 STR'), (r'\+\s*(\d+)\s*(?:덱|민첩)', r'+\1 DEX'),
    (r'\+\s*(\d+)\s*(?:인트|지력)', r'+\1 INT'), (r'\+\s*(\d+)\s*(?:럭|행운)', r'+\1 LUK'),
    (r'(?<![\d.])(\d+)\s*(?:힘)(?!\s*\d)', r'\1 STR'), (r'(?<![\d.])(\d+)\s*(?:덱|민첩)', r'\1 DEX'),
    (r'(?<![\d.])(\d+)\s*(?:인트|지력)', r'\1 INT'), (r'(?<![\d.])(\d+)\s*(?:럭|행운)', r'\1 LUK'),
    (r'노작|미강화|깡통|노강', 'clean'), (r'풀작', 'fully scrolled'),
]


def _options(s: str) -> tuple[str, list[str]]:
    found = []
    for pattern, english in _OPTION_RULES:
        def repl(m, english=english):
            found.append(m.expand(english))
            return f' ⟦O{len(found) - 1}⟧ '
        s = re.sub(pattern, repl, s)
    return s, found


def _extras(s: str) -> tuple[str, list[str], bool, str]:
    """channel / FM room / contact / offers; returns (rest, extras, each, qty)."""
    extras, each, qty = [], False, ''
    m = re.search(r'(\d+)\s*(?:채널|채|ch)\b|(?:채널|ch)\s*(\d+)', s, re.I)
    ch = (m.group(1) or m.group(2)) if m else ''
    s = s[:m.start()] + ' ' + s[m.end():] if m else s
    m = re.search(r'(?:자유\s*시장|자시|프리\s*마켓|fm)\s*(\d+)?\s*(?:번\s*(?:방)?)?', s, re.I)
    fm = None
    if m:
        fm = m.group(1) or ''
        s = s[:m.start()] + ' ' + s[m.end():]
    if ch or fm is not None:
        extras.append(' '.join(x for x in (f'ch{ch}' if ch else '', f'FM{fm}' if fm else ('FM' if fm == '' else '')) if x))
    for pattern, english in [(r'가격\s*(?:제안|제시)\s*(?:받(?:습니다|아요|음)|주세요|환영|해\s*주세요)?', 'taking offers'),
                             (r'(?:흥정|네고)\s*(?:가능|ㄱㄴ|됩니다|해요)?', 'neg'),
                             (r'급처(?:합니다|해요)?', 'quick sale'),
                             (r'(?:귓(?:말)?|쪽지|pm)\s*(?:주세요|줘요|ㄱ|부탁(?:해요|드려요)?|요|해\s*주세요|주셈)?', 'pm me'),
                             (r'(?:싸게|저렴하게)', 'cheap')]:
        if re.search(pattern, s, re.I):
            extras.append(english)
            s = re.sub(pattern, ' ', s, flags=re.I)
    if re.search(r'개당|하나에|하나당|개에|각각', s):
        each = True
        s = re.sub(r'개당|하나에|하나당|개에|각각', ' ', s)
    m = re.search(r'(?<![\d.])(\d+)\s*개(?!당)', s)
    if m:
        qty = f'x{m.group(1)}'
        s = s[:m.start()] + ' ' + s[m.end():]
    return s, extras, each, qty


_PARTICLES = ('으로', '이랑', '하고', '을', '를', '은', '는', '이', '가', '도', '만', '로', '랑', '에')
_FILLERS = {'좀', '꼭', '최저가', '급하게', '빨리', '전부', '모두', '싹', '다', '그리고', '및', '요',
            '같이', '함께', '세트로', '일괄', '분'}


def _unparticle(word: str) -> str:
    """'헤일로' and '인기도' are names; '노목을' / '엘릭서랑' end in a particle."""
    if word in _FILLERS:
        return ''
    if not re.search('[가-힣]', word) or _english_name(word):
        return word
    for p in _PARTICLES:
        if word.endswith(p) and len(word) > len(p) and _english_name(word[:-len(p)]):
            return word[:-len(p)]
    return word


def _segment(seg: str, fallback) -> str | None:
    """One item (or list) part of a post, without the verb."""
    seg = re.sub(r'\s+', ' ', seg).strip(' ,./·:')
    if not seg:
        return ''
    # place and contact first: 'FM 12' / '3채널' are not prices
    rest, extras, each, qty = _extras(seg)
    rest, scrolls = _scrolls(rest)
    rest, options = _options(rest)
    price = ''
    pm = list(_PRICE_RX.finditer(rest))
    if pm:
        m = pm[-1]
        value = _parse_money(m.group(0))
        if value is not None and value > 0:
            price = _won(value)
            rest = rest[:m.start()] + ' ' + rest[m.end():]
    rest = re.sub(r'(?<![가-힣])(?:메소|메)(?![가-힣])|(?<=\s)에(?=\s|$)', ' ', rest)
    # the words in their own order: names, scrolls and options where they stood
    words, run = [], []

    def flush():
        if run:
            text = ' '.join(w for w in (_unparticle(x) for x in run) if w).strip(' ,./·')
            if text:
                words.append(_items(text, fallback))
            run.clear()
    for token in re.findall(r'⟦[SO]\d+⟧|[^\s⟦⟧]+', rest):
        marker = re.fullmatch(r'⟦([SO])(\d+)⟧', token)
        if marker:
            flush()
            words.append((scrolls if marker.group(1) == 'S' else options)[int(marker.group(2))])
        else:
            run.append(token)
    flush()
    parts = [p for p in [*words, qty] if p]
    if price:
        parts.append(price + (' ea' if each else ''))
    elif each:
        parts.append('ea')
    parts += extras
    return ' '.join(parts).strip()


def _party(s: str) -> str | None:
    pq = ''
    for pattern, name in _PQ:
        if re.search(pattern, s, re.I):
            pq = name
            break
    recruit = re.search(r'(?:(\d)\s*명\s*(?:더\s*)?)?(?:모집|구합니다|구해요|구함|구인)', s)
    join = re.search(r'참가|참여|껴\s*(?:주세요|줘요|도)|끼워\s*(?:주세요|줘요)|들어가고\s*싶|가고\s*싶어요|갈래요', s)
    party_word = re.search(r'파티원?|팟', s)
    if not pq and not party_word:
        return None
    if not (recruit or join):
        return None
    mods = []
    if re.search(r'연속\s*진행|러쉬|러시|rush', s, re.I):
        mods.append('rush')
    if re.search(r'보너스', s):
        mods.append('bonus')
    lv = re.search(r'(\d{1,3})\s*(?:레벨|렙|lv)\s*(이상|\+)?|(?:lv|레벨)\s*(\d{1,3})\s*(이상|\+)?', s, re.I)
    level = ''
    if lv:
        n = lv.group(1) or lv.group(3)
        level = f'lv{n}' + ('+' if (lv.group(2) or lv.group(4)) else '')
    jobs = [en for ko, en in _JOBS.items() if ko in s]
    # '파티 구해요' / '파티 찾아요': looking for a party to join (not members)
    if not pq and re.search(r'파티\s*(?:구해요|구합니다|구함|찾아요|찾습니다)', s) and not re.search(r'파티원|\d\s*명', s):
        return ' '.join(x for x in ['LFP', *mods, level, *jobs] if x)
    if join and not (recruit and recruit.group(1)):
        head = 'J> ' + (pq or 'party')
        return ' '.join(x for x in [head, *mods, level, *jobs] if x)
    count = recruit.group(1) if recruit and recruit.group(1) else ''
    if not pq:
        if count:
            return ' '.join(x for x in [f'LF{count}M', *mods, level, *jobs] if x)
        return ' '.join(x for x in ['LFM', *mods, level, *jobs] if x)
    head = f'R> {pq}'
    return ' '.join(x for x in [head, *mods, f'need {count}' if count else '', *jobs, level] if x)


def korean_post(text: str, fallback: Callable[[str], str] | None = None) -> str | None:
    """A Korean trade / party post as Maple chat English, or None."""
    s = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not s or not re.search('[가-힣]', s):
        return None
    s = s.rstrip(' .!~')
    s = re.sub(r'(\d{1,3})\s*퍼(?:센트)?(?![가-힣])', r'\1%', s)            # '60퍼' -> '60%'
    party = _party(s)
    if party:
        return party
    # an English marker in front: 'S> 노목 900만'
    lead = re.match(r'\s*(S|B|T)\s*>\s*|\s*(WTS|WTB|WTT)\b\s*', s, re.I)
    lead_tag = ''
    if lead:
        lead_tag = (lead.group(1) or lead.group(2)[-1]).upper() + '>'
        s = s[lead.end():]
    # sell / buy / trade, possibly several parts: '... 팝니다 / ... 삽니다'
    pieces = re.split(rf'(?<=[가-힣])\s*(?:[/·]|,\s*(?=.*{_BUY}|.*{_SELL}))\s*', s) if re.search(r'[/·]', s) else [s]
    out, last_tag = [], ''
    for piece in pieces:
        tag = ''
        if re.search(_TRADE, piece):
            tag = 'T>'
        elif re.search(_SELL, piece) or re.search(r'급처|사실\s*분', piece):
            tag = 'S>'                                   # '사실 분' = anyone buying? (I sell)
        elif re.search(_BUY, piece) or re.search(r'파실\s*분', piece):
            tag = 'B>'                                   # '파실 분' = anyone selling? (I buy)
        if not tag and lead_tag and not out:
            tag = lead_tag
        if not tag and not last_tag and not lead_tag and _PRICE_RX.search(piece) and not re.search(r'[?？]|얼마', piece):
            # 'item + price' with no verb is how sellers write ('노목 3작 8공 9백만')
            tag = 'S>'
        if not tag:
            if not last_tag:
                return None
            tag = last_tag
        body = re.sub(f'{_SELL}|{_BUY}|{_TRADE}|사실\\s*분|파실\\s*분', ' ', piece)
        body = re.sub(r'(?:원해요|원합니다|합니다|해요|하실\s*분|있으신\s*분|계신가요|있나요)\s*$', ' ', body)
        if tag == 'T>':
            m = re.search(r'(.+?)\s*(?:랑|이랑|와|과|하고|를|을)\s+(.+)', body.strip())
            left, right = (m.group(1), m.group(2)) if m else (body, '')
            text_out = _segment(left, fallback) + (f' for {_segment(right, fallback)}' if right.strip() else '')
        else:
            text_out = _segment(body, fallback)
        if text_out is None:
            return None
        if re.search(r'전부|모두|싹\s*다|다\s*(?=삽니다|팝니다)', piece) and tag == 'B>':
            text_out = 'all ' + text_out
        out.append(f'{tag} {text_out}'.strip() if tag != last_tag or not out else text_out)
        last_tag = tag
    result = ' / '.join(x for x in out if x.strip())
    # never hand back Korean
    if re.search('[가-힣]', result) or re.fullmatch(r'[SBT]>\s*', result):
        return None
    return re.sub(r'\s{2,}', ' ', result).strip()
