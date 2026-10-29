"""Researched chat slang and Maple abbreviations for free-form EN->KO chat.

The offline MT model garbles raw shorthand ("ngl this map is so op lol"), but
translates spelled-out English far better.  This module therefore:

1. peels discourse markers (ngl, lol, smh, fr ...) off the start/end of a
   message and maps them straight to Korean chat words;
2. rewrites in-sentence shorthand into plain English before MT;
3. replaces English game names that MT leaves untouched with Korean names.

Trade lines, URLs, [item links], prices and numbers are never rewritten.
Exact-match terms already live in expanded_terms.py / chat_shorthand.py.
"""
from __future__ import annotations
import re

SOURCES = (
    'https://ayumilove.net/maplestory-abbreviations/',
    'https://meowdb.com/msclassic/ko/guides/maplestory-classic-glossary',
    'https://strategywiki.org/wiki/MapleStory/Glossary',
    'https://migaku.com/blog/language-fun/english-internet-slang-abbreviations',
)

# Lines that must stay on the trade/item code paths.
_TRADE = re.compile(r'(?i)(?:^|\s)(?:[SBTRJAL]\s*>|LF>|wts\b|wtb\b|wtt\b)|'
                    r'\d+(?:\.\d+)?\s*[kmb]\b|https?\s*:|www\.|discord\.gg|\bc\s*/\s*o\b|\ba\s*/\s*w\b')

# ---------------------------------------------------------------- 1. markers
_LAUGH = r'(?:l+o+l+[sz]?|lmf?ao+|rofl|lul|kek|x+d+|(?:ha){2,}h?|(?:he){2,}|(?:ja){2,})'
# (regex, Korean, position).  'front' markers lead the Korean sentence.
_MARKERS = (
    (r'not gonna lie|not going to lie|ngl|tbh|tbf|honestly|to be honest', '솔직히', 'front'),
    (r'imo|imho|in my opinion', '내 생각엔', 'front'),
    (r'btw|by the way', '근데', 'front'),
    (r'bruh+|bruv', '아니', 'front'),
    (r'omg+|omfg|oh my god|omagad', '헐', 'front'),
    (r'wtf|wth', '뭐야', 'front'),
    (r'fr fr|frfr|fr|for real|ong|on god|deadass', '진짜', 'front'),
    (r'lowkey', '은근', 'front'),
    (r'yo+', '야', 'front'),
    (r'ugh+|ughh+', '아오', 'front'),
    (r'rip', '아이고', 'front'),
    (r'smh|smdh|welp', '에휴', 'back'),
    (_LAUGH, 'ㅋㅋ', 'back'),
    (r'bro|dude|man|mate|guys', '', 'back'),
)
_MARKER_RES = tuple((re.compile(r'(?i)^(?:'+p+r')$'), ko, pos) for p, ko, pos in _MARKERS)
_EMOTICON = re.compile(r'^(?::\)+|:\(+|:d+|:p|;\)|xd|\^\^|\^_\^|<3|T_T|;_;|:3|o\.o)$', re.I)
_PUNCT = ' ,.!?~…'


def _marker(words: list[str]) -> tuple[int, str, str] | None:
    """Longest marker (up to 4 words) at the start of ``words``."""
    for size in (4, 3, 2, 1):
        if len(words) < size:
            continue
        phrase = ' '.join(words[:size]).strip(_PUNCT)
        for regex, ko, pos in _MARKER_RES:
            if regex.match(phrase):
                return size, ko, pos
    return None


def peel_markers(text: str):
    """Split ``text`` into (front_ko, core, back_ko); None when nothing peeled."""
    if _TRADE.search(text) or '[' in text:
        return None
    words = text.split()
    front: list[str] = []
    back: list[str] = []
    peeled = False
    while words:
        found = _marker(words)
        if not found:
            break
        size, ko, pos = found
        (front if pos == 'front' else back).append(ko)
        words = words[size:]
        peeled = True
    while words:
        if _EMOTICON.match(words[-1].strip(',.!?~')):
            back.insert(0, words.pop().strip(',.'))
            peeled = True
            continue
        found = None
        for size in (3, 2, 1):
            if len(words) >= size:
                tail = _marker(words[-size:])
                if tail and tail[0] == size:
                    found = tail
                    break
        if not found:
            break
        size, ko, pos = found
        (front if pos == 'front' else back).insert(0, ko)
        words = words[:-size]
        peeled = True
    core = ' '.join(words).strip(' ,')
    if not peeled or not re.search(r'[A-Za-z]{2,}', core):
        return None
    dedupe = lambda items: [k for i, k in enumerate(items) if k and k not in items[:i]]
    return dedupe(front), core, dedupe(back)


def join_markers(front: list[str], core_ko: str, back: list[str]) -> str:
    core_ko = core_ko.strip()
    if back and back[0] == 'ㅋㅋ':
        core_ko = core_ko.rstrip('.')
    return ' '.join(part for part in (*front, core_ko, *back) if part)


# ------------------------------------------------------- exact core sentences
_BUFFS = {'hb': '하이퍼 바디', 'hs': '홀리 심볼', 'se': '샤프 아이즈', 'haste': '헤이스트',
          'mw': '메이플 용사', 'bless': '블레스', 'heal': '힐', 'door': '미스틱 도어'}
_JOB_N = {'1st': '1', 'first': '1', '2nd': '2', 'second': '2',
          '3rd': '3', 'third': '3', '4th': '4', 'fourth': '4'}
_SENTENCES = (
    (r"(?:i |i just )?(?:got |keep )?(?:dc'?d|dced|d/c'?d|dc|disconnected)", '튕겼어'),
    (r"(?:i |i just )?(?:got |keep )?(?:dc'?d|dced|d/c'?d|dc|disconnected) again", '또 튕겼어'),
    (r"(?:i )?(?:got |just got )?(?:ks'?e?d|kill ?stole|kill ?stolen)", '스틸당했어'),
    (r"(?:i )?(?:got |just got )?(?:ks'?e?d|kill ?stole|kill ?stolen) again", '또 스틸당했어'),
    (r"(?:pls |plz |please )?(?:stop|dont|don't|no) ks(?:ing)?(?: me)?(?: pls| plz| please)?", '스틸하지 마세요'),
    (r'(?:ding|dinged|lvl ?up|leveled up|level up|lvled)', '레벨업!'),
    (r"(?:(?:i |i'll |ill |i will |im |i'm |gonna |going to |gotta |will |brb )?(?:go |be )?afk)"
     r"(?: for a (?:bit|sec|second|while|min|minute|few))?", '잠깐 잠수할게'),
    (r'where (?:do|can|should) i (?:get|do|take|make) (?:my |the )?(1st|2nd|3rd|4th|first|second|third|fourth) job(?: adv(?:ancement)?)?',
     lambda m: _JOB_N[m.group(1).casefold()]+'차 전직 어디서 해요?'),
    (r'(?:any ?one|any1|some ?one|some1|can (?:any ?one|any1|some ?one|some1)) (?:pls |plz )?(hb|hs|se|haste|mw|bless|heal|door)(?: me)?(?: pls| plz| please)?',
     lambda m: f'누가 {_BUFFS[m.group(1).casefold()]} 좀 주세요'),
    (r'(?:need|want) (hb|hs|se|haste|mw|bless|door)(?: pls| plz| please)?',
     lambda m: f'{_BUFFS[m.group(1).casefold()]} 필요해요'),
    (r'(?:ty|thx|thanks|thank you) (?:for|4) (?:the )?(?:buff|buffs|hb|hs|se|haste)', '버프 고마워요'),
    (r'(?:ty|thx|thanks|thank you) (?:for|4) (?:the )?(?:help)', '도와줘서 고마워요'),
    # 'leech' in Maple = getting EXP carried by a stronger player (쩔).
    (r"(?:pls |plz )?(?:dont|don't|do not|no) leech(?:ing)? (?:ur|your|ya) (?:friends?|buddies|guildies)",
     '친구한테 쩔 받지 마세요'),
    (r"(?:pls |plz )?(?:dont|don't|do not|no) leech(?:ing)?(?: here| pls| plz| please)?", '쩔 받지 마세요'),
    (r'(?:anyone |any1 |someone )?(?:can |could )?(?:give |gimme )?(?:me )?(?:a )?leech(?: me)?(?: pls| plz| please)?\??',
     '쩔 해줄 분 있나요?'),
    (r'(?:selling|s>?) ?leech(?:es|ing)?', '쩔 팝니다'),
    (r'(?:lowkey|kinda|kind of) (?:wanna|want to|gonna) quit', '은근 접고 싶어'),
    (r'(?:i )?(?:wanna|want to|gonna|going to) quit', '접고 싶어'),
)
_SENTENCE_RES = tuple((re.compile(r'(?i)^(?:'+p+r')$'), ko) for p, ko in _SENTENCES)


def slang_sentence(text: str) -> str | None:
    value = re.sub(r'\s+', ' ', text.strip()).strip(_PUNCT)
    if not value or _TRADE.search(value) or '[' in value:
        return None
    for regex, ko in _SENTENCE_RES:
        match = regex.match(value)
        if match:
            return ko(match) if callable(ko) else ko
    return None


# ------------------------------------------------- 2. expansion before MT
_VERB = (r'(?:do|go|be|get|try|give|buy|sell|help|wait|come|check|pay|take|make|see|'
         r'join|hunt|train|run|need|log|brb|invite|inv|trade|send|msg|pm|dm|tell|let|join)')
_RULES = (
    # a bare "wanna quit" has no subject; the MT model needs one
    (r'^(?:wanna|want to)\b', 'I kind of want to'),
    (r'^(?:need to|have to|gotta|gonna|going to)\b', lambda m: 'I ' + m.group().replace('gotta', 'have to').replace('gonna', 'am going to')),
    # pronouns and verbs
    (r"\bur\s+(?=(?:welcome|right|so|too|the|not|gonna|going|being|a)\b)", 'you are '),
    (r'\bur\b', 'your'),
    (r'\br\s+(u|you|we|they|ppl|people)\b', r'are \1'),
    (r'\b(u|you|we|they|ppl|people|these|those|there|where|how|what|who|mobs|prices)\s+r\b', r'\1 are'),
    (r'(?<![/\w])u(?![/\w])', 'you'),
    (r"\by'?all\b", 'you all'),
    (r'\bya\b(?=\s+(?:know|guys|all)\b)', 'you'),
    (r'\bim\b', 'I am'), (r"(?<=[!?.]\s)i'?m\b", 'I am'), (r'\bive\b', 'I have'), (r'\bid\b(?=\s+(?:like|love|rather)\b)', 'I would'),
    (r'\bill\s+(?='+_VERB+r'\b)', 'I will '),
    (r'\bdont\b', 'do not'), (r'\bcant\b', 'cannot'), (r'\bwont\b', 'will not'),
    (r'\bdidnt\b', 'did not'), (r'\bdoesnt\b', 'does not'), (r'\bisnt\b', 'is not'),
    (r'\bwasnt\b', 'was not'), (r'\barent\b', 'are not'), (r'\bhavent\b', 'have not'),
    (r'\bcouldnt\b', 'could not'), (r'\bshouldnt\b', 'should not'), (r'\bwouldnt\b', 'would not'),
    (r'\byoure\b', 'you are'), (r'\btheyre\b', 'they are'), (r'\bthats\b', 'that is'),
    (r'\bwhats\b', 'what is'), (r'\bwheres\b', 'where is'), (r'\bhows\b', 'how is'),
    (r'\btheres\b', 'there is'),
    # time / connectives
    (r'\b(?:tmrw|tmr|tmrow|tomoz|2moro|2morrow)\b', 'tomorrow'),
    (r'\b2day\b', 'today'), (r'\b(?:2nite|2night|tn)\b', 'tonight'), (r'\bb4\b', 'before'),
    (r'\babt\b', 'about'), (r'\b(?:prob|probs|prolly)\b', 'probably'),
    (r'\b(?:rly|rlly|rlly)\b', 'really'), (r'\bsrsly\b', 'seriously'),
    (r'\b(?:cuz|coz|cos|bc|bcuz|bcoz|bcos)\b', 'because'), (r'\btho\b', 'though'),
    (r'\bthru\b', 'through'), (r'\b(?:wat|wut|wht)\b', 'what'),
    (r'\bdunno\b', 'I do not know'), (r'\bgimme\b', 'give me'), (r'\blemme\b', 'let me'),
    (r'\bsorta\b', 'sort of'), (r'\bofc\b', 'of course'), (r'\b(?:obv|obvs)\b', 'obviously'),
    (r'\bik\b', 'I know'), (r'\bw/o\b', 'without'), (r'\bw/', 'with '),
    (r'\bw\s+(?=(?:you|me|us|them|my|your|him|her)\b)', 'with '),
    (r'\b(thanks|thank you|thx|ty|good|ready|waiting|looking)\s+4\b', r'\1 for'),
    (r'\b(?:dm|pm|msg)\s+me\b', 'message me'), (r'\bhmu\b', 'contact me'),
    # game actions
    (r"\b(?:dc'?d|dced|d/c'?d)\b", 'disconnected'),
    (r'\b(got|keep|kept|i)\s+dc\b', r'\1 disconnected'),
    (r"\b(?:ks'?e?d)\b", 'kill-stolen'), (r'\bks-?ing\b', 'stealing monsters'),
    (r'\b(gonna|going to|will|gotta|to|ill)\s+afk\b', r'\1 be away'), (r'\bafk\b', 'away'),
    (r'\blf(?=\s+[a-z])', 'looking for'), (r'\blfm\b', 'looking for more members for'),
    (r'\b(?:exp|xp)\b', 'EXP'), (r'\b(?:lvl|lv)\b', 'level'), (r'\bdmg\b', 'damage'),
    (r'\bpots\b', 'potions'), (r'\bpot\b(?=\s+(?:pls|plz)\b)', 'potion'),
    (r'\b(so|too|very|really|super|pretty)\s+op\b', r'\1 strong'), (r'\bop\b', 'too strong'),
    (r'\bdrop rate', 'item drop rate'), (r'\bfor a (?:bit|sec|second|min)\b', 'for a while'),
    (r'\b(before|after|pre|post)[\s-]?bb\b', r'\1 the Big Bang update'),
    (r'\b(str|dex|int|luk)\b', lambda m: m.group().upper()),
    (r'\bhpq\b', 'Henesys party quest'), (r'\bpac\b', 'Pink Adventurer Cape'),
    (r'\bcs\b(?=\s+(?:worth|pass|passed|fail|failed|boom|boomed)\b)', 'Chaos Scroll'),
    (r'\b(is|are|was)\s+cs\b', r'\1 Chaos Scroll'),(r'\bgoated\b', 'the best'), (r'\bez\b', 'easy'),
    (r'\b(?:noob|nub|newb|n00b|noobs|nubs)\b', 'beginner'),
    (r'\b(train|training|grind|grinding)\s+(?=(?:at|in|on|near)\b)',
     lambda m: 'hunting ' if m.group(1).casefold().endswith('ing') else 'hunt '),
    (r'\bwhere\s+(to|should i|do i|do you|can i|should we|do we)\s+(?:train|grind)\b', r'where \1 hunt'),
    (r'\b(?:grinding)\b', 'hunting'),
    # places
    (r'\b(?:hene|henny|henes)\b', 'Henesys'), (r'\b(?:elli|ellin|elina)\b', 'Ellinia'),
    (r'\bperi\b', 'Perion'), (r'\b(?:kc|kerning)\b(?!\s*(?:pq|party))', 'Kerning City'),
    (r'\bludi\b(?!\s*pq)', 'Ludibrium'), (r'\bnath\b', 'El Nath'),
    (r'\b(at|in|to|from|near)\s+sleepy\b', r'\1 Sleepywood'), (r'\blith\b', 'Lith Harbor'),
    (r'\b(at|in|to|from|train|hunt|duo|solo)\s+gs\b', r'\1 Ghost Ship'),
    # bosses
    (r'\b(?:zak|zk|zakum)\b', 'Zakum'), (r'\bht\b(?!\s*(?:p|n|pq)\b)', 'Horntail'),
    (r'\bpap\b', 'Papulatus'), (r'\bpb\b', 'Pink Bean'), (r'\bcrog\b', 'Crimson Balrog'),
    (r'\bjrog\b', 'Jr. Balrog'),
    # jobs
    (r'\bsins\b', 'Assassins'), (r'\bsin\b', 'Assassin'), (r'\bdits\b', 'Bandits'),
    (r'\bdit\b', 'Bandit'), (r'\bnl\b', 'Night Lord'), (r'\bshad\b', 'Shadower'),
    (r'\b(?:dk|drk)\b', 'Dark Knight'), (r'\bfp\b', 'Fire/Poison mage'),
    (r'\bbucc\b', 'Buccaneer'), (r'\bsair\b', 'Corsair'), (r'\b(?:pally|pala)\b', 'Paladin'),
    (r'\b(?:bish|bishy)\b', 'Bishop'), (r'\bsader\b', 'Crusader'), (r'\bxbow(?:man)?\b', 'Crossbowman'),
    # buffs / skills
    (r'\bhs\b', 'Holy Symbol'), (r'\bse\b', 'Sharp Eyes'), (r'\bhb\b', 'Hyper Body'),
    (r'\bmw\b', 'Maple Warrior'), (r'\btele\b', 'Teleport'), (r'\bfj\b', 'Flash Jump'),
    # items
    (r'\bws\b', 'White Scroll'),
    (r'\bcs\b(?=\s+(?:on|it|them|this|that|my|your)\b)', 'Chaos Scroll'),
    (r'\b(a|my|use|using|used|failed|passed|bought)\s+cs\b', r'\1 Chaos Scroll'),
    (r'\b(in|from|at)\s+(the\s+)?cs\b', r'\1 \2Cash Shop'),
    (r'\bcs\b(?=\s+(?:sale|items?|shop)\b)', 'Cash Shop'),
    (r'\bbwg\b', 'Brown Work Gloves'), (r'\b(?:ilbis|ilbi)\b', 'Ilbi throwing stars'),
    (r'\bsubis?\b', 'Subi throwing stars'), (r'\bnx\b', 'NX'),
)
_RULE_RES = tuple((re.compile(p, re.I), r) for p, r in _RULES)
_PROTECTED = re.compile(r'(\[[^\]]*\]|\d+(?:[.,]\d+)*\s*%|\b(?:STR|DEX|INT|LUK)\b)')


def expand_slang(text: str) -> str:
    """Spell out shorthand in plain English for the MT model."""
    if _TRADE.search(text):
        return text
    parts = _PROTECTED.split(text)
    for i in range(0, len(parts), 2):
        value = parts[i]
        for regex, replacement in _RULE_RES:
            value = regex.sub(replacement, value)
        parts[i] = value
    return re.sub(r'\s{2,}', ' ', ''.join(parts)).strip()


# --------------------------------------------- 3. Korean names after MT
_NAMES = (
    ('Kerning City', '커닝시티'), ('Lith Harbor', '리스항구'), ('El Nath', '엘나스'),
    ('Victoria Island', '빅토리아 아일랜드'), ('Free Market', '자유시장'),
    ('Ghost Ship', '유령선'), ('Pink Bean', '핑크빈'), ('Crimson Balrog', '크림슨 발록'),
    ('Jr. Balrog', '주니어 발록'), ('Jr Balrog', '주니어 발록'), ('Night Lord', '나이트로드'),
    ('Dark Knight', '다크나이트'), ('Hyper Body', '하이퍼 바디'), ('Holy Symbol', '홀리 심볼'),
    ('Sharp Eyes', '샤프 아이즈'), ('Maple Warrior', '메이플 용사'), ('Flash Jump', '플래시 점프'),
    ('White Scroll', '백의 주문서'), ('Chaos Scroll', '혼돈의 주문서'), ('Cash Shop', '캐시샵'),
    ('Brown Work Gloves', '갈색 목장갑'), ('Ilbi', '일비 표창'), ('Subi', '수비 표창'),
    ('Henesys', '헤네시스'), ('Ellinia', '엘리니아'), ('Perion', '페리온'),
    ('Sleepywood', '슬리피우드'), ('Orbis', '오르비스'), ('Ludibrium', '루디브리엄'),
    ('Leafre', '리프레'), ('Zakum', '자쿰'), ('Horntail', '혼테일'), ('Papulatus', '파풀라투스'),
    ('Mushmom', '머쉬맘'), ('Assassins', '표도'), ('Assassin', '표도'), ('Bandits', '시프'),
    ('Bandit', '시프'), ('Shadower', '섀도어'), ('Bishop', '비숍'), ('Paladin', '팔라딘'),
    ('Buccaneer', '바이퍼'), ('Corsair', '캡틴'), ('Crusader', '크루세이더'),
    ('Crossbowman', '사수'), ('Cleric', '클레릭'), ('Priest', '프리스트'),
    ('Teleport', '텔레포트'), ('leeching', '쩔 받기'), ('leech', '쩔'),
    ('mesos', '메소'), ('meso', '메소'), ('NX', '캐시'),
    ('Henesys party quest', '헤네 파퀘'), ('Kerning City party quest', '커닝 파퀘'),
    ('Ludibrium party quest', '루디 파퀘'), ('Orbis party quest', '오르비스 파퀘'),
    ('party quest', '파티 퀘스트'), ('Big Bang Update', '빅뱅 업데이트'), ('Big Bang', '빅뱅'),
    ('Chaos Scroll', '혼돈의 주문서'), ('Maple', '메이플'),
)
# Longest first so "Maple Warrior" wins over "Maple".
_NAME_RE = re.compile(r'(?i)(?<![A-Za-z])(' + '|'.join(
    re.escape(e) for e, _ in sorted(_NAMES, key=lambda n: -len(n[0]))) + r')(?![A-Za-z])')
_NAME_KO = {e.casefold(): k for e, k in _NAMES}
# Half-translated forms the MT model produces for names it partly knows.
_KO_FIXES = (
    (re.compile(r'(헤네시스|헤네)\s*(?:Party|파티)\s*퀘스트'), '헤네 파퀘'),
    (re.compile(r'(커닝시티|커닝)\s*(?:Party|파티)\s*퀘스트'), '커닝 파퀘'),
    (re.compile(r'(루디브리엄|루디)\s*(?:Party|파티)\s*퀘스트'), '루디 파퀘'),
    (re.compile(r'오르비스\s*(?:Party|파티)\s*퀘스트'), '오르비스 파퀘'),
    (re.compile(r'Party\s*퀘스트'), '파티 퀘스트'),
    (re.compile(r'작업\s*장갑'), '목장갑'),
    (re.compile(r'하락\s*비율'), '드롭률'), (re.compile(r'아이템\s*드롭\s*비율'), '드롭률'),
)


_PAIRS = {'은': ('은', '는'), '는': ('은', '는'), '이': ('이', '가'), '가': ('이', '가'),
          '을': ('을', '를'), '를': ('을', '를')}
_KO_NAMES = sorted({k for _, k in _NAMES}, key=len, reverse=True)
_PARTICLE_RE = re.compile('(' + '|'.join(map(re.escape, _KO_NAMES)) + r')([은는이가을를])(?![가-힣])')


def _fix_particle(match: re.Match) -> str:
    """Match 은/는, 이/가, 을/를 to the Korean name's final consonant."""
    name, particle = match.groups()
    last = name[-1]
    has_final = '가' <= last <= '힣' and (ord(last) - 0xAC00) % 28 != 0
    with_final, without = _PAIRS[particle]
    return name + (with_final if has_final else without)


def koreanize_names(text: str) -> str:
    """Swap English game names MT left in a Korean result; skip [item links]."""
    if not re.search('[가-힣]', text):
        return text
    parts = re.split(r'(\[[^\]]*\])', text)
    for i in range(0, len(parts), 2):
        value = _NAME_RE.sub(lambda m: _NAME_KO[m.group(1).casefold()], parts[i])
        value = _PARTICLE_RE.sub(_fix_particle, value)
        for regex, replacement in _KO_FIXES:
            value = regex.sub(replacement, value)
        parts[i] = value
    return ''.join(parts)
