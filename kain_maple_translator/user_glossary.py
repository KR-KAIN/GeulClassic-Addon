"""User glossary (Global Maple Classic abbreviations, 2026-10-28 workbook).

Two uses, both conservative:
1. glossary_sentence(): a short chat line made only of glossary terms
   ("GG, TYFP. GTG", "CC pls, no KS", "BRB, repot") is read term by term.
   Any unknown word -> None, so normal sentences still go to the model.
2. glossary_leftover(): after translation, an abbreviation that is still in
   English and also present in the source line gets its Korean meaning
   ("HHG" -> 헤네시스 사냥터). Ambiguous spellings (CB, SS, MG ...) and
   rows marked '문맥 확인' are never replaced.
"""
from __future__ import annotations
import re
from functools import lru_cache

from .user_glossary_data import ENTRIES

# Short chat wording for rows whose 한국어 뜻 column is an explanation.
SHORT = {
    'pmo': '가격 제안은 귓말로', 'l/o': '가격 제안 남겨 주세요', 'lo': '가격 제안 남겨 주세요',
    'l/n/o': '닉네임과 가격 남겨 주세요', 'lno': '닉네임과 가격 남겨 주세요',
    's/b': '시작가', 'c/o': '현재가', 'h/o': '최고가', 'a/w': '즉결가', 'b/o': '즉시 구매가',
    'obo': '가격 협의 가능', 'res': '최저가', 'reserve': '최저가', 'res met': '최저가 도달',
    'pc': '시세 문의', 'p/c': '시세 문의', 'nego': '흥정 가능', 'neg': '흥정 가능',
    'firm': '가격 고정', 'bulk': '대량', 'no lowball': '후려치기 사절', 'mesos only': '메소로만 거래',
    'fcfs': '선착순', 'offer': '가격 제안', 'nx trash': '잡캐시템', 'junk nx': '잡캐시템',
    'merch': '되팔이', 'merchant': '되팔이', 'merching': '되팔이', 'clean': '노작',
    'scrolled': '작 된 장비', 'godly': '옵션 좋은', 'god roll': '옵션 좋은', 'boomed': '파괴됨',
    'smega': '확성기', 'smeg': '확성기', 'mega': '확성기', 'nx': '캐시',
    'inv': '초대', 'ldr': '파티장', 'lead': '파티장', 'full': '파티 꽉 찼어요',
    'lfg': '파티 구해요', 'lfm': '인원 구해요', 'lfp': '파티 구해요', 'lf pt': '파티 구해요',
    'lf1m': '1명 구해요', 'lf2m': '2명 구해요', 'r>': '모집', 'j>': '참가 원해요',
    'pq': '파티 퀘스트', 'kpq': '커닝 파퀘', 'kerning pq': '커닝 파퀘', 'jq': '점프 퀘스트',
    'rush': '연속 진행', 'bonus': '보너스 구간', 'pass': '통행증', 'run': '한 판',
    'ks': '스틸', 'ksing': '스틸', 'cc': '채널 변경', 'ch': '채널', 'carry': '캐리', 'leech': '쩔',
    'repot': '물약 보충', 'grind': '사냥', 'grinding': '사냥', 'loot': '아이템 줍기',
    'ninja loot': '몰래 루팅', 'preq': '선행 퀘스트', 'prequest': '선행 퀘스트',
    'afk': '잠수', 'brb': '금방 올게요', 'brt': '곧 갈게요', 'gtg': '이제 가야 해요',
    'g2g': '이제 가야 해요', 'otw': '가는 중이에요', 'omw': '가는 중이에요', 'wb': '어서 와요',
    'cya': '나중에 봐요', 'ttyl': '나중에 얘기해요', 'ty': '고마워요', 'thx': '고마워요',
    'thnx': '고마워요', 'tysm': '정말 고마워요', 'tyfp': '파티 고마웠어요', 'np': '괜찮아요',
    'yw': '천만에요', 'sry': '미안해요', 'mb': '제 실수예요', 'dw': '걱정 마세요',
    'pls': '부탁해요', 'plz': '부탁해요', 'pl0x': '부탁해요', 'plox': '부탁해요',
    'gz': '축하해요', 'gratz': '축하해요', 'grats': '축하해요', 'gl': '행운을 빌어요',
    'hf': '재밌게 하세요', 'glhf': '행운을 빌어요, 재밌게 하세요', 'gg': '수고했어요',
    'gj': '잘했어요', 'lol': 'ㅋㅋ', 'lawl': 'ㅋㅋ', 'lmao': 'ㅋㅋㅋ', 'lmfao': 'ㅋㅋㅋ',
    'rofl': 'ㅋㅋㅋㅋ', 'omg': '헐', 'omfg': '헐', 'idk': '모르겠어요', 'idc': '상관없어요',
    'ik': '알아요', 'ikr': '그러게요', 'iirc': '제 기억으로는', 'imo': '제 생각엔',
    'imho': '제 생각엔', 'tbh': '솔직히', 'ngl': '솔직히', 'btw': '그런데', 'fyi': '참고로',
    'jk': '농담이에요', 'irl': '현실에서', 'rl': '현실', 'atm': '지금은', 'rn': '지금',
    'tmr': '내일', 'tmrw': '내일', 'hmu': '연락 주세요', 'lmk': '알려 주세요',
    'k': '알겠어요', 'kk': '알겠어요', 'ok': '알겠어요', 'w/e': '아무거나', 'wbu': '당신은요?',
    'wc': '채팅 잘못 쳤어요', 'w/c': '채팅 잘못 쳤어요', 'rip': '아이고', 'ez': '쉽네요',
    'op': '사기급', 'newb': '뉴비', 'newbie': '뉴비', 'noob': '뉴비', 'nub': '뉴비',
    'vet': '고인물', 'pm': '귓말', 'dm': '귓말', 'whisp': '귓말', 'nvm': '신경 쓰지 마세요',
    'ppl': '사람들', 'd/c': '튕겼어요', 'dc': '튕겼어요', "dc'd": '튕겼어요', 'relog': '재접속',
    'lag': '렉', 'sc': '서버 점검', 'ign': '닉네임', 'bl': '친구 목록', 'char': '캐릭터',
    'gm': '운영자', 'fame': '인기도 올려주세요', 'defame': '인기도 내리기',
    'buff': '버프', 'rebuff': '버프 다시', 'debuff': '디버프', 'aggro': '어그로', 'lure': '몰이',
    'party': '파티', 'pt': '파티', 'pots': '물약', 'ap': 'AP', 'sp': 'SP', 'exp': '경험치',
    'xp': '경험치', 'hp': 'HP', 'mp': 'MP', 'lv': '레벨', 'lvl': '레벨', 'sin': '어쌔신',
    'dit': '시프', 'wg': '노가다 목장갑', 'wgs': '노가다 목장갑', 'eq': '장비', 'equips': '장비',
    'bis': '최고 장비',
    # R19 audit (game-only abbreviations that stayed in English)
    'sb': 'SB(슬래시 블러스트·세비지 블로우)', 'fa': 'FA(파이널 어택·파이어 애로우)',
    'ab': 'AB(애로우 블로우·애로우 봄)', 'ds': 'DS(더블 샷·더블 스탭·다크 사이트)',
    'mc': 'MC(매직 클로·몬스터 카니발)', 'cb': 'CB(콜드 빔·크로스보우 부스터)',
    'ar': 'AR(애로우 레인·엔젤레이)', 'hh': 'HH(헤드리스 호스맨·생츄어리)', 'mm': 'MM(머쉬맘·신궁)',
    'gs': 'GS(건슬링거·유령선)', 'ss': 'SS(스크린샷·연막탄)', 'bb': 'BB(보우 부스터·잘 가요)',
    'sw': 'SW(검·스푸키 월드)', 'fw': 'FW(승리 양보·승부)',
    'mg': '매직 가드', 'eb': '에너지 볼트', 'imr': 'MP 회복력 향상', 'mmi': '최대 MP 증가',
    'tp': '텔레포트', 'med': '메디테이션', 'ib': '아이언 바디', 'tb': '썬더 볼트',
    'bga': '보디가드 A', 'bgb': '보디가드 B', 'esw': '스푸키 월드 입구', 'npc': 'NPC',
    'npcing': 'NPC에 팔기', 'p2w': '현질 게임', 'ulu1': '울루 1', 'ulu2': '울루 2',
    'sindit': '표도(신딧) 빌드', 'banditsin': '표도(신딧) 빌드', 'fizard': '불 위자드',
    'pizard': '독 위자드', 'lizzard': '썬콜 위자드', 'pgc': '분홍 가이아 망토', 'pugc': '보라 가이아 망토',
    'yss': '노란 스노우슈즈', 'vss': '보라 스노우슈즈', 'duo': '2인', 'trio': '3인', 'quad': '4인',
    'brick': '망한 작', 'bricked': '망한 작', 'perfect': '완벽한 작', 'bot': '봇',
    'fondue': '초콜릿 퐁듀', 'halo': '천사의 헤일로', 'michael': '미카엘 날개', 'rifle': '장난감 총',
    'selective': '셀렉티브 쿠폰', 'oa': '전신 갑옷', 'ma': '마력', 'wd': '물리 방어력', 'md': '마법 방어력',
    'vic': '빅토리아 아일랜드', 'aqua': '아쿠아로드', 'ludi': '루디브리엄', 'tot': '시간의 신전',
    'zip': '지팡구', 'ftp': '판타지 테마파크', 'skele': '스켈레곤', 'skeles': '스켈레곤',
    'petri': '페트리파이터', 'hime': '드리미 고스트', 'himes': '드리미 고스트',
    'dexless': '덱스리스', 'lukless': '럭리스', 'strless': '힘 미투자', 'hybrid': '하이브리드',
    'mpe': 'MP 이터', 'gs1': '유령선 1', 'gs2': '유령선 2', 'michaels': '미카엘 날개',
    'me': '저', 'mule': '부캐', 'main': '본캐', 'srs': '진심이에요', 'srsly': '진심이에요',
    'door': '미스틱 도어', 'elix': '엘릭서', 'aw': '즉결가',
    'intermediate': '중급', 'lesser': '하급', 'greater': '상급', 'chaos': '혼돈',
    '1st': '1차 전직', '2nd': '2차 전직', '3rd': '3차 전직', '4th': '4차 전직',
    '1st job': '1차 전직', '2nd job': '2차 전직', '3rd job': '3차 전직', '4th job': '4차 전직',
}
# Several meanings: shown with the abbreviation, replaced after the
# sentence model only when typed in capitals ('need SB' / 'SB pls').
_CAPS_ONLY = {'sb', 'fa', 'ab', 'ds', 'mc', 'cb', 'ar', 'hh', 'mm', 'gs', 'ss', 'bb', 'sw', 'fw',
              'mg', 'eb', 'ib', 'tb', 'tp', 'oa', 'ma', 'wd', 'md', 'bga', 'bgb', 'esw', 'imr', 'mmi',
              'pgc', 'pugc', 'yss', 'vss'}

# Common English words: never swapped inside a translated sentence.
_ENGLISH = set('''
run full pass slot spot offer firm bulk clean perfect rifle halo door aqua track vet lag fame
bot char pure hybrid buff booster soul med tele crimson sleepy zip loot lead grind grinding
carry leech debuff rebuff aggro lure coupon bonus rush helm bottom sword rog nate gen gene met
michael selective fondue pots slots scrolled godly boomed brick bricked equips mega merch
merchant merching inv need sin dit rip vic llama ftp mp3 tot op ok kk wb bb lol omg ppl
idk rn atm rl ty np yw jk pm dm gg gl hf ez k b m f haste skele petri hime door ludi
party pt ap sp hp mp exp xp lv lvl char ign gm pc res reserve nego neg nx smega smeg pq
'''.split())

_THANKS = {'ty', 'thx', 'thnx', 'thanks', 'tysm', 'thank you'}
_PLEASE = {'pls', 'plz', 'please', 'pl0x', 'plox'}
_PHRASES = {
    'pass lead': '파티장 넘겨 주세요', 'pass lead pls': '파티장 넘겨 주세요',
    'pass ldr': '파티장 넘겨 주세요', 'pass ldr pls': '파티장 넘겨 주세요',
    'buff pls': '버프 부탁해요', 'buffs pls': '버프 부탁해요',
    # R19 audit: '<verb> me' and other two-word chat
    'carry me': '캐리해 주세요', 'inv me': '초대해 주세요', 'invite me': '초대해 주세요',
    'add me': '추가해 주세요', 'buff me': '버프 주세요', 'hb me': '하이퍼 바디 주세요',
    'hs me': '홀리 심볼 주세요', 'trade me': '거래 걸어 주세요', 'pm me': '귓말 주세요',
    'msg me': '귓말 주세요', 'whisper me': '귓말 주세요', 'ty all': '모두 고마워요',
    'thx all': '모두 고마워요', 'ty guys': '다들 고마워요', 'thx guys': '다들 고마워요',
    'ks free': '스틸 안 해요', 'no ks': '스틸 금지', 'pure luk': '올럭', 'pure str': '올힘',
    'pure dex': '올덱', 'pure int': '올인트', 'perm nx': '영구 캐시템',
    'thats op': '그거 사기네요', "that's op": '그거 사기네요', 'so op': '완전 사기네요',
    'cc pls ks': '스틸이에요, 채널 바꿔 주세요', 'cc ks': '스틸이에요, 채널 바꿔 주세요',
}
_NAME_CATEGORIES = ('지역', '몬스터', '장비', '아이템', '직업', '스킬', 'PQ', '사냥', '빌드')


def _forms(form: str):
    form = form.strip()
    if '(s)' in form:
        yield form.replace('(s)', '').lower()
        yield form.replace('(s)', 's').lower()
        return
    yield form.lower()


def _label(korean: str) -> str:
    return re.split(r'[;·,]', korean)[0].strip()


@lru_cache(maxsize=1)
def _tables():
    seen: dict[str, set] = {}
    rows: dict[str, tuple] = {}
    for cat, forms, english, korean, status, note in ENTRIES:
        for f in forms:
            for key in _forms(f):
                seen.setdefault(key, set()).add(korean)
                rows.setdefault(key, (cat, english, korean, status))
    vocab: dict[str, str] = {}
    leftover: dict[str, str] = {}
    for key, meanings in seen.items():
        cat, english, korean, status = rows[key]
        ambiguous = len(meanings) > 1 or status == '문맥 확인' or ' / ' in korean
        label = SHORT.get(key) or ('' if ambiguous else _label(korean))
        if not label or '=' in label or (len(label) > 16 and key not in SHORT):
            continue
        vocab[key] = label
        if (not ambiguous and len(key) >= 3 and key not in _ENGLISH and re.search('[a-z]', key)
                and re.fullmatch(r"[a-z0-9][a-z0-9 .'’/-]*", key) and not key.endswith('>')):
            leftover[key] = label
    for key, label in SHORT.items():
        vocab.setdefault(key, label)
    for key in _CAPS_ONLY:
        if key in SHORT:
            leftover[key] = SHORT[key]
    for key in ('sindit', 'banditsin', 'fizard', 'pizard', 'lizzard', 'ulu1', 'ulu2', 'npcing', 'p2w',
                'bricked', 'fondue', 'selective', 'skele', 'skeles', 'petri', 'hime', 'himes', 'duo', 'trio'):
        leftover[key] = SHORT[key]
    # English full names of places, monsters, items, jobs and skills.
    names: dict[str, str] = {}
    for cat, forms, english, korean, status, note in ENTRIES:
        if not any(c in cat for c in _NAME_CATEGORIES) or '/' in english or ' / ' in korean:
            continue
        if english in ('—', '') or status == '문맥 확인' or len(english) < 5:
            continue
        label = _label(korean)
        if label and len(label) <= 16 and english.lower() not in _ENGLISH and not label.startswith('해당'):
            names[english.lower()] = label
    return vocab, leftover, names


def _rx(keys):
    alt = '|'.join(re.escape(k) for k in sorted(keys, key=len, reverse=True))
    return re.compile(r"(?<![A-Za-z0-9_\[/'])(" + alt + r")(?![A-Za-z0-9_\]/'])", re.I)


@lru_cache(maxsize=1)
def _regexes():
    vocab, leftover, names = _tables()
    return _rx(leftover), _rx(names)


# ------------------------------------------------------------- whole lines
def _unit(words, i):
    """Longest glossary term starting at words[i] -> (label, next index)."""
    vocab = _tables()[0]
    for n in (3, 2, 1):
        if i + n <= len(words):
            key = ' '.join(words[i:i + n])
            if key in _PHRASES:
                return _PHRASES[key], i + n
            if key in vocab:
                return vocab[key], i + n
    return None, i


def _segment(seg: str) -> str | None:
    words = [w.strip("!?~^") for w in seg.lower().replace('’', "'").split()]
    words = [w for w in words if w]
    if not words:
        return ''
    # 'LF sin for EEC' / 'lf DSG party'
    if words[0] == 'need' and 'for' in words[2:] and len(words) > 3:
        cut = words.index('for', 2)
        who, where = _segment(' '.join(words[1:cut])), _segment(' '.join(words[cut + 1:]))
        return f'{where} 갈 {who} 필요해요' if who and where else None
    if words[0] in ('lf', 'lfm', 'lf>') and len(words) > 1:
        while len(words) > 2 and words[-1] in _PLEASE:
            words = words[:-1]
        if 'need' in words[2:]:
            cut = words.index('need', 2)
            first, wanted = _segment(' '.join(words[:cut])), _segment(' '.join(words[cut + 1:]))
            return f'{first}, {wanted} 필요해요' if first and wanted else None
        rest = ' '.join(words[1:])
        m = re.fullmatch(r'(.+?)\s+for\s+(.+)', rest)
        who = _segment(m.group(1)) if m else _segment(rest)
        if m and m.group(2) in ('party', 'pt', 'my party', 'our party', 'the party'):
            return f'{who} 파티원 구해요' if who else None
        where = _segment(m.group(2)) if m else None
        if who and (where or not m):
            return (f'{where} 갈 ' if where else '') + f'{who} 구해요'
        return None
    # 'going to Vic' / 'heading to ludi' / 'otw to aqua'
    if words[0] in ('going', 'goin', 'heading', 'omw', 'otw', 'go') and len(words) > 1:
        rest = words[1:]
        if rest[0] == 'to':
            rest = rest[1:]
        place = _segment(' '.join(rest)) if rest else None
        return f'{place} 가는 중이에요' if place else None
    # 'im a fizard' / "i'm an IL"
    if words[0] in ('im', "i'm", 'i am') and len(words) > 2 and words[1] in ('a', 'an'):
        what = _segment(' '.join(words[2:]))
        if not what:
            return None
        josa = '이에요' if re.search('[가-힣]$', what) and (ord(what[-1]) - 0xAC00) % 28 else '예요'
        return f'저 {what}{josa}'
    if words[0] in ('im', "i'm") and len(words) > 2 and words[-1] == 'now':   # 'im 2nd job now'
        what = _segment(' '.join(words[1:-1]))
        if what and re.search('[가-힣]$', what):
            josa = '이에요' if (ord(what[-1]) - 0xAC00) % 28 else '예요'
            return f'저 이제 {what}{josa}'
        return None
    if words[0] in ('im', "i'm") and len(words) > 1:      # "im ks free"
        return _segment(' '.join(words[1:]))
    # 'gz on 2nd job' / 'grats on 30'
    if words[0] in ('gz', 'gratz', 'grats', 'congrats', 'congratz', 'gj') and len(words) > 2 and words[1] == 'on':
        rest = words[2:]
        if len(rest) == 1 and re.fullmatch(r'\d{1,3}', rest[0]):
            return f'{rest[0]}레벨 축하해요'          # 'grats on 30'
        what = _segment(' '.join(rest))
        return f'{what} 축하해요' if what else None
    pieces: list[str] = []
    i = 0
    neg = need = False
    while i < len(words):
        w = words[i]
        label, k = _unit(words, i)
        if label and k - i > 1:  # multi-word terms first ('no lowball')
            if need:
                label, need = re.sub(r' 부탁해요$', '', label) + ' 필요해요' + (
                    ', 부탁해요' if label.endswith('부탁해요') else ''), False
            if neg:
                label, neg = label + ' 금지', False
            pieces.append(label)
            i = k
            continue
        if w in _PLEASE and pieces:
            if not pieces[-1].endswith(('요', '세요')):
                pieces[-1] += ' 부탁해요'
            i += 1
            continue
        if w in _THANKS and i + 1 < len(words) and words[i + 1] in ('4', 'for'):
            j = i + 2 + (1 if i + 2 < len(words) and words[i + 2] == 'the' else 0)
            label, k = _unit(words, j)
            if label:
                pieces.append(f'{label} 고마워요')
                i = k
                continue
            return None
        if w == 'no':
            neg = True
            i += 1
            continue
        if w == 'need':
            need = True
            i += 1
            continue
        if w == 'i':
            i += 1
            continue
        if re.fullmatch(r'\d{1,3}', w) and i + 1 < len(words) and words[i + 1] in ('min', 'mins', 'm', 'minutes'):
            pieces.append(f'{w}분')
            i += 2
            continue
        if re.fullmatch(r'\d{1,4}', w) and pieces:     # 'mule lvl 30'
            pieces.append(w)
            i += 1
            continue
        label, k = _unit(words, i)
        if not label:
            return None
        if neg:
            label, neg = label + ' 금지', False
        if need:
            label, need = label + ' 필요', False
        pieces.append(label)
        i = k
    if neg or need:
        return None
    out = ' '.join(pieces)
    # 'need mw pls' -> '메이플 용사 필요해요' (a sentence, not a label)
    return out + '해요' if out.endswith(' 필요') else out


def glossary_sentence(text: str) -> str | None:
    """Translate a short line made only of glossary terms, else None."""
    value = re.sub(r'\s+', ' ', (text or '').strip())
    if not value or len(value) > 60 or '[' in value or re.search(r'[가-힣]', value):
        return None
    if re.match(r'(?:[SBTA]\s*>|WT[SBT]\b|selling\b|buying\b)', value, re.I):
        return None  # trade posts have their own parsers
    # ('LF1M' is a party word, not a 1m price)
    if re.search(r'(?<![A-Za-z])\d+(?:\.\d+)?\s*[kmb]\b|%|https?:|www\.', value, re.I):
        return None  # prices and stats belong to the trade parsers
    parts = re.split(r'([,.;!?]+\s*)', value)
    out = []
    terms = 0
    for idx, part in enumerate(parts):
        if idx % 2:
            out.append(part.strip()[:1] + ' ' if part.strip()[:1] in ',.;' else part)
            continue
        if not part.strip():
            continue
        ko = _segment(part)
        if ko is None:
            return None
        terms += 1
        out.append(ko)
    result = ''.join(out).strip().rstrip(',;').strip()
    result = re.sub(r'잠수 (\d+분)', r'\1 동안 자리 비울게요', result)
    return result if terms and result else None


# ------------------------------------------------------------- leftovers
def glossary_leftover(source: str, result: str) -> str:
    """Korean for glossary abbreviations/names still in English after MT.

    Only words that also occur in the source line are changed, and never
    inside [linked item] labels.
    """
    if not result or not re.search(r'[A-Za-z]', result):
        return result
    abbr_rx, name_rx = _regexes()
    vocab, leftover, names = _tables()
    src = (source or '').lower()
    parts = re.split(r'(\[[^\[\]\n]+\])', result)
    for i in range(0, len(parts), 2):
        seg = parts[i]
        seg = name_rx.sub(lambda m: names.get(m.group(1).lower(), m.group(1)), seg)

        def swap(m):
            word = m.group(1)
            key = word.lower()
            if key not in leftover or key not in src:
                return word
            if m.string[m.end():m.end() + 1] == '(':
                return word      # 'SB(슬래시 블러스트·…)' is annotated already
            if key in _CAPS_ONLY and re.search(r'(?i)\b(?:dm|pm|msg)\s*$', m.string[:m.start()]):
                return word
            if key in _CAPS_ONLY and re.match(r'\s*\d{1,3}\s*%', m.string[m.end():]):
                return word      # 'FA 60%' is a scroll name (OCR of GFA), not a skill
            if key in _CAPS_ONLY and not re.search(r'(?<![A-Za-z])' + re.escape(word.upper()) + r'(?![A-Za-z])',
                                                   source or ''):
                return word      # lower-case 'ar', 'mm', 'sw' are ordinary words
            return leftover[key]
        parts[i] = abbr_rx.sub(swap, seg)
    return ''.join(parts)
