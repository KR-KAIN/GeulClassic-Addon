"""Clean real Free Market chat before translation (R15, from live logs).

Three things seen thousands of times in the user's 2026-10-27 chat history:
1. '@@@@' and '~~~~' spam runs, often with OCR crumbs ('c', 'Q', '②', '3m')
   inside or after them. They were copied into translations and the crumbs
   became fake prices ("@@@@3m" -> "가격 300만 메소").
2. A small set of OCR misspellings of very common market words
   ('lron ore', 'WHITEF OTION', 'nure water', 'scrols').
3. Party posts: J>PQ, JPQ, I>pq (J read as I), R>1 SUPER RUSH 30+.
   The sentence model turned these into '가입을 찾고' or 'IP 주소'.
"""
from __future__ import annotations
import re

# A spam run starts with two '@' and swallows the symbols, spaces and
# single OCR crumbs that appear inside it.
_SPAM_RUN = re.compile(r'@{2,}(?:[@\s②③④①⑤⑥∂©€éΦσα#$!~_.,\-\]\[|]|[A-Za-z0-9](?=[@②③④∂]))*')
_REPEAT_SYMBOLS = re.compile(r'[~_]{4,}|[#$]{3,}[#$\s]*')
_HAN = re.compile(r'[㐀-鿿]')


def clean_spam(text: str) -> str:
    """Remove decoration spam; keep real words around it."""
    if not text:
        return text
    value = text
    value = re.sub(r'[\$§]\s*>', 'S>', value)
    value = re.sub(r'(?<=\d)\s+@\d{1,3}\s*$', '', value)        # '700 @12' (a spam counter)
    if '@@' in value:
        value = re.sub(r'(?<=[a-z]{2})[QC](?=@@)', '', value)   # 'BonusQ@@@' (never 'RusH@@')
        value = re.sub(r'(?<=\s)[QCG](?=@@)', '', value)          # 'items C@@@'
        value = re.sub(r'@[A-Za-z0-9②③④Φ]{0,3}(?=@@)', '', value)   # 'IPo@e@@@', 'RusH@q2c@@', '60% @2@@'
        value = re.sub(r'[②③④①⑤⑥∂©Φ]+(?=@@)', '', value)
        parts = _SPAM_RUN.split(value)
        kept = []
        for index, part in enumerate(parts):
            if index > 0:
                stripped = part.strip()
                # Crumbs between or after runs ('c', 'QQ', '3m', 'a', '②')
                # are OCR noise, not a price or a word.
                if len(stripped) <= 3 and ' ' not in stripped:
                    continue
                if re.fullmatch(r'[\d\s?]{1,10}', stripped):
                    continue      # '22 22222' / '??2'
                # 'aaaa', 'aa@aa' - repeated crumb letters, never a word
                if re.fullmatch(r'[aceoQGCOΦ②③④①⑤⑥∂©@\s]+', stripped):
                    continue
                if (re.fullmatch(r'[aceoQGCOΦ②③④①⑤⑥∂©@\s0-9]+', stripped)
                        and re.search(r'[QGCΦ②③④@]', stripped)):
                    continue      # '2Q', 'Q0', 'QQ@C2'
                if '@' in stripped and not re.search(r'[A-Za-z]{3,}', stripped):
                    continue    # 'mb@aa@a'
            kept.append(part)
        value = ' '.join(p.strip() for p in kept if p.strip())
    # '@G@QGGQ@Φ@ @Q' left before a run: single '@' with OCR crumbs between
    # (crumb letters only, never the start of a real word such as 'White')
    if value.count('@') >= 3:
        value = re.sub(r'(?:@[QGCOoce0-9Φ②③④∂©]{0,4}(?![A-Za-z])\s?){3,}@?', ' ', value).strip()
    if '@@' in text:
        # crumbs left at the end of a spam line ('pet speed 60% Q0 Q')
        value = re.sub(r'(?:\s+(?=\S*[QGC])[QGCO0-9]{1,2})+\s*$', '', value)
    # a lone '@' means 'at' a price: 'BLUE POTS @ 150 EA'
    value = re.sub(r'(?<=\s)@\s*(?=\d{2,})', '', value)
    # OCR crumbs of the spam run left at the end ('SIN ②', 'SIN ②C')
    value = re.sub(r'(?:\s+[②③④①⑤⑥∂©][A-Za-z②③④①⑤⑥∂©]{0,2})+\s*$', '', value)
    value = _REPEAT_SYMBOLS.sub(' ', value)
    value = re.sub(r'(?:[+&%#!*()^@±|$~<>=\\/]\s?[0-9A-Za-z]?){7,}',
                   lambda m: ' ' if len(set(re.sub(r'[\sA-Za-z0-9]', '', m.group()))) >= 4 else m.group(), value)
    # '44444555555666666': keyboard-mash digits, never a price.
    value = re.sub(r'(?<![\w.,])\d{8,}(?![\w.,])', ' ', value)
    # OCR of another line's Hangul/Han glyphs glued after English text.
    if _HAN.search(value) and len(re.findall(r'[A-Za-z]{2,}', value)) >= 2:
        # ...but an item label's ']' glued to such a glyph stays ('[DIC 号]')
        value = ' '.join(tok if not _HAN.search(tok) else re.sub(r'[^\[\]]', '', tok)
                         for tok in value.split())
        value = re.sub(r'\s+\]', ']', value)
    value = re.sub(r'\s{2,}', ' ', value).strip()
    return value or text.strip()


_OCR_WORDS = [
    # R16 live chat: 'KPQ RUSH' read as 'KPToRusH'; a price split '2. 7m'
    (re.compile(r'\bKPTo\s*Rush\b', re.I), lambda m: 'KPQ RUSH'),
    (re.compile(r'(?<![\d.])(\d)\.\s+(\d)\s*([kKmM])\b'), lambda m: f'{m.group(1)}.{m.group(2)}{m.group(3)}'),
    # market shorthand the model misreads ('Crit 2' became '팟캐스트')
    (re.compile(r'\bwgs?\b', re.I), lambda m: 'work gloves'),
    # glossary: 'OA STR' = Overall Armor STR scroll, 'ear INT' = earring INT
    (re.compile(r'\bO\.?A\b(?=\s*(?:STR|DEX|INT|LUK)\b)', re.I), lambda m: 'Overall'),
    (re.compile(r'\bear\b(?=\s*(?:STR|DEX|INT|LUK)\b)', re.I), lambda m: 'Earring'),
    (re.compile(r'\b(white|blue|red|orange)f?\s*(?:[pn]\s*)?[oô0]t?i[o0]n(s)?\b', re.I),
     lambda m: f'{m.group(1)} potion{m.group(2) or ""}'),
    (re.compile(r'\b(white|blue|red|orange)\s+p\b(?=\s*[\d,~])', re.I),
     lambda m: f'{m.group(1)} potion'),
    (re.compile(r'\b(white|blue|red|orange|mana)\s*pots?(?![A-Za-z])', re.I),
     lambda m: f'{m.group(1)} potion '),
    (re.compile(r'\bB(?=[pn]ur[eé]\s*water)', re.I), lambda m: 'B> '),
    (re.compile(r'\b[pn]ur[eé]\s*water\b', re.I), lambda m: 'pure water'),
    (re.compile(r'\buna[qgo][il1](?![A-Za-z])', re.I), lambda m: 'unagi '),
    (re.compile(r'\bpui?re\s*water', re.I), lambda m: 'pure water '),
    (re.compile(r'\blron\b'), lambda m: 'iron'),
    (re.compile(r'\b(?:eadh|eacn|eaoh)\b', re.I), lambda m: 'each'),
    (re.compile(r'\bscrol(s)?\b|\bsrrol+(s|a)?\b', re.I), lambda m: 'scrolls'),
    (re.compile(r'\bltems\b'), lambda m: 'items'),
    (re.compile(r'\bF[ae]uipment\b', re.I), lambda m: 'equipment'),
    (re.compile(r'\b[ef]ar+in[gqo]s\b|\bearinas\b', re.I), lambda m: 'earrings'),
    (re.compile(r'\b[Il][vV][Il]\b(?=\s*\d)'), lambda m: 'lvl'),
]


def repair_ocr_words(text: str) -> str:
    # Non-standard trade markers: 'B- ', 'buy>>', 'sell >' -> 'B>' / 'S>'.
    value = re.sub(r'^\s*(?:buy(?:ing)?\s*>+|B\s*-\s+)', 'B> ', text, flags=re.I)
    value = re.sub(r'^\s*(?:sell(?:ing)?\s*>+|S\s*-\s+)', 'S> ', value, flags=re.I)
    for pattern, repl in _OCR_WORDS:
        value = pattern.sub(repl, value)
    return value


_TRADE_LINE = re.compile(r'^\s*(?:\[[^\]\n]+\]\s*)?(?:[SBTR]\s*[>)]|[SB]X|WT[SBT]\b|sell|buy|selling|buying)'
                         r'|\d\s*[kKmM]\b|\d[kKmM][A-Za-z]|\d\s*%', re.I)


def _split_piece(s: str) -> str:
    # '60%Scrolls' -> '60% Scrolls'
    s = re.sub(r'(\d\s*%)(?=[A-Za-z]|\d+(?:\.\d+)?\s*[kKmM]\b)', r'\1 ', s)
    # '3more', '8more', '2ea'
    s = re.sub(r'(?<![A-Za-z])(\d+)(?=(?:more|ea|each|pcs|sets?|slots?)\b)', r'\1 ', s, flags=re.I)
    # '450keach' / '100krunarius' / '400kwhi' -> price, then the next word
    # ('+8magicatk' is a stat, not 8m)
    s = re.sub(r'(?<![+\d.])(\d+(?:\.\d+)?[kK])(?=[A-Za-z]{2,})', r'\1 ', s)
    s = re.sub(r'(?<=\d)[mM][eE](?:[eE][nNsS]?|[sS][nN]?)\b', ' meso', s)      # '750Meen' / '750Mes'
    s = re.sub(r'(?<![+\d.])(\d+(?:\.\d+)?[mM])(?![iI][lL]|(?i:ore\b|esos?\b|agic|att|atk|ins?\b|e(?!a)))(?=[A-Za-z]{2,})', r'\1 ', s)
    # 'FMchn37' / 'CH37FM17' -> 'FM CH 37' / 'CH 37 FM 17'
    s = re.sub(r'\bFM\s*ch(?:n|annel)?\s*(\d+)', r'FM CH \1', s, flags=re.I)
    s = re.sub(r'(?<![A-Za-z])(CH|FM)(\d+)', r'\1 \2', s, flags=re.I)
    s = re.sub(r'(\d)(?=(?:CH|FM)\s*\d)', r'\1 ', s, flags=re.I)
    # '40kIShieldAc' / '40k I Scrolls': OCR of the '|' item separator
    s = re.sub(r'(?<=\d[kKmM])[I|l](?=[A-Z])', ', ', s)
    s = re.sub(r'(?<=[\dkKmM%)])\s+[I|1]\s+(?=[A-Za-z])', ', ', s)
    s = re.sub(r'\bW\s+(?=(?:INT|DEX|STR|LUK)\b)', '', s)            # 'EARRINGS W INT+2' (with)
    # camelCase glue: 'IronOre' -> 'Iron Ore', '2hAxe' -> '2h Axe'
    s = re.sub(r'(?<=[a-z])(?=[A-Z][a-z])', ' ', s)
    s = re.sub(r'(?<=[A-Z]{2})(?=[A-Z][a-z]{2})', ' ', s)          # 'AVGClean' -> 'AVG Clean'
    s = re.sub(r'(?<=[a-z]{2})(?=[A-Z]{3})', ' ', s)              # 'CleanPANLD' -> 'Clean PANLD'
    # word + number: 'Claw140k', 'water700', 'box11', 'gfa60', 'Skull225k'
    s = re.sub(r'(?<![A-Za-z0-9])([A-Za-z]{3,})(?=\d)', r'\1 ', s)
    s = re.sub(r'(?<=[a-z])([A-Z]{2,})(?=\d)', r' \1', s)
    return s


def split_glued(text: str) -> str:
    """Put spaces back into run-together market posts ('Claw140k Dagger135k').

    Only on trade-looking lines, never inside [linked item] labels or URLs.
    """
    if not text or not _TRADE_LINE.search(text) or re.search(r'https?:|www\.|\.(?:com|gg|net)\b', text, re.I):
        return text
    # 'Player123 : ...' - the nickname before the colon stays as typed
    sender = re.match(r'^([^\s:\[\]]{2,24}\s*:\s*)', text)
    head, body = (sender.group(1), text[sender.end():]) if sender else ('', text)
    parts = re.split(r'(\[[^\[\]\n]+\])', body)
    for i in range(0, len(parts), 2):
        parts[i] = _split_piece(parts[i])
    return head + re.sub(r'[ \t]{2,}', ' ', ''.join(parts)).strip()


_FULL_BRACKETS = str.maketrans({'【': '[', '［': '[', '】': ']', '］': ']'})


def _known_item(name: str) -> bool:
    try:
        from .classic_item_index import current_index
        return name.casefold() in current_index().by_en
    except Exception:
        return False


def repair_link_close(text: str) -> str:
    """'[Angel Halol S>...' -> '[Angel Halo] S>...' for a KNOWN item name.

    The OCR often reads a linked item's closing ']' as l / I / 1 or drops
    it. Only an exact known English item name may be closed; anything else
    is left as typed.
    """
    if '[' not in text:
        return text
    out, pos = [], 0
    for m in re.finditer(r'\[(?![^\[\]]*\])', text):
        start = m.end()
        words = text[start:].split(' ')
        for n in range(min(7, len(words)), 0, -1):
            name = ' '.join(words[:n])
            stripped = re.sub(r'[lI1|)\]]$', '', name)
            for candidate in (name, stripped):
                if len(candidate) >= 4 and _known_item(candidate):
                    end = start+len(name)
                    out.append(text[pos:m.start()]+'['+candidate+']')
                    pos = end
                    break
            else:
                continue
            break
    out.append(text[pos:])
    return ''.join(out)


def prepare_chat(text: str) -> str:
    text = (text or '').translate(_FULL_BRACKETS)
    # ':)' ';D' faces in the middle of a post became a stray ':' (R18)
    text = re.sub(r'(?<=\s)[:;]-?[)(DPp](?=\s|$)', ' ', text)
    text = re.sub(r'(?<=[a-z]{2})([!?])(?=[A-Za-z]{2})', r'\1 ', text)
    from .chat_fixups import clean_crumbs, collapse_repeats, repair_markers, repair_words
    value = repair_link_close(repair_markers(collapse_repeats(clean_crumbs(clean_spam(text)))))
    out = repair_ocr_words(repair_words(split_glued(value)))
    # an OCR fix can reveal the trade verb ('Ruvina' -> 'Buying'): read the
    # markers again so the line splits like a clean one
    if re.match(r'(?i)\s*(?:buy|sell)', out) and not re.match(r'(?i)\s*(?:buy|sell)', value):
        out = repair_markers(out)
    return out


# ---------------------------------------------------------------- party posts
_PQ = {'pq', 'po', 'pa', 'p@', 'rq', 'p0', 'oq', 'pg'}
_RUSH = re.compile(r'^(?:super)?(?:rush+i?|bush|rusi|rus|ruch)$|^superrush$')
_BONUS = re.compile(r'^(?:[bhr][o0]n+[uo]s+t?|bonu|bouns|bonous|ronhs|bonis|bontis|ronis|bonuss+|bon[l1]u?s)$')
_CLASSES = {
    'hunter': '헌터', 'assassin': '어쌔신', 'sin': '어쌔신', 'mage': '마법사',
    'page': '페이지', 'spearman': '스피어맨', 'fighter': '파이터', 'cleric': '클레릭',
    'wizard': '위자드', 'bandit': '시프', 'crossbowman': '사수', 'ranger': '레인저',
    'warrior': '전사', 'thief': '도적', 'bowman': '궁수', 'archer': '궁수',
    'ranged': '원거리', 'melee': '근거리', 'rogue': '도적',
}
_FILLER = {'please', 'pls', 'plz', 'pl', 'pis', 'thanks', 'expert', 'rushers', 'ok', 'thx', 'ty', '&', 'and', 'or', 'me',
           'add', 'inv', 'invite', 'only', 'pro', 'experienced', 'exp', 'fast', 'runs', 'run', 'help', 'helo',
           'stage', 'staae', 'stg', 'in',
           'any', 'all', 'more', 'for', 'map', 'preferred', 'round', 'doing', 'need', 'lf', 'super',
           'norm', 'normal', 'reg', 'regular', 'spot', 'spots', 'snot', 'slot', 'slots', 'j', 'last',
           'l', 'people', 'ppl', 'person', 'persons', 'peeps', 'good', 'be', 'quick', 'pls!',
           'everyone', 'anyone', 'guys'}   # 'Bonus!!l': the OCR reads a '!' as l


_PQ_NAMES = {'hpq': '헤네 파퀘', 'opq': '오르비스 파퀘', 'ppq': '해적 파퀘', 'epq': '엘린 파퀘',
             'gpq': '길드 파퀘', 'apq': '아모리아 파퀘', 'mpq': '마가티아 파퀘', 'cpq': '몬스터 카니발',
             'lmpq': '루디 미로 파퀘', 'zpq': '자쿰 파퀘', 'htpq': '혼테일 파퀘', 'cwkpq': '크림슨우드 파퀘'}


def _tokens(body: str):
    body = body.lower().replace('+', ' + ')
    body = body.replace('±', ' + ')
    body = re.sub(r'(\d)\s*/\s*(\d)', r'\1of\2', body)  # keep '3/4' party size
    body = re.sub(r'[!?.,~^_\-/()\[\]:;*@#<>=|\'"–—’·]+', ' ', body)
    body = re.sub(r'\b([jip1]?p[qo])[qo0]+\b', r'\1', body)
    body = re.sub(r'(?<=pq)(?=[ji]pq)', ' ', body)      # 'jpqjpq'
    # 'PQPQPQPQPPQPQany' / 'papapapappapa' spam of one 'pq'
    body = re.sub(r'\banv\b|\bany{2,}\b', 'any', body)
    body = re.sub(r'\b(?=[pqoa]*p)(?=[pqoa]*[qa])[pqoa]{6,}(an[yv])?\b',
                  lambda m: 'pq' + (' any' if m.group(1) else ''), body)
    body = re.sub(r'\b(bonus|rush)1\b', r'\1', body)   # 'BONUS1' is 'BONUS!'
    body = re.sub(r'\b[ji1](rush|bonus)\b', r'j \1', body)
    return [t for t in body.split() if t and not re.fullmatch(r'[qo0]{3,}|\d+mins?', t)]


def party_post(text: str) -> str | None:
    """Translate a complete party join/recruit post, or return None."""
    value = re.sub(r'\s+', ' ', text).strip()
    # Keep a trailing face ('^_^', '^^', '*_*') as the player wrote it.
    face = re.search(r'\s+([\^*][_^*\s]*[\^*])$', value)
    decoration = ' ' + face.group(1) if face else ''
    if face:
        value = value[:face.start()]
    result = _party_core(value)
    return result + decoration if result is not None else None


def party_split(text: str):
    """('파티 퀘스트 연속 진행 참가 원해요', 'be good') for a party post with a
    few extra words ('J> RUSH PQ BE GOOD'); None when it is not a party post."""
    value = re.sub(r'\s+', ' ', text or '').strip()
    if not re.match(r'^(?:[JjIi1RrNn]\s*[>:<-]|>+\s*\w|[JjIi1]?[KkLlHhOo]?[Pp][QqOo]|[JjIi1]\s+[KkLl]?[Pp][QqOo]|LF\b|lfm\b'
                    r'|(?i:any)\s*[JjIi1]?[KkLl]?[Pp][QqOo]\b|[JjIi1]\)\s*[KkLl]?[Pp][QqOo])', value):
        return None
    res = _party_core(value, tolerant=True)
    if not isinstance(res, tuple):
        return None
    head, extra = res
    extra = [t for t in extra if len(t) > 1 and not re.fullmatch(r'[qocea0-9@]+', t)]
    if len(extra) > 9:
        return None
    return head, ' '.join(extra)


def _party_core(value: str, tolerant: bool = False):
    # R18 live: 'J-pq', 'J-oq!!' (dash for '>') and 'R PQ Bonus' (no '>')
    value = value.lstrip('.,·:;\'"` ')
    lead = re.match(r'(?i)^(lv\.?|lvl)\s*(\d{1,3})\s+(?=[JjIi1]\s*>?\s*[KkLl]?[Pp][QqOo0])', value)
    if lead:
        value = value[lead.end():] + f' lv{lead.group(2)}'
    value = re.sub(r'^([JjIi1Rr])\s*-\s*(?=[A-Za-z])', r'\1>', value)
    value = re.sub(r'^([JjIi1])\s*:\s*(?=[A-Za-z])', r'\1>', value)              # 'J: RUSH'
    value = re.sub(r'^([JjIi1])[.,]\s*(?=[KkLl]?[Pp][QqOo]\b)', r'\1>', value)      # 'J.PQ RUSH'
    value = re.sub(r'^([RrJj])\s*<+\s*', r'\1> ', value)                          # 'R< Bonus PQ', 'J<PQ'
    value = re.sub(r'^[iI]\s+(?=[JjIi]?[Pp][QqOo])', '', value)                     # 'i JPQQQQ'
    value = re.sub(r'^[Rr](?=[Pp][QqOo]\b)', 'K', value)                            # 'RPQ RUSH', 'RPO RUSH'
    value = re.sub(r'^[Dd](?=[Pp][QqOo]\b)', 'J', value)                            # 'DPO honus'
    value = re.sub(r'^([JjIi1])\)\s*(?=[KkLl]?[Pp][QqOo])', r'\1>', value)          # 'J)PQ stage in BONUS'
    value = re.sub(r'^(?i:any)\s*(?=[JjIi1]?[KkLl]?[Pp][QqOo]\b)', 'J> any ', value)  # 'ANY JPQ'
    value = re.sub(r'^[Rr]1\s+(?=(?i:[br]ush|rush)\b)', 'R> ', value)                # 'R1 BUSH MAX HASTE'
    value = re.sub(r'(?i)^join(?:ing)?\s+(?=(?:rush|bonus)\b)', 'J> ', value)          # 'Joining BONUS'
    value = re.sub(r'^>+\s*(?=[A-Za-z]{0,2}[Pp][QqOo]\b)', 'J> ', value)            # '>> KPO'
    value = re.sub(r'^N(?=P[QO]\b)', 'J', value)                                   # 'NPO BONUS'
    value = re.sub(r'^[dD]\s*>(?=\s*(?:(?i:rush)\s+)?[KkLl]?[Pp][QqOo])', 'J>', value)   # 'd>PQ RUSH', 'D>Rush PQ'
    value = re.sub(r'^(?i:join(?:ing)?)\s+(?=[KkLl]?[Pp][QqOo]\b)', 'J> ', value)   # 'Join PQ Bonus'
    value = re.sub(r'^([Pp])([Oo])(?=\s+(?i:rush|bonus)\b)', r'\1Q', value)        # 'PO RUSH'
    value = re.sub(r'^([Rr])\s+(?=[KkLl]?[Pp][QqOo0]\b)', r'\1> ', value)
    m = re.match(r'^(?:([JjIi1])\s*>+|([Rr]|[Bb](?=\s*>+(?i:.*\b(?:rush|bush|bonus|[kl]?pq)\b)))\s*[>)]+|([JjIi1])(?=\s*(?:[KkLlOo]?[Pp][QqOoAaGg0]+|[Pp][Tt])\b|\s*(?i:rush|[bhr]onus)\b)|(LF|lf|Lf|L|l)\s*>+'
                 # R16: a bare 'KPQ RUSH' / 'PQ BONUS' line is a join post too
                 r'|(?=(?:[KkLlHhOoPpEeGgAaMmCcZz]|[Ll][Mm]|[Hh][Tt]|[Cc][Ww][Kk])?[Pp][Qq]\b)'
                 # 'LF KPQ rush' (join) / 'LFM KPQ 3/4', 'need 3 more for KPQ' (recruit)
                 r'|(?:LF|lf|Lf)\s+(?=(?:[KkLlHhOoPpEeGgAaMmCcZz]|[Ll][Mm]|[Hh][Tt]|[Cc][Ww][Kk])?[Pp][Qq]\b)|([Ll][Ff][1-5]?[Mm]|[Nn]eed)\s+(?=.*\b(?:(?:[KkLlHhOoPpEeGgAaMmCcZz]|[Ll][Mm]|[Hh][Tt]|[Cc][Ww][Kk])?[Pp][Qq]|(?i:rush|bonus))\b))\s*(.*)$', value)
    if not m:
        return None
    recruit = bool(m.group(2) or m.group(5))
    lfm_style = bool(m.group(5)) or bool(re.search(r'\blf\d?m\b', value, re.I))
    body = m.group(6)
    if m.group(3):
        body = body  # 'JPQ ...': the J was the join marker
    tokens = _tokens(body)
    if not tokens:
        return None
    lead_count = re.match(r'(?i)lf([1-5])m', m.group(5) or '')
    target = None
    rush = bonus = False
    level = None
    level_plus = False
    count = int(lead_count.group(1)) if lead_count else None
    progress = None
    roles = []
    invite = only = skilled = fast = anywhere = normal = False
    no_trolls = False
    extra: list[str] = []
    extra_notes: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ''
        if t in _PQ or t in {'jpq', 'ipq', 'ipo', 'ipa', 'jpa', 'jpo', 'ipg', 'jpg'}:
            target = target or 'pq'
        elif t in {'kpq', 'kpo', 'rpq', 'kpa'}:
            target = 'kpq'
        elif t in _PQ_NAMES:
            target = t
        elif t == 'lpq':
            target = 'lpq'
        elif t in {'pt', 'party'}:
            target = target or 'pt'
        elif re.fullmatch(r'(?:pq|po)(rush|bonus)', t):
            target = target or 'pq'
            rush = rush or t.endswith('rush')
            bonus = bonus or t.endswith('bonus')
        elif _RUSH.match(t):
            rush = True
        elif _BONUS.match(t):
            bonus = True
        elif t in {'lv', 'lvl', 'level', 'iv', 'lyl', 'im', 'm', 'mvl', 'iyh', 'lyh', 'lvh', 'v'} and re.fullmatch(r'\d{1,3}', nxt):
            level = int(nxt)
            i += 1
            if i + 1 < len(tokens) and tokens[i + 1] == '+':          # 'lvl 30+'
                level_plus = True
                i += 1
        elif re.fullmatch(r'(?:lv|lvl|lm|im|lyl|iv|ivl|v)(\d{1,3})', t):
            level = int(re.fullmatch(r'\D+(\d+)', t).group(1))
            if nxt == '+':                                              # 'LV25+'
                level_plus = True
                i += 1
        elif re.fullmatch(r'(\d{1,3})(?:lv|lvl)', t):
            level = int(re.match(r'\d+', t).group())
        elif re.fullmatch(r'\d{1,3}', t):
            n = int(t)
            if nxt == '+' or (i > 0 and tokens[i - 1] == '+'):
                level, level_plus = n, True
                if nxt == '+':
                    i += 1
            elif re.fullmatch(r'\d', t) and re.fullmatch(r'\d', nxt or 'x') is None and n <= 5 and recruit:
                count = n
            elif re.fullmatch(r'\d', t) and nxt == 'more':
                count = n
            elif 10 <= n <= 200:
                level = n
            elif n <= 5:
                count = n
            else:
                return None
        elif re.fullmatch(r'(\d{1,3})\+', t):
            level, level_plus = int(t[:-1]), True
        elif re.fullmatch(r'lf([1-5])m', t):
            recruit, count = True, int(t[2])
        elif t == 'lfm':
            recruit = True
        elif re.fullmatch(r'[1-5]of[2-6]', t):
            progress = t.replace('of', '/')
        elif t == '+':
            pass
        elif t == 'no' and nxt in {'troll', 'trolls', 'trolling', 'afk', 'leech', 'leechers', 'leeches'}:
            no_trolls = True
            i += 1
        elif t == 'no' and nxt == 'low' and i + 2 < len(tokens) and tokens[i + 2] in {'level', 'levels', 'lvl', 'lvls', 'lv'}:
            extra_notes.append('저레벨 사절')
            i += 2
        elif re.fullmatch(r'\d{1,2}', t) and nxt in {'minute', 'minutes', 'min', 'mins'}:
            extra_notes.append(f'{t}분 컷')
            i += 1
        elif t == 'we' and nxt == 'are' and i + 2 < len(tokens) and re.fullmatch(r'\d', tokens[i + 2]):
            extra_notes.append(f'현재 {tokens[i + 2]}명')
            i += 2
        elif t == 'on' and nxt == 'discord':
            extra_notes.append('디스코드')
            i += 1
        elif t == 'funded':
            extra_notes.append('풀템')
        elif t == 'haste' or (t in {'with', 'max', 'w'} and nxt == 'haste'):
            if '헤이스트 있음' not in extra_notes:
                extra_notes.append('헤이스트 있음')
            if t != 'haste':
                i += 1
        elif t in _CLASSES:
            roles.append(_CLASSES[t])
        elif re.fullmatch(r'(\d{1,3})(' + '|'.join(_CLASSES) + ')', t):
            mm = re.fullmatch(r'(\d{1,3})([a-z]+)', t)
            level = int(mm.group(1))
            roles.append(_CLASSES[mm.group(2)])
        elif t in _FILLER:
            invite = invite or t in {'inv', 'invite', 'add'}
            only = only or t == 'only'
            skilled = skilled or t in {'pro', 'experienced'}
            fast = fast or t == 'fast'
            anywhere = anywhere or t in {'any', 'all'}
            normal = normal or t in {'norm', 'normal', 'reg', 'regular'}
            if t == 'last':
                count = count or 1
        else:
            if not tolerant:
                return None
            extra.append(t)
        i += 1
    if not (target or rush or bonus):
        return None
    if roles and not (target or rush or bonus):
        return None
    name = {'pq': '파티 퀘스트', 'kpq': '커닝 파퀘', 'lpq': '루디 파퀘', 'pt': '파티',
            None: '파티 퀘스트', **_PQ_NAMES}[target]
    mode = []
    if rush:
        mode.append('연속 진행' + (' 또는 일반 진행' if normal else ''))
    elif normal:
        mode.append('일반 진행')
    if bonus:
        mode.append('보너스 구간')
    head = name + (' ' + '/'.join(mode) if mode else '')
    notes = []
    if level is not None:
        notes.append(f'{level}레벨' + (' 이상' if level_plus else ''))
    if roles:
        notes.append(' '.join(dict.fromkeys(roles)) + (' 만' if only else ''))
    elif only and level_plus:
        notes[-1] += '만'
    if skilled:
        notes.append('숙련자')
    if fast:
        notes.append('빠르게')
    if anywhere and not recruit:
        notes.append('아무 파티나')
    if progress:
        notes.append(f'현재 {progress}')
    if no_trolls:
        notes.append('트롤 사절')
    notes.extend(extra_notes)
    tail = f' ({", ".join(notes)})' if notes else ''
    if recruit:
        who = f' {count}명' if count else ''
        verb = '구해요' if lfm_style else '모집해요'
        out = f'{head}{who} {verb}{tail}'
    else:
        out = f'{head} 참가 원해요{tail}' + (' · 초대해 주세요' if invite else '')
    if tolerant:
        return (out, extra) if extra else out
    return out


def recruit_as_buy(text: str) -> str:
    """'R>' followed by an item price is OCR of 'B>' (buy), not recruiting.

    Only called after party_post() found no party post in the line.
    """
    m = re.match(r'^\s*R\s*[>)]\s*(.+)$', text)
    if m and re.search(r'\d+(?:\.\d+)?\s*[kKmM]\b|\b(?:ea|each)\b|\d+\s*(?:ea|each|mesos?)\b', m.group(1), re.I):
        return 'B> ' + m.group(1)
    if m and re.search(r'(?i)\b(?:nx\s+)?items?\b|\bscrolls?\b|\bpotions?\b|\bpots?\b|\b(?:shoes?|gloves?|hats?|helm(?:et)?s?|'
                       r'earrings?|capes?|overalls?|tops?|bottoms?|pants|shields?|claws?|wands?|staffs?|xbows?|crossbows?|'
                       r'daggers?|spears?|polearms?|masks?|rings?|wings?|pure\s*water|unagis?|elixirs?|ores?)\b', m.group(1)) \
            and not re.search(r'(?i)\b[kl]?pq\b|\brush\b|\bbonus\b|\bpt\b', m.group(1)):
        return 'B> ' + m.group(1)
    return text


# ------------------------------------------------- leftover English vocabulary
_ITEM_WORDS = [
    (r'mana elix(?:irs?|ers?)?', '마나 엘릭서'), (r'power elix(?:irs?|ers?)?', '파워 엘릭서'),
    (r'elix(?:irs?|ers?)?', '엘릭서'),
    (r'hp pots?', 'HP 물약'), (r'mp pots?', 'MP 물약'),
    (r'warrior pots?|warrior potions?', '전사의 물약'), (r'magician pots?|magician potions?', '마법사의 물약'),
    (r'white potions?|white pots?', '하얀 포션'), (r'blue potions?|blue pots?|blue po', '파란 포션'),
    (r'red potions?', '빨간 포션'), (r'orange potions?', '주황 포션'),
    (r'unagis?', '장어구이'), (r'iron ores?', '철 원석'), (r'mithril ores?', '미스릴의 원석'),
    (r'bronze ores?', '청동의 원석'), (r'adamantium ores?', '아다만티움의 원석'), (r'silver ores?', '은의 원석'),
    (r'orihalcon ores?', '오리할콘의 원석'), (r'gold ores?', '금의 원석'), (r'garnet ores?', '가넷의 원석'),
    (r'amethyst ores?', '자수정의 원석'), (r'aquamarine ores?', '아쿠아마린의 원석'), (r'emerald ores?', '에메랄드의 원석'),
    (r'opal ores?', '오팔의 원석'), (r'sapphire ores?', '사파이어의 원석'), (r'topaz ores?', '토파즈의 원석'),
    (r'black crystal ores?', '흑수정의 원석'), (r'bazlud', '베즐러드'), (r'pig ribbons?', '돼지의 리본'),
    (r'sauna(?:\s+robes?)?', '사우나 가운'), (r'mithril pole ?arms?', '미스릴 폴암'),
    (r'pure waters?', '맑은 물'),   # the game's own name (meowdb / KMS)
    (r'diamond ores?', '다이아몬드의 원석'), (r'leathers?', '가죽'),
    (r'crossbow arrows?', '석궁 전용 화살'), (r'bow arrows?', '활 전용 화살'),
    (r'earrings?', '귀고리'), (r'nx items?', '캐시 아이템'), (r'potions?', '포션'),
]
_ITEM_RX = re.compile(r'(?<![\w\[])(' + '|'.join(p for p, _ in _ITEM_WORDS) + r')(?![A-Za-z\]])', re.I)
_ITEM_KO = [(re.compile(r'^(?:' + p + r')$', re.I), ko) for p, ko in _ITEM_WORDS]
# Gear/market words: only on lines already recognised as trades, so normal
# chat such as "top 10" or "for real" is never touched.
_TRADE_WORDS = [
    (r'pet\s*,?\s*speed', '펫 이동속도'),
    (r'junk nx|nx trash|trash nx|nx junk', '잡캐시템'), (r'hair coupon', '헤어 쿠폰'),
    (r'(?:5|five)[- ]slot coupon', '5슬롯 쿠폰'), (r'coupons?', '쿠폰'),
    (r'overalls?', '전신'), (r'scrolls?', '주문서'), (r'gloves?', '장갑'), (r'hats?', '모자'),
    (r'claws?', '아대'), (r'wands?', '완드'), (r'staffs?', '스태프'), (r'crossbows?', '석궁'),
    (r'shields?', '방패'), (r'capes?', '망토'), (r'shoes', '신발'), (r'tops?', '상의'),
    (r'bottoms?', '하의'), (r'pants', '바지'), (r'ores?', '원석'), (r'ingots?', '판'),
    (r'gear|equipment|equips?', '장비'), (r'mage', '마법사'), (r'thief', '도적'),
    (r'warrior', '전사'), (r'bowman|archer', '궁수'), (r'clean', '노작'),
    (r'offers?|obo', '가격 제안'), (r'pets?', '펫'), (r'stats', '스탯'),
    (r'abv avg|above average', '평균 이상'), (r'avg|average', '평균'),
    # R16 live chat: stat words and 'for all' left in English
    (r'luck|luk', '행운'), (r'dex', '민첩'), (r'for all', '전부'),
    (r'sunglass(?:es)?', '선글라스'), (r'black', '블랙'),
    (r'fame', '인기도'),
    # R18 live chat
    (r'cheap', '싸게'), (r'scrolled', '작된'), (r'ea?r+ings?', '귀고리'),
    (r'halloween', '할로윈'), (r'armou?r', '갑옷'), (r'trash\s+stats?', '저옵'),
    (r'godly|god\s+roll', '옵 좋은'), (r'perfect', '완벽한 작'), (r'boomed', '파괴된'),
    (r'brick(?:ed)?', '망한 작'), (r'pots', '물약'), (r'nego|neg', '흥정 가능'),
    (r'merch(?:ant|ing)?', '되팔이'), (r'smega|smeg|mega', '확성기'),
    (r'split\s+leech', '분할 쩔'), (r'solo\s+leech', '단독 쩔'), (r'leech', '쩔'),
    (r'ulu\s*(?:estate\s*)?1', '울루 1'), (r'ulu\s*(?:estate\s*)?2', '울루 2'),
    (r'skeles?', '스켈레곤'), (r'petri', '페트리파이터'), (r'himes?', '드리미 고스트'),
    (r'fondue', '초콜릿 퐁듀'), (r'halo', '천사의 헤일로'), (r'selective', '셀렉티브 쿠폰'),
    (r'michaels?', '마이클 날개'), (r'rifle', '장난감 총'), (r'z\s*helm|zh', '자쿰 투구'),
    (r'pugc', '보라 가이아 망토'), (r'pgc', '분홍 가이아 망토'), (r'llama', '메이플 라마 스태프'),
    (r'helms?', '투구'), (r'perm(?:anent)?\s+nx', '영구 캐시템'),
    (r'good\s+prices?', '좋은 가격에'), (r'accuracy|acc', '명중률'), (r'bamboo', '대나무'),
    (r'bulk', '대량'), (r'vending\s+machine', '자판기'), (r'emerald', '에메랄드'),
    (r'shirts?', '상의'), (r'daggers?', '단검'), (r'axes?', '도끼'), (r'white\s+labels?', '하얀 명찰'),
    (r'spears?', '창'), (r'mithril pole ?arms?', '미스릴 폴암'), (r'polearms?', '폴암'), (r'magicians?', '마법사'), (r'boxes', '상자'),
    (r'shoes?\s+speed', '신발 이동속도'), (r'strength', '힘'), (r'ear(?=\s+(?:scrolls?|주문서|dex|str|int|luk))', '귀고리'),
    (r'nx\s+clothes', '캐시 옷'), (r'clothes', '옷'), (r'black crystal ores?', '흑수정의 원석'),
    (r'nx(?!\s*items?)', '캐시템'), (r'garnets?', '가넷'),
    (r'signature\s+hair', '시그니처 헤어'), (r'as\s+well', '도'), (r'need\s+a\s+lot', '많이 필요'),
    (r'crates?', '상자'), (r'lemons?', '레몬'), (r'unwanted\s+nx', '안 쓰는 캐시템'), (r'old\s+nx', '옛날 캐시템'),
    (r'low\s+price', '저렴하게'), (r'last\s+one', '마지막 1개'), (r'mesos?\s+only', '메소 거래만'),
    (r'iron(?!\s+(?:ball|axe|helm|shield|sword|mace|plate|ores?|claw|wolf))', '철 원석'),
    (r'negotiable', '흥정 가능'), (r'silver', '실버'), (r'white', '흰색'), (r'def', '방어력'), (r'garnets?', '가넷'), (r'items?', '아이템'),
    (r'hs', '홀리 심볼'), (r'hb', '하이퍼 바디'), (r'se', '샤프 아이즈'), (r'mw', '메이플 용사'),
]
# Weapon kinds: only as a whole item name in a scroll price list, never
# inside a player-typed item name ('Cherubs Bow').
_WEAPONS = {
    '2h sword': '두손검', '2h swords': '두손검', '2h axe': '두손도끼', '2h axes': '두손도끼',
    '2h bw': '두손둔기', '1h sword': '한손검', 'sword': '한손검', 'swords': '한손검',
    '1h axe': '한손도끼', 'axe': '한손도끼', 'dagger': '단검', 'daggers': '단검',
    'polearm': '폴암', 'pole arm': '폴암', 'spear': '창', 'spears': '창', 'xbow': '석궁',
    'crossbow': '석궁', 'bow': '활', 'bows': '활', 'claw': '아대', 'claws': '아대',
    'wand': '완드', 'staff': '스태프', 'knuckle': '너클', 'gun': '총', 'helmet': '투구',
    'helm': '투구', 'earring': '귀고리', 'earrings': '귀고리', 'overall': '전신', 'cape': '망토',
    'shoes': '신발', 'gloves': '장갑', 'glove': '장갑', 'shield': '방패', 'top': '상의',
    'bottom': '하의', 'pet speed': '펫 이동속도', 'pet,speed': '펫 이동속도',
}
_TRADE_RX = re.compile(r'(?<![\w\[])(' + '|'.join(p for p, _ in _TRADE_WORDS) + r')(?![A-Za-z\]])', re.I)
_TRADE_KO = [(re.compile(r'^(?:' + p + r')$', re.I), ko) for p, ko in _TRADE_WORDS]


def _trade_ko(word: str) -> str:
    for rx, ko in _TRADE_KO:
        if rx.match(word):
            return ko
    return word


def _item_ko(word: str) -> str:
    for rx, ko in _ITEM_KO:
        if rx.match(word):
            return ko
    return word


def polish_leftover(result: str) -> str:
    """Translate common market words the item/price rules left in English.

    Only plain words outside [linked item] labels are touched.
    """
    if not result:
        return result
    # 'NX' amounts are Nexon cash, never mesos ("17.5K NX" -> '17,500 캐시')
    result = re.sub(r'(\d[\d,]*(?:\s*[만천]\s*[\d,]*)*)\s*메소\s+(?:넥슨\s+)?캐시', r'\1 캐시', result)
    result = result.replace('캐시 공짜', '캐시 나눔').replace('지금 일어나기', '지금 진행 중')
    if not re.search(r'[A-Za-z]', result):
        return _dedupe_offers(result)
    is_trade = bool(re.search(r'삽니다|팝니다|교환|메소|개당', result))
    parts = re.split(r'(\[[^\[\]\n]+\])', result)
    for i in range(0, len(parts), 2):
        seg = parts[i]
        if is_trade and re.search(r'[A-Za-z]{4}', seg):
            try:
                from .classic_item_index import current_index
                seg = current_index().replace_verified(seg)      # 'squishy shoes' -> 물컹물컹한 신발
            except Exception:
                pass
        seg = re.sub(r'순수(?:한)?\s*물(?:\s*S\b)?', '맑은 물', seg)
        seg = re.sub(r'(?i)(?:아니|NO)\s+(?:INDIANS?|인도(?:인)?)(?:\s*(?:제공|제안|OFFERS?))?', '인도인 사절', seg)
        seg = re.sub(r'(?i)\bno\s+de[fe]\b', '방어력 주문서 제외', seg)
        seg = re.sub(r'(?i)\boffer\s+me\s+(?:a\s+)?(?:price|offer)\b', '가격 제안 주세요', seg)
        seg = re.sub(r'(?i)\bwhisper\s+if\s+inte\s?[Il]?rested\b', '관심 있으면 귓말 주세요', seg)
        seg = re.sub(r'(?i)\b(?:whisp|w)\s+me\b', '귓말 주세요', seg)
        seg = re.sub(r'(?i)\bwhisper\b(?=\s*(?:CH|ch|\d|$))', '귓말 주세요', seg)
        seg = re.sub(r'(?i)\ball\s+my\s+', '제 ', seg)
        seg = re.sub(r'(?i)\bsome\s+(?=[가-힣])', '', seg)                       # 'SELLING SOME NX CLOTHES'
        seg = re.sub(r'(?i)\bear\s+(?=주문서|민첩|힘|지력|행운)', '귀고리 ', seg)        # 'DEX EAR SCROLL'
        seg = re.sub(r'(?i)\bwhisper\b(?=\s*(?:삽니다|팝니다|[.!]|$))', '귓말 주세요', seg)   # 'Bowman Pants. WHISPER'
        seg = re.sub(r'(?i)\bsend\s+(?:me\s+)?(?:ur\s+|your\s+|an?\s+)?(?:offers?\w*|가격\s*제안)', '가격 제안 주세요', seg)
        seg = re.sub(r'(?i)\b(?:(?:for\s+)?[1I]\s+)?persona?l?\s+use\b', '개인 사용 목적', seg)
        seg = re.sub(r'(?i)\bhonest\s+(?:가격|price)', '정직한 가격', seg)
        seg = re.sub(r'(?i)\bquick\s+sale\b', '급처', seg)
        seg = re.sub(r'(?i)\bor\s+highest\s+(?:whisper\s+)?(?:offer|가격\s*제안)', '또는 최고가 제안', seg)
        seg = re.sub(r'(?i)\bthis\s+(mask|hat|ring|item|one)\b',
                     lambda m: '이 ' + {'mask': '가면', 'hat': '모자', 'ring': '반지'}.get(m.group(1).lower(), '아이템'), seg)
        seg = re.sub(r'(?i)(?<=\d)\s*wep\b', ' 공격력', seg)                        # '2 crit 7 wep'
        seg = re.sub(r'(?i)\bopen\s+(?:to\s+)?(?:offers?|가격\s*제안)', '가격 제안 받습니다', seg)
        seg = re.sub(r'(?i)\bless\s+than\s+(?:the\s+)?(?:shop|store|npc)\b', '(상점가보다 저렴)', seg)
        seg = re.sub(r'(?i)판\s+(?:okay|ok|fine)\b', '판도 가능', seg)                    # 'Iron ore 200 Ingot okay'
        seg = re.sub(r'(?i)\b(?:dm|pm|w)\s+me\s+(?:ur\s+|your\s+)?(?:offers?|가격\s*제안)', '귓말로 가격 제안 주세요', seg)
        seg = re.sub(r'(?i)\bwhisper\s+(?:me\s+)?(?:an?\s+|your\s+|ur\s+)?(?:offers?|가격\s*제안)', '귓말로 가격 제안 주세요', seg)
        seg = re.sub(r'(?i)\bpay(?:ing)?\s+(?:in\s+)?(?:메소|mesos?)', '메소로 지불', seg)
        seg = re.sub(r'(?i)(?<=메소)\s+st(?:ar|a|e)tin[ge]\b', '부터', seg)                 # '15K starting'
        seg = re.sub(r'(?i)\bthis\b(?=\s*[.!]?\s*(?:팝니다|삽니다|$))', '이 아이템', seg)      # '[장팔사모] S>this c/o 700k'
        seg = re.sub(r'(?i)\ball\s+(?:your|ur)\s+([가-힣]+)', r'\1 전부', seg)        # 'All your junk nx'
        seg = re.sub(r'(?i),?\s*·?\s*(?:and\s+)?more\b!*(?=\s*(?:팝니다|삽니다|할로윈|$))', ' 등', seg)   # 'coffin, and more!'
        seg = re.sub(r'(?i)\blast\s+chance\b', '마지막 기회', seg)
        seg = re.sub(r'(?i)\bnice\s+(?=미강화|깨끗)', '', seg)                    # 'Nice clean Emerald Earrings'
        if is_trade:
            seg = re.sub(r'(?i)\+\s*mesos?\b', '+ 메소', seg)                     # '3 kumbi + mesos for 1 tobi'
        seg = re.sub(r'(?i),?\s*have\s+(?=(?:팝니다|삽니다)\.\s*재고)', ' ', seg)   # 'HAVE 67 LEFT'
        seg = re.sub(r'(?i)\ball\s+(\d{1,3}%\s*주문서)', r'\1 전부', seg)              # 'all 60% scrolls'
        seg = _ITEM_RX.sub(lambda m: _item_ko(m.group(1)), seg)
        seg = re.sub(r'(포션|장어구이|엘릭서|물)(?=\d)', r'\1 ', seg)
        seg = re.sub(r'(?:백색|화이트|흰색?)\s*포션', '하얀 포션', seg)
        seg = re.sub(r'블루\s*포션', '파란 포션', seg)
        seg = re.sub(r'(?i)\b(blue|white|red|orange)\s+칼륨',
                     lambda m: {'blue': '파란', 'white': '하얀', 'red': '빨간', 'orange': '주황'}[m.group(1).lower()] + ' 포션', seg)
        seg = seg.replace('칼륨', '포션')
        # '100 mesos ea' / '200 Each' / 'ea 270'
        seg = re.sub(r'(?<![\w.])(\d[\d,.]*\s*[kKmM]?)\s*(?:mesos?\s*)?(?:ea|each)\b\.?',
                     lambda m: '개당 ' + _price(m.group(1)), seg, flags=re.I)
        seg = re.sub(r'\b(?:ea|each)\.?\s+(\d[\d,.]*\s*[kKmM]?)(?![\w.])(?:\s*(?:mesos?|메소)(?![\w]))?',
                     lambda m: '개당 ' + _price(m.group(1)), seg, flags=re.I)
        # 'Pure Water ea 750 meso Blue Pot ea 160 meso': one price per item
        seg = re.sub(r'(개당 [\d,.만천억 ]+메소)\s+(?!(?:삽니다|팝니다|에|씩)(?:[.\s]|$))(?=[가-힣])', r'\1, ', seg)
        seg = re.sub(r'메소\s+only\b', '메소 (메소 거래만)', seg, flags=re.I)
        seg = re.sub(r'\bi take all\b', '전부 삽니다', seg, flags=re.I)
        seg = re.sub(r'\btrade me\b', '거래 걸어주세요', seg, flags=re.I)
        seg = re.sub(r'\bpm me\b|\bmsg me\b|\bwhisper me\b|\bwisp me\b', '귓말 주세요', seg, flags=re.I)
        seg = re.sub(r'\boffer me\b|\bleave offers?\b|\boffer price\b', '가격 제안 주세요', seg, flags=re.I)
        seg = re.sub(r'\ba lot of\b', '많은', seg, flags=re.I)
        seg = re.sub(r'\btaking\s+(?:offers?|가격\s*제안)', '가격 제안 받습니다', seg, flags=re.I)
        seg = re.sub(r'\bpm\s+offers?\b', '가격 제안 귓말 주세요', seg, flags=re.I)
        # stats are numbers + words; done here, never by the model
        seg = re.sub(r'(\d+)\s*(?:att|attack)\b', r'\1 공격력', seg, flags=re.I)
        seg = re.sub(r'(\d+)\s*(?:crit(?:ical)?s?|crt)\b(?!\s*(?:dmg|damage))', r'\1 크리티컬', seg, flags=re.I)
        seg = re.sub(r'\bcrit(?:ical)?\b(?!\s*(?:dmg|damage))', '크리티컬', seg, flags=re.I)
        seg = re.sub(r'가격 제안 (?:팝니다|삽니다)\.?\s*가격 제안 받습니다', '가격 제안 받습니다', seg)
        if is_trade:
            # a lone 'and' between items, never inside 'Ink-And-Wash'
            seg = re.sub(r'(?<=\s)and(?=\s)', '·', seg, flags=re.I)
        # auction terms the trade rules left in English
        seg = re.sub(r'\b(s/?b|c/?o|h/?o|a/?w|b/?o|res)\s*[:=]?\s*(\d[\d,.]*\s*[kKmMbB]?)(?![\w.])',
                     lambda m: {'sb': '시작가', 'co': '현재가', 'ho': '최고가', 'aw': '즉결가',
                                'bo': '즉시 구매가', 'res': '최저가'}[m.group(1).lower().replace('/', '')]
                     + ' ' + _price(m.group(2)), seg, flags=re.I)
        # scroll part names ('helm def 60%', 'bot dex 10%', 'sw att 60%')
        seg = re.sub(r'\b(helm|bot|sw|bw|pa|oa)\b(?=\s+(?:[A-Za-z.]+\s+){0,2}\d{1,3}\s*%)',
                     lambda m: {'helm': '투구', 'bot': '하의', 'sw': '한손검', 'bw': '둔기', 'pa': '폴암',
                                'oa': '전신'}[m.group(1).lower()], seg, flags=re.I)
        # stats written as abbreviations ('3 MA', '20 WD')
        seg = re.sub(r'(\d+)\s*(MA|WD|MD)\b',
                     lambda m: m.group(1) + ' ' + {'MA': '마력', 'WD': '물리 방어력', 'MD': '마법 방어력'}[m.group(2)], seg)
        if is_trade:
            seg = re.sub(r'\((F|M)\)', lambda m: '(여)' if m.group(1) == 'F' else '(남)', seg)
        seg = re.sub(r'\bneed\s+(\d{1,4})\s*more\b', r'\1개 더 필요', seg, flags=re.I)
        seg = re.sub(r'\bneed\s+(\d{1,4})\b(?!\s*[kKmM%])', r'\1개', seg, flags=re.I)
        seg = re.sub(r'펫\s*,?\s*speed', '펫 이동속도', seg, flags=re.I)
        if is_trade:
            seg = _TRADE_RX.sub(lambda m: _trade_ko(m.group(1)), seg)
            # 'Any 펫 주문서 삽니다' -> '펫 주문서 아무거나 삽니다'
            seg = re.sub(r'^\s*any\s+([^.·]+?)\s+(삽니다|팝니다)', r'\1 아무거나 \2', seg, flags=re.I)
            seg = re.sub(r'\ball\s+(잡캐시템|캐시 아이템)', r'\1 전부', seg, flags=re.I)
            seg = re.sub(r'\ball\s+nx\b', '캐시 아이템 전부', seg, flags=re.I)
            # '3 slots' (left); never '30 slot ring' (a ring name)
            seg = re.sub(r'\b(\d{1,2})\s*slots?(?:\s*(?:left|remaining))?\b(?!\s*[A-Za-z])', r'업그레이드 가능 \1회', seg, flags=re.I)
            seg = re.sub(r'\+?0?(\d)\s*slots?\s*coupons?', r'\1슬롯 쿠폰', seg, flags=re.I)
            seg = re.sub(r'(?i)\bslots?\b', '슬롯', seg)
            seg = re.sub(r'\bCC\s*(\d{1,2})\s*FM\b', r'\1채널 자유시장', seg, flags=re.I)
            seg = re.sub(r'\bCC\s*(\d{1,2})\b', r'\1채널', seg, flags=re.I)
            seg = re.sub(r'(?<=채널) FM\b', ' 자유시장', seg)
            if re.search(r'(?i)\bshow\s+me\b', seg):
                seg = re.sub(r'(?i)\s*\bshow\s+me\b', '', seg) + ' · 물건 보여주세요'
            seg = re.sub(r'(?<![\w./])(\d+(?:\.\d+)?)\s*([kKmM])(?![A-Za-z])(?!\s*/\s*\d)',
                         lambda m: _price(m.group(1)+m.group(2)), seg)
            seg = re.sub(r'(?:^|(?<=\s))[SB]>\s*', '', seg)
            seg = re.sub(r'(?i)\bnew\s+nx\b', '신규 캐시템', seg)
            seg = re.sub(r'(?i)(?:\s*·\s*|\s+)(?:and\s+)?more(?=\s+(?:팝니다|삽니다)|$)', ' 등', seg)
            seg = re.sub(r'갑옷\s+armou?r\b', '갑옷', seg, flags=re.I)
        # R18: '... or 팝니다' (the 'or' of a split 'S>450k or T> ...'),
        # run after prices/offers are Korean ('17만 메소 or 가격 제안')
        seg = re.sub(r'\s+or\s+(?=(?:팝니다|삽니다)(?:[.\s]|$))', ' ', seg, flags=re.I)
        seg = re.sub(r'(?<=[가-힣\dkKmM])\s+or\s+(?:pm\s+)?(?:a\s+)?price\b', ' 또는 가격 제안', seg, flags=re.I)
        seg = re.sub(r'(?<=[가-힣\d])\s+or\s+(?=[가-힣\d])', ' 또는 ', seg, flags=re.I)
        if is_trade:
            seg = re.sub(r'(?i)\bprices?\b', '가격', seg)     # 'Pm price and stats' (after 'or price')
        parts[i] = seg
    return _dedupe_offers(re.sub(r'\s{2,}', ' ', ''.join(parts)).strip())


_PAIR = re.compile(r"\s*([0-9]*[A-Za-z][A-Za-z0-9 .,'&+-]*?)\s+(\d+(?:\.\d+)?\s*[kKmM])(?![A-Za-z0-9])\s*(?:ea\b|each\b)?\s*[,·|/]?")


def price_pairs(text: str) -> str | None:
    """'B> 60% Scrolls Claw 140k Dagger 135k Wand 115k' -> one price per item.

    Needs at least two 'name price' pairs that cover the whole post.
    """
    m = re.match(r'^\s*([SB])\s*>\s*(.+)$', text or '', re.I)
    if not m:
        return None
    action = '팝니다' if m.group(1).upper() == 'S' else '삽니다'
    body = m.group(2).strip()
    head = ''
    h = re.match(r'(\d+\s*%\s*scrolls?)\s+', body, re.I)
    if h:
        head = re.sub(r'\s+', ' ', h.group(1))
        body = body[h.end():]
    pairs = []
    pos = 0
    while pos < len(body):
        p = _PAIR.match(body, pos)
        if not p or p.end() == pos:
            break
        pairs.append((p.group(1).strip(' ,'), p.group(2)))
        pos = p.end()
    rest = body[pos:].strip(' ,·|/')
    if len(pairs) < 2 or (rest and len(rest) > 20):
        return None
    from .natural_trade import _money

    def name_ko(name):
        return _WEAPONS.get(re.sub(r'\s+', ' ', name.lower()), name)
    items = ', '.join(f'{name_ko(name)} {_money(price.replace(" ", "").lower())}' for name, price in pairs)
    if rest:
        items += ', ' + rest
    head = re.sub(r'(?i)scrolls?', '주문서', head)
    return (f'{head}: ' if head else '') + f'{items} {action}'


_PLAIN_PAIR = re.compile(r'\s*(?:[SB]\s*>+\s*)?([A-Za-z][A-Za-z .]*?)\s+(\d{2,6})(?![\d.kKmM%])\s*(?:(?:ea|each)\b)?\s*[,·|/]?', re.I)


_COLOUR_POTS = {'blue': '파란 포션', 'red': '빨간 포션', 'white': '하얀 포션', 'orange': '주황 포션'}


def consumable_prices(text: str, translate=None) -> str | None:
    """'B> UNAGIS 500 WHITE POTS 250 ORANGE POTS 125 PURE WATER 700' ->
    '장어구이 500, 하얀 포션 250, 주황 포션 125, 맑은 물 700 삽니다'. Every name
    must be a known consumable; the unit stays as the player wrote it."""
    m = re.match(r'^\s*([SB])\s*>+\s*(.+)$', text or '', re.I)
    if not m:
        return None
    action = '팝니다' if m.group(1).upper() == 'S' else '삽니다'
    body, pos, pairs = m.group(2).strip(), 0, []
    while pos < len(body):
        p = _PLAIN_PAIR.match(body, pos)
        if not p or p.end() == pos:
            break
        name = re.sub(r'\s+', ' ', p.group(1)).strip(' .')
        ko = _COLOUR_POTS.get(name.lower()) or _item_ko(name)
        if ko == name or not re.search('[가-힣]', ko):
            return None
        each = bool(re.search(r'\b(?:ea|each)\b', p.group(0), re.I))
        pairs.append(f'{ko} {"개당 " if each else ""}{p.group(2)}')
        pos = p.end()
    rest = body[pos:].strip(' ,·|/')
    if len(pairs) < 2:
        return None
    if rest:
        if translate is None:
            return None
        # 'B> Blue 130 Unagi 400 ... Ear Dex/Str60%': the rest is its own item
        rest_ko = re.sub(r'\s*(?:삽니다|팝니다)\.?\s*$', '', translate(m.group(1).upper() + '> ' + rest)).strip()
        if not rest_ko or re.search(r'[A-Za-z]{4,}', rest_ko):
            return None
        pairs.append(rest_ko)
    return ', '.join(pairs) + ' ' + action


def offer_post(text: str) -> str | None:
    """A whole 'S> Taking offers PMO' line: the seller wants price offers."""
    if re.fullmatch(r'\s*(?:[SB]\s*>+\s*)?taking\s+offers?\s*(?:[,.!]\s*)?(?:pmo|pm\s*me|pm|msg\s*me|w\s*me)?[\s!.~]*',
                    text or '', re.I):
        return '가격 제안 받습니다 · 귓말 주세요'
    return None


_GENDER = {'f': '여자 ', 'female': '여자 ', 'm': '남자 ', 'male': '남자 '}


def _batchim(word: str) -> bool:
    """True when the last Hangul syllable has a final consonant (과/이에요)."""
    last = (word or '').strip()[-1:]
    return bool(last) and '가' <= last <= '힣' and (ord(last) - 0xAC00) % 28 != 0


def _gear_for(m) -> str:
    who = _CLASSES.get(m.group(2).lower(), m.group(2))
    return f'{_GENDER.get((m.group(1) or "").lower(), "")}{who} {m.group(3)}레벨용 장비'


def _dedupe_offers(out: str) -> str:
    out = re.sub(r'(귓말 주세요)\.?\s+(삽니다|팝니다)', r'\2. \1', out)        # '귓말 주세요 삽니다'
    out = re.sub(r'(?i)\ball\s+(\d{1,3}%\s*주문서)', r'\1 전부', out)              # 'all 60% scrolls'
    out = re.sub(r'(?i)(^\s*|·\s*)all\s+([가-힣][^.·]*?)\s+(삽니다|팝니다)', r'\1\2 전부 \3', out)   # 'Buy all scrolls'
    out = re.sub(r'(\d[\d,]*)\s*mesos?\b', r'\1 메소', out, flags=re.I)        # '900mesos cheap'
    out = re.sub(r'(?<=[가-힣])\s+도(?=\s|$)', '도', out)                           # '어딜 덤비냥 도' (as well)
    # '(700 Meso Each)' came out as '(700 메소 개당)'
    out = re.sub(r'([\d,]+)\s*메소\s*개당', r'개당 \1 메소', out)
    # a second 'BUYING' / 'SELLING' inside the same post
    out = re.sub(r'(?<=[가-힣!.;,]\s)(?:BUYING|SELLING|buying|selling)\s+', '', out)
    # 'meet in fm ch28' - the room/channel is shown separately
    out = re.sub(r',?\s*m\s?eet(?:\s+(?:in|at|@))?\s*(?=삽니다|팝니다|$)', ' ', out)
    out = re.sub(r'\bor\s+trade\s+for\s+(.+?)(?=\s+(?:팝니다|삽니다)|$)',
                 lambda m: '또는 ' + m.group(1) + ('과' if _batchim(m.group(1)) else '와') + ' 교환', out, flags=re.I)
    out = re.sub(r'\bFemale\b', '여자', out)
    out = re.sub(r'\bMale\b', '남자', out)
    out = re.sub(r'\bfor\s+([\d,]+\s*(?:[만천억]\s*[\d,]*\s*)*메소)', r'\1에', out, flags=re.I)
    # the sentence model repeated particles ('의 의', '각 각 각'); a word the
    # player repeated on purpose ('ye ye' -> '응 응') stays
    out = re.sub(r'(?<![가-힣])(의|각|에|을|를|은|는|이|가|와|과|및|대|한|로|으로)(?:\s+\1)+(?![가-힣])', r'\1', out)
    out = re.sub(r'([\d,]+\s*(?:[만천억]\s*[\d,]*\s*)*메소)\s+ea\b', r'개당 \1', out)
    out = re.sub(r'캐시 아이템\s+(?:items?|아이템)\b', '캐시 아이템', out)
    out = re.sub(r'표창\s+stars?\b', '표창', out, flags=re.I)
    out = re.sub(r'(?:\s+-+)+\s*(?=(?:삽니다|팝니다)|$)', ' ', out)
    out = re.sub(r'\s+--\s+', ' · ', out)
    out = re.sub(r'(?i)(?:\b(?:gear|equips?|equipment)|장비)\s+for\s+(?:(f|m|female|male)\s+)?([a-z]+)\s+(?:lv|lvl|level|tv|lyl)\s*(\d{1,3})',
                 _gear_for, out)
    out = re.sub(r'!(?:\s+!)+', '!', out)      # '! !' only; '!!!' stays
    out = re.sub(r'\s+\.\s+(?=삽니다|팝니다)', ' ', out)
    out = re.sub(r'갑옷\s+갑옷', '갑옷', out)
    # 'S> Taking offers' -> not "selling price offers"; say it once
    out = re.sub(r'가격 제안 받습니다\s+PMO\s+(팝니다|삽니다)', r'\1 · 가격 제안 받습니다 · 귓말 주세요', out)
    out = re.sub(r'^(?:가격 제안 (?:팝니다|삽니다)\.?\s*)(?=가격 제안 받습니다)', '', out)
    return re.sub(r'(?<=\] · )가격 제안 (?:팝니다|삽니다)\.?\s*(?=가격 제안 받습니다)', '', out)


# Item names the model translates word by word ("Dollish Pink" -> '인형 핑크').
# Keep the English name when the source line has it.
_KEEP_NAMES = [
    (re.compile(r'dollish\s+pink', re.I), re.compile(r'인형\s*(?:같은\s*)?(?:핑크|분홍)'), 'Dollish Pink'),
]


def keep_item_names(source: str, result: str) -> str:
    for src_rx, bad_rx, name in _KEEP_NAMES:
        if src_rx.search(source or ''):
            result = bad_rx.sub(name, result)
    return result


def _price(value: str) -> str:
    v = re.sub(r'\s+', '', value)
    if re.fullmatch(r'\d+(?:\.\d+)?[kKmM]', v):
        from .natural_trade import _money
        return _money(v.lower())
    if re.fullmatch(r'\d{1,3}(?:,\d{3})+|\d+', v):
        return v + ' 메소'
    return v
