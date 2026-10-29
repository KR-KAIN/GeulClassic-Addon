"""Hand-curated MapleStory Classic phrase interpreter.

Source context: https://meowdb.com/msclassic/ko/guides/maplestory-classic-glossary
The glossary is a reference, NOT a runtime scraper: short translations below are
independently written, and ambiguous words are interpreted in context.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import re

from .glossary_catalog import CATALOG, headwords, term_index
from .community_terms import COMMUNITY_TERMS
from .expanded_terms import ENTRIES as EXPANDED_ENTRIES, exact_label, scroll_label, contextual_short, AMBIGUOUS
SOURCE_URL = 'https://meowdb.com/msclassic/ko/guides/maplestory-classic-glossary'

@dataclass(frozen=True)
class Term:
    english: str
    korean: str
    category: str
    aliases: tuple[str, ...] = ()

TERMS = (
    Term('MS Classic', '메이플 클래식', '기본', ('MSCW',)),
    Term('pre-BB', '빅뱅 이전', '기본'),
    Term('grind', '반복 사냥', '사냥'),
    Term('ding', '레벨 업', '사냥'),
    Term('leech', '경험치 쩔', '사냥'),
    Term('PL', '빠른 레벨업 지원', '사냥', ('power level',)),
    Term('train', '함께 사냥', '사냥'),
    Term('respawn', '몬스터 재생성', '사냥'),
    Term('AP', '능력치 포인트', '능력치'),
    Term('SP', '스킬 포인트', '능력치'),
    Term('STR', '힘', '능력치'),
    Term('DEX', '민첩', '능력치'),
    Term('INT', '지력', '능력치'),
    Term('LUK', '운', '능력치'),
    Term('dexless', '덱스리스 빌드', '능력치'),
    Term('lukless', '럭리스 빌드', '능력치'),
    Term('pure stat', '순수 스탯 빌드', '능력치'),
    Term('prereq', '선행 조건', '스킬'),
    Term('buff', '버프', '스킬'),
    Term('mastery', '마스터리', '스킬'),
    Term('WATK', '무기 공격력', '전투', ('W.ATK',)),
    Term('MATK', '마법 공격력', '전투'),
    Term('PDEF', '물리 방어력', '전투'),
    Term('MDEF', '마법 방어력', '전투'),
    Term('ACC', '명중률', '전투'),
    Term('AVOID', '회피율', '전투'),
    Term('KB', '넉백', '전투'),
    Term('crit', '치명타', '전투'),
    Term('one-shot', '한 방 사냥', '전투'),
    Term('scroll', '주문서', '장비'),
    Term('clean', '미강화', '장비'),
    Term('slots', '강화 슬롯', '장비'),
    Term('god roll', '강화 대성공 아이템', '장비'),
    Term('boomed', '강화 실패로 파괴됨', '장비', ('brick',)),
    Term('untradeable', '거래 불가', '장비'),
    Term('claw', '아대', '장비'),
    Term('overall', '한벌옷', '장비', ('overalls',)),
    Term('Sauna Robe', '사우나 가운', '장비'),
    Term('PQ', '파티 퀘스트', '파티'),
    Term('kPQ', '커닝 파퀘', '파티', ('Kerning PQ',)),
    Term('LPQ', '루디 파퀘', '파티', ('Ludi PQ',)),
    Term('KS', '자리 스틸', '파티', ('kill steal',)),
    Term('carry', '고레벨 캐리', '파티'),
    Term('loot', '아이템 줍기', '파티'),
    Term('ninja loot', '남의 아이템 몰래 줍기', '파티'),
    Term('LFP', '파티 구함', '파티', ('LFG',)),
    Term('J>', '참가 희망', '파티'),
    Term('R>', '파티 모집', '파티'),
    Term('FM', '자유시장', '거래', ('Free Market',)),
    Term('mesos', '메소', '거래'),
    Term('merchant', '장사꾼', '거래'),
    Term('c/o', '현재 최고 제시가', '거래'),
    Term('a/w', '즉시 구매가', '거래'),
    Term('RES', '최소 판매가', '거래'),
    Term('RES MET', '최소 판매가 충족', '거래'),
    Term('ea', '개당', '거래'),
    Term('B>', '삽니다', '거래', ('WTB',)),
    Term('S>', '팝니다', '거래', ('WTS',)),
    Term('T>', '교환합니다', '거래', ('WTT',)),
    Term('CH', '채널', '거래'),
    Term('AFK', '자리 비움', '커뮤니티'),
    Term('BRB', '곧 돌아옴', '커뮤니티'),
    Term('GG', '수고했어요', '커뮤니티'),
    Term('RIP', '아이고, 망했다', '커뮤니티'),
    Term('cc', '채널 변경', '커뮤니티'),
    Term('noob', '초보자', '커뮤니티'),
    Term('sniping', '몬스터 선점 가로채기', '커뮤니티'),
)

# Provide every headword from the cited guide to the in-app glossary index,
# without reproducing the original guide's explanatory paragraphs.
_EXISTING = {term.english.casefold() for term in TERMS}
TERMS = TERMS + tuple(Term(en, ko, cat) for en,ko,cat in headwords()
                      if en.casefold() not in _EXISTING)
_EXISTING = {term.english.casefold() for term in TERMS}
TERMS = TERMS + tuple(Term(row.term, row.korean, row.category, row.aliases)
                      for row in EXPANDED_ENTRIES if row.term.casefold() not in _EXISTING)



_WORD_TERMS = {
    'kpq': '커닝 파퀘', 'kerning pq': '커닝 파퀘',
    'lpq': '루디 파퀘', 'pq': '파티 퀘스트',
    'clean claw': '미강화 아대', 'clean': '미강화',
    'claw': '아대', 'scroll': '주문서', 'overall': '한벌옷',
    'fame': '인기도', 'mesos': '메소', 'meso': '메소',
    'fm': '자유시장', 'cc': '채널 변경', 'ks': '스틸',
    'buff': '버프', 'cleric': '클레릭', 'party': '파티',
    'sword': '검', 'cape': '망토', 'boots': '신발',
}

_WORD_RE = re.compile(r'(?<!\w)(clean\s+claw|kerning\s+pq|lpq|kpq|pq|claw|scroll|overall|fame|mesos|meso|fm|cc|ks|buff|cleric|party|sword|cape|boots|clean)(?!\w)', re.I)
_MONEY_RE = re.compile(r'(?<!\w)(\d+(?:\.\d+)?)\s*([kmb])(?!\w)', re.I)
_MARKET_RE = re.compile(r'^\s*(s\s*>|b\s*>|t\s*>|j\s*>|r\s*>|wts\b|wtb\b|wtt\b)\s*(.*?)\s*$', re.I)
_OFFER_RE = re.compile(r'^\s*(c\s*/\s*o|h\s*/\s*o|l\s*/\s*o|a\s*/?\s*w|res\s+met|res)\s*[:=]?\s*(.*?)\s*$', re.I)
_WHITESPACE_RE = re.compile(r'\s+')
_LOCATION_RE = re.compile(r'^FM\s*(\d+)\s+CH\s*(\d+)$', re.I)


def canonical(text: str) -> str:
    return _WHITESPACE_RE.sub(' ', text.strip()).replace('＞', '>').replace('〉', '>').replace('／', '/')


def money_ko(token: str) -> str | None:
    match = _MONEY_RE.fullmatch(token.strip())
    if not match:
        return None
    value = Decimal(match.group(1)) * {'k': Decimal(1000), 'm': Decimal(1000000), 'b': Decimal(1000000000)}[match.group(2).lower()]
    if value == value.to_integral_value():
        total = int(value)
        if total % 100000000 == 0 and total >= 100000000:
            return f'{total // 100000000:,}억 메소'
        if total % 10000 == 0 and total >= 10000:
            return f'{total // 10000:,}만 메소'
        return f'{total:,} 메소'
    return format(value, ',f').rstrip('0').rstrip('.')+' 메소'


def _target_ko(words: str) -> str | None:
    """Translate only known item phrases; unknown items go through MT."""
    target = canonical(words).lower()
    if target in _WORD_TERMS:
        return _WORD_TERMS[target]
    combined = scroll_label(words)
    if combined:
        return combined
    # Shortcode aliases must be recognized in market listings while ordinary
    # English prose ("clean the room") still goes to the AI model.
    term = exact_label(words)
    if term:
        return term

    scroll = re.fullmatch(r'(\d{1,3})\s*%\s*scroll', target)
    if scroll:
        return f'{scroll.group(1)}% 주문서'
    pair = re.fullmatch(r'(.+?)\s+(claw|scroll|cape|overall)', target)
    if pair and pair.group(1) in ('clean', '60%', '10%', '100%'):
        return f'{_WORD_TERMS.get(pair.group(1), pair.group(1))} {_WORD_TERMS[pair.group(2)]}'
    return None


def _market_sentence(tag: str, payload: str) -> str | None:
    typ = re.sub(r'\s+', '', tag.lower())
    typ = {'wts': 's>', 'wtb': 'b>', 'wtt': 't>'}.get(typ, typ)
    payload = canonical(payload)
    if not payload:
        return None
    if typ in ('j>', 'r>'):
        need = re.fullmatch(r'(.+?)\s+(?:need\s+)?(\d+)\s*(?:more)?', payload, re.I)
        if need:
            target = _target_ko(need.group(1))
            if target:
                return f'{target} {need.group(2)}명 ' + ('참가 원해요' if typ == 'j>' else '모집해요')
        target = _target_ko(payload)
        if target:
            return f'{target} ' + ('참가 원해요' if typ == 'j>' else '모집해요')
        return None
    # e.g. S> 60% scroll 2m / B> clean claw / S> scroll 2m @ FM4 CH9
    location = ''
    placed = re.search(r'\s+@\s*(FM\s*\d+\s+CH\s*\d+)\s*$', payload, re.I)
    if not placed:
        placed = re.search(r'\s+(FM\s*\d+\s+CH\s*\d+)\s*$',payload,re.I)
    if placed:
        room = _LOCATION_RE.fullmatch(canonical(placed.group(1)))
        if room:
            location = f' ({room.group(2)}채널 자유시장 {room.group(1)}번 방)'
            payload = payload[:placed.start()].strip()
    # In market listings "AW" means instant buyout, while "C/O" is a bid,
    # not a promised selling price. Protect the number and item description.
    deal = re.search(r'\s+(a\s*/?\s*w|c\s*/\s*o|h\s*/\s*o|res)\s+(\d+(?:\.\d+)?\s*[kmb])\s*$',payload,re.I)
    if deal:
        status = re.sub(r'\s+','',deal.group(1).lower())
        status_name = {'aw':'즉시 구매가','a/w':'즉시 구매가',
                       'c/o':'현재 최고 제시가','h/o':'최고 제시가',
                       'res':'최소 판매가'}.get(status)
        item = _target_ko(payload[:deal.start()].strip())
        price = money_ko(deal.group(2))
        if item and price and status_name:
            action = {'s>':'팝니다','b>':'삽니다','t>':'교환합니다'}.get(typ)
            if action:
                return f'{item} {action} ({status_name} {price}){location}'
    each = bool(re.search(r'\s+ea$', payload, re.I))
    if each:
        payload = re.sub(r'\s+ea$', '', payload, flags=re.I).strip()
    price_match = re.search(r'\s+(\d+(?:\.\d+)?\s*[kmb])$', payload, re.I)
    price = money_ko(price_match.group(1)) if price_match else None
    item_source = payload[:price_match.start()].strip() if price_match else payload
    item = _target_ko(item_source)
    if item:
        price_prefix = ('개당 ' if each else '') + price + '에 ' if price else ''
        if typ == 's>':
            return f'{item} {price_prefix}팝니다{location}'
        if typ == 'b>':
            return f'{item} {price_prefix}삽니다{location}'
        if typ == 't>':
            return f'{item} 교환합니다{location}'
    return None


_EXACT_MARKET_TERMS = {
    'wts': '판매', 's>': '판매', 'wtb': '구매', 'b>': '구매',
    'wtt': '교환', 't>': '교환', 'pmo': '가격 제시 요망',
    'obo': '더 좋은 가격 제안 가능', 'c/o': '현재 최고 제시가',
    'a/w': '즉시 구매가', 'pc': '시세 문의', 'lf>': '구함',
    'att': '공격력', 'atk': '공격력', 'm.att': '마력',
    'ma': '마력', 'str': '힘', 'dex': '민첩', 'int': '지력',
    'luk': '행운', 'bwg': '브라운 워크글러브',
    'scg': '스톰캐스터 글러브', 'zhelm': '자쿰의 투구',
    'gfa': '장갑 공격력 주문서', 'gfma': '장갑 마력 주문서',
    'gma': '장갑 마력 주문서', 'css': '순백의 주문서',
    'ws': '백의 주문서',
}

_SCROLL_FULL_ALIASES = (
    (r'Scroll\s+for\s+One[- ]Handed\s+Sword\s+for\s+(?:ATT|ATK)', '한손검 공격력 주문서'),
    (r'Scroll\s+for\s+Two[- ]Handed\s+Sword\s+for\s+(?:ATT|ATK)', '두손검 공격력 주문서'),
    (r'Scroll\s+for\s+Wand\s+for\s+(?:Magic\s+(?:ATT|ATK)|M\.ATT)', '완드 마력 주문서'),
    (r'Scroll\s+for\s+Staff\s+for\s+(?:Magic\s+(?:ATT|ATK)|M\.ATT)', '스태프 마력 주문서'),
    (r'Scroll\s+for\s+Gloves?\s+for\s+(?:ATT|ATK)', '장갑 공격력 주문서'),
)


def _literal_scroll_trade(text: str) -> str | None:
    """Exact equipment/stat scroll names and rates only, no model guesswork."""
    for pattern, label in _SCROLL_FULL_ALIASES:
        m = re.fullmatch(pattern + r'\s*(100|70|60|30|10|1)\s*[%％]?', text, re.I)
        if m:
            return f'{label} {m.group(1)}%'
    return None


def _market_abbreviation(text: str) -> str | None:
    """Handle complete short transaction phrases, leave arbitrary prose to MT."""
    alias = _EXACT_MARKET_TERMS.get(text.casefold())
    if alias:
        return alias
    rate = re.fullmatch(r'(?i)(GFA|GFMA|GMA|CSS|WS)\s*(100|70|60|30|10|1)\s*[%％]', text)
    if rate:
        key = rate.group(1).casefold()
        return f'{_EXACT_MARKET_TERMS[key]} {rate.group(2)}%'
    return _literal_scroll_trade(text)


def rule_translate(text: str, direction: str) -> str | None:
    """Offline fast-path for high-frequency, context-sensitive phrases."""
    s = canonical(text)
    lo = s.casefold().rstrip('!~. ')
    if direction == 'en-ko':
        fixed = {
            'lfp': '파티 구해요', 'lfg': '파티 구해요',
            'pq': '파티 퀘스트', 'kpq': '커닝 파퀘', 'lpq': '루디 파퀘',
            'cc': '채널 변경', 'fm': '자유시장', 'ks': '자리 스틸',
            'afk': '자리 비움', 'brb': '곧 돌아올게요', 'gg': '수고했어요',
            'res met': '최소 판매가 충족',
            'inv me': '초대해 주세요', 'party': '파티',
            'party?': '파티 하실래요?', 'how much': '얼마인가요?',
            'offer': '가격 제안해 주세요',
            'cc plz': '채널 좀 바꿔 주세요', 'cc pls': '채널 좀 바꿔 주세요',
            'stop ks': '스틸하지 마세요', 'no ks': '스틸 금지',
        }
        if lo in COMMUNITY_TERMS and lo not in ('plz','pls','inv','mob','pot','pots','map','spawn','loot','solo','duo','trio'):
            return COMMUNITY_TERMS[lo]
        if lo in fixed:
            return fixed[lo]
        loc = _LOCATION_RE.fullmatch(s)
        if loc:
            return f'{loc.group(2)}채널 자유시장 {loc.group(1)}번 방'
        marker = _OFFER_RE.match(s)
        if marker:
            key = marker.group(1).lower().replace(' ', '')
            price = money_ko(marker.group(2))
            if price:
                return f"{ {'c/o': '현재 최고 제시가', 'a/w': '즉시 구매가', 'res': '최소 판매가', 'resmet': '최소 판매가 충족', 'aw': '즉시 구매가', 'h/o': '최고 제시가', 'l/o': '희망 제시가'}[key]} {price}"
        market = _MARKET_RE.match(s)
        if market:
            return _market_sentence(*market.groups())
        # Full reference glossary: exact headwords are translated locally
        # even when the machine-translation model is unavailable. Do not
        # replace ordinary words inside longer sentences without context.
        # Composite scroll/item labels, e.g. GFA 60%, Helmet DEX 10%.
        combined = scroll_label(s)
        if combined:
            return combined
        context_value = contextual_short(s)
        if context_value:
            return context_value
        # Single-letter and reused codes have multiple meanings in chat.
        # Preserve uncertainty instead of falsely choosing one sense.
        if s.casefold() == 'cs':
            return 'CS(혼줌/캐시샵, 문맥 확인)'
        if s.casefold() in ('bm','mm','bs','am','r','a','pc','bb','ee','gs','ht'):
            return s + '(문맥 확인)'
        # Preserve established NiaMeowDB headword renderings when the same
        # complete English term appears in both source collections.
        entry = term_index().get(s.casefold())
        if entry:
            return entry[0]
        expanded = exact_label(s)
        if expanded:
            return expanded
        # Extra aliases only after established context-sensitive vocabulary.
        return _market_abbreviation(s)
    if direction == 'ko-en':
        fixed = {
            '파티 초대해 주세요': 'Please invite me to your party.',
            '파티 구해요': 'LFP',
            '얼마인가요': 'How much?',
            '조금 깎아주실 수 있나요': 'Could you lower the price a bit?',
            '잠시만요': 'One moment, please.',
            '어디서 사냥해요': 'Where are you training?',
            '채널 좀 옮겨주세요': 'cc plz',
            '스틸하지 마세요': 'Stop KS.',
            '커닝 파퀘 참가 원해요': 'J> kPQ',
            '커닝 파퀘 2명 모집해요': 'R> kPQ need 2',
        }
        if s in fixed:
            return fixed[s]
        recruits = re.fullmatch(r'(커닝\s*파퀘|루디\s*파퀘)\s*(\d+)\s*명\s*모집(?:해요|합니다)?', s)
        if recruits:
            return f'R> {"kPQ" if recruits.group(1).startswith("커닝") else "LPQ"} need {recruits.group(2)}'
        selling = re.fullmatch(r'(\d+)%\s*주문서\s*(\d+)만\s*메소에\s*(팝니다|삽니다)', s)
        if selling:
            tag = 'S>' if selling.group(3) == '팝니다' else 'B>'
            price = Decimal(selling.group(2)) / Decimal(100)
            return f'{tag} {selling.group(1)}% scroll {format(price, "f").rstrip("0").rstrip(".")}m'
    return None


def _money_expand(match: re.Match) -> str:
    unit = {'k': 'thousand', 'm': 'million', 'b': 'billion'}[match.group(2).lower()]
    return f'{match.group(1)} {unit} mesos'


def expand_for_mt(text: str, direction: str) -> str:
    """Disambiguate abbreviations *before* machine translation.

    Avoid blindly replacing ordinary words such as 'clean' or 'train'.
    """
    text = canonical(text)
    if direction == 'en-ko':
        text = _MONEY_RE.sub(_money_expand, text)
        market = _MARKET_RE.match(text)
        if market:
            verb = re.sub(r'\s+', '', market.group(1).casefold())
            verb = {'s>': 'Selling', 'wts': 'Selling', 'b>': 'Buying', 'wtb': 'Buying',
                    't>': 'Trading', 'wtt': 'Trading', 'j>': 'Looking to join',
                    'r>': 'Recruiting'}.get(verb, verb)
            text = f'{verb}: {market.group(2)}'
        substitutions = (
            (r'(?<!\w)c\s*/\s*o(?!\w)', 'current highest bid'),
            (r'(?<!\w)a\s*/\s*w(?!\w)', 'instant purchase price'),
            (r'\bres\s+met\b', 'minimum sale price reached'),
            (r'\bkpq\b', 'Kerning City party quest'),
            (r'\blpq\b', 'Ludibrium party quest'),
            (r'\bKS\b', 'kill stealing'),
            (r'\bcc\b', 'change channel'),
            (r'\bFM\b', 'Free Market'),
            (r'\bLFP\b|\bLFG\b', 'looking for party'),
            (r'\bclean\s+(?=claw|overall|cape|sword|boots\b)', 'unscrolled '),
            (r'\b(10|60|100)%\s*scroll\b', r'\1% equipment upgrade scroll'),
        )
        for regex, replacement in substitutions:
            text = re.sub(regex, replacement, text, flags=re.I)
        # Phrase disambiguation for common market shorthand, with word boundaries.
        # Keep CS/BM/MM/BS unexpanded unless a recognized surrounding context.
        extra_substitutions = (
            (r'(?<!\w)GFA(?=\s+\d+\s*%|\b)', 'glove attack scroll'),
            (r'(?<!\w)GMA(?=\s+\d+\s*%|\b)', 'glove magic attack scroll'),
            (r'\bWG\b', 'work gloves'),
            (r'\bZhelm\b', 'Zakum helmet'),
            (r'\bHP\s+wash(?:ing)?\b', 'HP washing stat allocation'),
            (r'\bFoG\b', 'Forest of Golem hunting map'),
            (r'\bLHC\b', 'Lion Heart Castle'),
            (r'\bOPQ\b', 'Orbis party quest'),
            (r'\bGPQ\b', 'guild party quest'),
        )
        for regex, replacement in extra_substitutions:
            text = re.sub(regex,replacement,text,flags=re.I)
    elif direction == 'ko-en':
        substitutions = (
            (r'커닝\s*파퀘', 'Kerning City party quest'),
            (r'루디\s*파퀘', 'Ludibrium party quest'),
            (r'파티\s*퀘스트', 'party quest'),
            (r'자유시장', 'Free Market'),
            (r'아대', 'claw weapon'),
            (r'미강화', 'unscrolled'),
            (r'주문서', 'equipment upgrade scroll'),
            (r'자리\s*스틸', 'kill stealing'),
        )
        for regex, replacement in substitutions:
            text = re.sub(regex, replacement, text)
    return text


def normalize_mt_result(text: str, direction: str) -> str:
    if direction == 'en-ko':
        for key, value in (
            ('커닝시티 파티 퀘스트', '커닝 파퀘'),
            ('루디브리엄 파티 퀘스트', '루디 파퀘'),
            ('파티 퀘스트', '파티 퀘스트'),
            ('킬 스틸', '스틸'),
        ):
            text = text.replace(key, value)
    return text
