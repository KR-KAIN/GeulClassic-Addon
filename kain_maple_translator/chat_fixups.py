"""R18 inspection fixes from a 150 s live Free Market sample (208 lines).

- OCR crumbs of '@@@@' spam ('aa@aa', 'CQQQQ', '②②②', '=========', '250C')
- trade-marker variants ('S<<', '$>', 'B)', 'B ITEM 90K')
- item/word OCR variants (PAN UID -> panlid, Ammor -> armor, Scrolis, Overali,
  Fure Water, buvina -> buying, 8WAWG, offerme, '120 FAL' -> '120 EA')
- stat posts the model garbled ('attack+11 cri+2', '+4 crit damage',
  '3 slots left', 'taking offers')
- known model hallucinations for unknown single words ('뚱 베어', '…의 특징')
- casual requests ('fame 4 fame', 'anyone can help me with ...')
"""
from __future__ import annotations

import re
import unicodedata

# ------------------------------------------------------------ cleaning
_CRUMB_CHARS = set('@aQqCcde0123456789②③④①⑤⑥ΦσΦ∂©#.,-~')


def _latin_plain(text: str) -> str:
    """Drop accents on Latin letters only ('bívinat' -> 'bivinat').
    Hangul must never be decomposed."""
    out = []
    for ch in text:
        if ord(ch) < 0x0250 and not ch.isascii():
            base = unicodedata.normalize('NFKD', ch)
            out.append(''.join(c for c in base if not unicodedata.combining(c)) or ch)
        else:
            out.append(ch)
    return ''.join(out)


def _is_crumb(token: str) -> bool:
    if not token:
        return False
    if re.fullmatch(r'\d{2,}@+', token):
        return False      # 'WHITE POTS 250@': the price stays
    if re.fullmatch(r'[QO0]{4,}', token):
        return True
    if not set(token) <= _CRUMB_CHARS:
        return False
    return any(c in token for c in '@②③④①⑤⑥')


_TAIL_JUNK = set('@②③④①⑤⑥©Φ∂σ')


def _drop_crumb_tail(value: str) -> str:
    """'R> RUSH FAST RUNS 6 © @ ② 6 @ @ @': a spaced spam tail with OCR
    crumbs ('6', '©', 'C') inside. A digit stays unless real garbage
    symbols surround it ('need 2 @ @ @' keeps the 2)."""
    toks = value.split(' ')
    i = len(toks)
    while i > 0 and toks[i-1] and len(toks[i-1]) <= 2 and set(toks[i-1]) <= (_CRUMB_CHARS | _TAIL_JUNK | {'C'}):
        i -= 1
    tail = toks[i:]
    if sum(1 for t in tail if t and set(t) <= _TAIL_JUNK) < 2:
        return value
    if not any(set(t) & set('②③④①⑤⑥©Φ∂σ') for t in tail):
        while tail and re.search(r'\d', tail[0]):
            i += 1
            tail = tail[1:]
    return ' '.join(toks[:i])


def collapse_repeats(text: str) -> str:
    """'Add me, level 39Add me, level 39Add me, level 3' -> one copy."""
    m = re.fullmatch(r'(.{6,60}?)(?:\s*\1)+\s*(.*)', text or '', re.S)
    if m and m.group(1).strip() and m.group(1).startswith(m.group(2).strip()):
        return m.group(1).strip()
    return text


def clean_crumbs(text: str) -> str:
    """Remove what the spam cleaner leaves behind."""
    value = _latin_plain(text)
    value = re.sub(r'[=]{4,}|-{4,}|[*]{4,}|[+]{6,}', ' ', value)
    # runs of circled digits are the same decoration as '@@@@'
    value = re.sub(r'[②③④①⑤⑥]{2,}[②③④①⑤⑥@a-zA-Z0-9]*', ' ', value)
    value = re.sub(r'(?<![A-Za-z])([JjIi1]?[Pp][QqOo])[QqOo0]{3,}(?![A-Za-z])', r'\1', value)
    value = re.sub(r'(?<=[A-Za-z])(?:l?e)Fr[o0][gq]?\s*$|\s(?:l?e)Fr[o0][gq]?\s*$', '', value)   # super megaphone screen crumbs
    value = re.sub(r'(?<=[a-z0-9])(?:Hit)?TheR(?:oad|n)\s*$', '', value)                  # 'HitTheRoad'
    value = _drop_crumb_tail(value)
    value = ' '.join(t for t in value.split() if not _is_crumb(t))
    # 'Potion 250C' / '740@Q' / 'QWhite': a crumb letter glued to text
    value = re.sub(r'(?<=\d)[QC]@*(?=\s|$)', '', value)
    value = re.sub(r'(?<=\d)@[QC@]*', '', value)
    value = re.sub(r'(?<![A-Za-z])[QC](?=[A-Z][a-z]{2,})', '', value)
    return re.sub(r'\s{2,}', ' ', value).strip()


# ------------------------------------------------------------ markers / words
def repair_markers(text: str) -> str:
    value = text
    # R18 live: 'B< Pure Water ea 750' (B< for B>), 'SXAP Reset' (S> AP)
    value = re.sub(r'^(\s*)[BbHh]\s*<\s*(?=[A-Za-z]{3})', r'\1B> ', value)      # 'B<', 'b< scroll', 'h< srroll'
    value = re.sub(r'(?<=\s)[\$§]\s*>', 'S>', value)                             # '@@@@@ $ > LVL 20'
    value = re.sub(r'^(\s*\[[^\]\n]*\]\s*)[\$§]\s*>', r'\1S>', value)            # '[Ring] $>500k'
    value = re.sub(r'(?<=\s)[I|1l](?=[SB]>)', '', value)                         # 'HATS IS>FAME'
    value = re.sub(r'^(\s*)B(?=(?:GFA|GMA|GFMA|WG|BWG)\b)', r'\1B> ', value)       # 'BGFA 60% 800k'
    value = re.sub(r'(?i)^(\s*)sell(?:ing)?\s*>+', r'\1S>', value)                 # 'Sell >> +05 Slot'
    value = re.sub(r'(?i)^(\s*)(?:buy(?:ing)?|wtb)\s+(?=(?:all|al|any)\s)', r'\1B> ', value)    # 'Buy all scrolls'
    value = re.sub(r'(?i)^(\s*)buy(?:ing)?\s*>+', r'\1B>', value)
    # ('S<' stays: its direction is never assumed - R10 rule)
    # 'Trading Male dark suit for Female Dark suit' (T> without the marker)
    value = re.sub(r'(?i)^(\s*)trad(?:ing|ind|e)\s+(?=.+\s+for\s+\S)', r'\1T> ', value)
    value = re.sub(r'^(\s*(?:\[[^\]\n]*\]\s*)?)(buy(?:ing)?|sell(?:ing)?)\s+(.+?)\s+(?:at|for|@)\s+(\d+(?:\.\d+)?\s*[kKmMbB])(\s*(?:each|ea))?\s*$',
                   lambda m: m.group(1) + ('B> ' if m.group(2).lower().startswith('b') else 'S> ')
                   + m.group(3) + ' ' + m.group(4) + (m.group(5) or ''), value, flags=re.I)
    # 'Selling White Label 480k', 'Sell low price NX 19K each', 'BUY any NX 10000 each'
    value = re.sub(r'(?i)^(\s*)(?:sell(?:ing|ina|ino|in)?|wts)\s+(?!me\b|you\b|u\b|it\b)(?=.*(?:\d+(?:\.\d+)?\s*[km]\b|\d+\s*(?:ea|each)\b))',
                   r'\1S> ', value)
    value = re.sub(r'(?i)^(\s*)(?:buy(?:ing)?|wtb)\s+(?!me\b|you\b|u\b|it\b)(?=.*(?:\d+(?:\.\d+)?\s*[km]\b|\d+\s*(?:ea|each)\b))',
                   r'\1B> ', value)
    # 'h>60% earing' (b>), 'S 60% Earrings' (no '>')
    value = re.sub(r'^(\s*)h\s*>(?=\s*(?:\d+\s*%|[A-Za-z]))', r'\1b>', value)   # 'h>hat' is b>hat
    value = re.sub(r'^(\s*)>\s*(?=(?i:[pq]{4,}))', r'\1J>', value)                 # '> pqpqpq any'
    value = re.sub(r'^(\s*)([SB])\s+(?=\d+\s*%\s*[A-Za-z])', r'\1\2> ', value)
    value = re.sub(r'^(\s*)([SB])X(?=AP\b|SP\b|[A-Z][a-z]{2}|[A-Z]{3})', r'\1\2> ', value)   # 'BXSCROLLS'
    value = re.sub(r'^(\s*(?:\[[^\]\n]+\]\s*)?)([SB])\s*<{2,3}', r'\1\2<', value)
    value = re.sub(r'^(\s*)[\$§]\s*>', r'\1S>', value)
    value = re.sub(r'(?<=[/,·]\s)§\s*>|(?<=[/,·])§\s*>', 'S>', value)      # '/ §> Pet Speed'
    value = re.sub(r'^(\s*)([SB])\)\s*', r'\1\2> ', value)
    # 'B CHOCOLATE RIBBON 90K': single S/B, then an item and a k/m price
    value = re.sub(r'^(\s*)([SB])\s+(?=[A-Za-z][A-Za-z ]{2,40}\s*\d+(?:\.\d+)?\s*[kKmM]\b)', r'\1\2> ', value)
    return value


_WORDS = [
    (r'\bpan\s*(?:l\s*i\s*d|u\s*i\s*d|l\s*d|i\s*i?\s*d)\b', 'panlid'),
    (r'\bam{1,2}or\b|\barmour\b', 'armor'),
    (r'\bsc?a?ro?l{1,2}is\b|\bscrols\b|\bsaroll?s\b', 'scrolls'),
    (r'\bsaroll?\b|\bscrol\b', 'scroll'),
    (r'\boveral[ilf1]\b', 'overall'),
    (r'\bf(?:u|ur)e\s*water\b', 'pure water'),
    (r'\b[bh][iuy]v[iy]n[ag]t?(?=\s|$|scrolls?)', 'buying '),
    (r'(?<=\d)\s*WAWGs?\b', ' WA WG'),
    (r'\bofferme\b', 'offer me'),
    # R18 live chat
    (r'\bpure\s*water\b', 'pure water'),
    (r'(?<=\d)\s*mesos?\b', ' meso'),            # '160MESO' is 160, not 160M
    (r'\bea(?=\d)', 'ea '),
    (r'(?<=\d[kK])[A-Z](?=\s|$)', ''),            # '330kE' crumb
    (r'\bRU\s+NS\b', 'RUNS'), (r'\bRUSHFAST\b', 'RUSH FAST'),
    (r'\bear(?:r?ing|ina|dna|ting|rina)s?\b', 'earring'),
    (r'\b[RrBbH]lue\s+[nrph]otion', 'blue potion'),
    (r'(?<=\d)(\s*[kKmM]?)\s+ach\b', r'\1 each'),
    (r'\bbuv\b|\bhuv\b', 'buy'),
    (r'(?<=[A-Za-z])@[@.]*(?=\s|$)', ''),
    (r'\bNEN\s+NX\b', 'NEW NX'),
    (r'\bunag\s?[1il]{1,2}s?\b|\bhnagi\b|\binaai\b', 'unagis'),
    (r'(?<=>)\s*pots?\s+(white|blue|red|orange)\b', r' \1 pots'),   # 'B> Pots White' -> 'White pots'
    (r'\battac\b', 'attack'), (r'\belixeir\b', 'elixir'),
    (r'\bdey\b(?=\s*\d+\s*%)', 'dex'), (r'\bsneed\b', 'speed'), (r'\bqverall\b', 'overall'),
    (r'\bwarf?i?or\b|\bwarinr\b|\bwarfior\b', 'warrior'), (r'\bpumpkn\b', 'pumpkin'),
    (r'\boranae\b', 'orange'), (r'\banv\b', 'any'),
    # R19 corpus audit, second pass
    (r'\bhlue\b', 'blue'), (r'(?<=blue\s)n[on]ts\b', 'pots'), (r'\bnrice\b', 'price'), (r'\biteme\b', 'items'),
    (r'\bemarled\b', 'emerald'), (r'\bhoms?\b', 'horns'), (r'\bdevil\s+horn\b', 'devil horns'),
    (r'\bcatsoul\b', 'cat soul'), (r'\bLVI\b(?=\s*\d)', 'LVL'), (r'\bAl\b(?=\s+s[ca]rolls?)', 'all'),
    (r'\bpu(?:re|rf|e|r)\s*w[ae]te[rq]s?\b', 'pure water'), (r'\br[l1]u?sh\b', 'rush'),
    (r'\bany[qgco0]{1,3}\b', 'any'),
    # R19 corpus audit, third pass
    (r'\bfamle\b', 'FAME'), (r'\bstaf\b', 'staff'), (r'\bmagic\s+at\b(?!t)', 'magic attack'),
    (r'\bs[a-z]?[au]ish[yv]\b', 'squishy'), (r'\bsho\b(?=\s+speed)', 'shoe'), (r'\beamtng\b|\bfarr?inas?\b', 'earring'),
    (r'\b(\d)\1{4,}\b', ''), (r'(?<=\d)n(?=%)', '0'), (r'(?<=\d)nk\b', '0k'), (r'Δ(?=[A-Za-z])|(?<=[A-Za-z])Δ', 'A'),
    (r'\bunaoi\b', 'unagi'), (r'(\d+)\s*/\s*ea\b', r'\1 ea'), (r'\bscrdl\b|\bsaols\b|\bsarols\b', 'scrolls'),
    (r'\bgranet\b', 'garnet'), (r'\bloong\b|\blookin\b', 'looking'), (r'\biust\b', 'just'), (r'\bmavhe\b', 'maybe'),
    (r'\bmanle\b', 'maple'), (r'\bonen\b', 'open'), (r'\bvou\b', 'you'), (r'\bvour\b', 'your'),
    (r'\bscrolle\b', 'scrolls'), (r'\bmummv\b', 'mummy'), (r'\bhonus\b', 'bonus'), (r'\bchanae\b', 'change'),
    (r'\bL[1I]IK\b', 'LUK'), (r'\bfmerald\b', 'emerald'), (r'\beves\b', 'eyes'), (r'\bruvina\b', 'Buying'),
    (r'\bnire\b(?=\s+clean)', 'Nice'),
    # R19 audit, fourth pass (megaphone font misreads)
    (r'\br[l1i]sh\b', 'RUSH'), (r'\bjon[i1]ng\b', 'joining'), (r'\bwhitep\b(?=\s*potion)', 'white'),
    (r'\bO\s*V[FE]L\s*ALL\b|\bovfraii\b|\bovera[l1]{1,2}\b', 'overall'), (r'\b[L1l][1Il]IK\b', 'LUK'),
    (r'\bwolhis\b', 'wolbis'), (r"\bwolbi'?s\b", 'wolbis'), (r'\b[1lIt]\s?evel(?=\s*\d)', 'level '),
    (r'\bc\s+hance\b', 'chance'), (r'\bfach\b', 'each'), (r'\bpurf\b', 'pure'), (r'\bshne\b', 'shoe'),
    (r'\bgtoves?\b', 'gloves'), (r'\bctean\b', 'clean'), (r'\bfarring\b', 'earring'), (r'\bdfx\b', 'dex'),
    (r'\bdff\b', 'def'), (r'\bscrol[il1]\b', 'scroll'), (r'\bfar\b(?=\s+scroll)', 'ear'),
    (r'\b[1lIt]{1,2}naai', 'Unagi '), (r'(?<=\d)FA\b', 'EA'), (r'\bru[yv]ing\b', 'BUYING'),
    (r'\beach(?=(?:pure|white|blue|red|orange|mana|elixir)\b)', 'each '),
    (r'\b(white|blue|red|orange|mana)\s+n[ao]tions?\b', r'\1 potion'),
    (r'\b([KLJRD]?)P[O0]\b(?=\s*(?:rush|[bhr]o?n[l1]?[uo]?s|bonus))', r'\1PQ'), (r'\brush[l1e]\b', 'RUSH'),
    (r'\bPQ[l1I]\b', 'PQ'), (r'\bpure\s*,\s*water\b', 'pure water'), (r'\bnure\s+water(?=\d|\b)', 'pure water'),
    (r'\bearh\b', 'each'), (r'(?<=\d[kKmM]\s)ea(?-i:(?=[A-Z][a-z]))(?!ch\b)', 'ea '), (r'\bpan\s+(?:h?id|ud|l[il1]d)\b', 'Pan Lid'),
    (r'\+\s*[1lI]{2}K\b(?=\s+overall)', '+ LUK'), (r'(?<![\d%])%\s*(\d{1,3})\b', r'\1%'),
    (r'\bscr\s?[o0][lI1]{2}\b', 'scroll'), (r'\bscr\b(?=\s*\d)', 'scroll'), (r'\bPN\b(?=\s+[A-Z][A-Za-z]+\.?\s*$)', 'PM'),
    # R19 audit, fifth pass
    # R19 live check (08:07 session)
    (r'(?<=[\s,])(?-i:[ADIJ1l])(?:\s*>\s*)?[hb]onus\b', ' J> bonus'), (r'\biscrolls\b', 'scrolls'),
    (r'\bwolbie?\s+throwing\s+stars?\b', 'wolbis'), (r'\bwol\s*bi[ef]s\b', 'wolbis'), (r'\bfamf\b', 'FAME'),
    (r'\banvone\b', 'anyone'), (r'\bty{2,}\b', 'ty'), (r'\b(rush|bonus)\d{1,2}\b', r'\1'), (r'\bdr\s+(?:i\s+)?acula\b', 'Dracula'),
    (r'\bwnite\b', 'white'), (r'\bcoff?[il]?n\s+of\s+gloom\b', 'Coffin of Gloom'), (r'(?-i:\bPIs\b)', 'Pls'), (r'\bIv(?=\d)', 'lv'), (r'\bI?PM\s?MEI?\b', 'PM ME'),
    (r'\bpet\s+speed\s+(100|60|10)\b(?!\s*%)', r'pet speed \1%'), (r'\s*=\s*(?=\d)', ' '),
    (r'^\s*([SB])x(?=[A-Z]{3})', r'\1> '), (r'\bchnese\b', 'chinese'), (r'\b(steel|bronze|adamantium)\s+ign?or\b', r'\1 Igor'),
    (r'\bpri?s[oi]n(?:er)?\s+pants\b|\bpison\s+pants\b', 'Prisoner Pants'), (r'\bof\s+fer\b', 'offer'),
    (r'\bmessos\b', 'mesos'), (r'(?<=(?:plz|pls)\s)hel[oó]\b', 'help'), (r'\b(?:riark|rlack|hlack)\b', 'Black'),
    (r'\bcr[vy]e?s?tal\b', 'Crystal'), (r'\b(potion|scroll|pot)s{2,}\b', r'\1s'), (r'\bto\s?bi\s+throwing\s+stars?\b', 'tobis'),
    (r'(\d+)\s*/\s*each\b', r'\1 each'), (r'\bngot\b', 'ingot'), (r'\blron\b', 'iron'), (r'(?<=[a-z])B\s?(?=0%)', ' 6'),
    (r'\bscrol[il1]s\b|\bsrrolls?\b', 'scrolls'), (r'\bamor\b', 'armor'),
    (r'^\s*([SB])\s+(?=(?:gloves?|helm|hat|cape|shoes?|claw|dagger|wand|staff|bow|overall|earrings?|top|bottom)\b)', r'\1> '), (r'(?<=\d{3})n\b', '0'), (r'^\s*([JjIi1])\s*\)\s*>', r'\1>'),
    (r'^\s*B(?:[.,]\s*|\s+)(?=all\b)', 'B> '), (r'\bmithril\s+pole\s?arm\b', 'Mithril Pole Arm'), (r'\b[hr]uvina\b', 'Buying'), (r'(?<=water)(?=\d)', ' '), (r'(?<=\d)nnu?\b', '00'), (r'(?<=\d{3})[uU]\b', ''),
    (r'\bwol\s+bis\b', 'wolbis'), (r'\b(rush)h{2,}[a-z]*', r'\1'), (r'\bpole?a[mr]m\b|\bpokam\b', 'polearm'),
    (r'\bcean\b', 'clean'), (r'\bnanlid\b', 'Pan Lid'), (r'\beari?n[oa]s\b', 'earrings'), (r'\bhal+o+ween\b', 'Halloween'),
    (r'\be[i1l]l\s+skull\b', 'evil skull'), (r'\bIEvil\b', 'Evil'), (r'(?<=\d)(?=each\b)', ' '),
    (r'(?<=\d[kKmM])\s?ea+e+ch\b', ' each'), (r'\bhighest\s+offer\s+wins\b', 'taking offers'),
    # the whole item name, before 'and' joins two items ('Ink · wash thought ring')
    # ('ink and wash name rings' is a different item and stays)
    (r'\bink\s*(?:-\s*)?(?:and|&|n)?\s*(?:-\s*)?wash\s+(?:thought(?:\s+bubble)?|bubble)\s+r?ing\b', 'Ink-and-Wash Thought Bubble Ring'),
    # '170k each ---- S clean Work Gloves 2.5k each': a dash-separated second post
    (r'[-—–]{3,}\s*S\s+(?=[A-Za-z])', ' S> '),
    # 'NO DEFB>ALL NX': a second trade marker glued to the previous word
    (r'(?<=[A-Za-z0-9%!.]{3})(?<![Ww][Tt])([SB])>(?=\s*[A-Za-z0-9])', r' \1>'), (r'\b[asdf]{4,}\b|\bqwer(?:ty)?\b|\bzxcv\b', ''),   # keyboard mash
    (r'\b([a-z])\1{4,}[a-z]{0,2}\b', ''),                       # 'wwwwwwwww'
    (r'(?:[!lI|]?@){3,}[!lI|]?', ' '),                          # '!@!@l@!@' decoration
    (r'\belixer\b', 'elixir'), (r'\bbuyng\b', 'buying'), (r'\bsorrv\b', 'sorry'),
    (r'\bcrnsshow\b|\bcrossbw\b', 'crossbow'), (r'\bscrol\b', 'scroll'),

    (r'(?<=\d)\s+@\d{1,3}\s*$', ''),            # '700 @12' (a spam counter, not 'at 12')
    (r'(?<=\d)\s*(?:mil|mill|million)\b', 'm'), (r'(?<=\d)\s*(?:bil|billion)\b', 'b'),   # '10 mil'
    (r'\bcach(?:\s*\d)?\b', 'each'), (r'\bofer\b', 'offer'), (r'\bPOT\$', 'POTS'),
    (r'\bC/\s+(?=\d)', 'c/o '),
    (r'(?<=\d[kKmM])\d(?=\s*$)', ''),          # 'c/o 150k1' (end-of-line crumb)
    (r'(?<=\d)\s*(?:FAL|FAU|FAI|EAl|EAI)\b', ' EA'),
    # R19 corpus audit (the user's own 2,000 latest chat lines)
    (r'\bDAGGE\s[RB](?=\s|PANTS|$)', 'DAGGER '), (r'\bSHO[EF][S5]?\b', 'SHOES'),
    (r'(?<=\d)\s+mes(?:\s+o)?\b', ' meso'),                 # '120 MES O' (cut off), never 'MESO' (r'\bH[iΔ]\s?Ts\b', 'HATS'), (r'\bsqu[s]?hy\b', 'squishy'),
    (r'\bearrngs?\b', 'earrings'), (r'\bemeral\b', 'emerald'), (r'\bsiver\b', 'silver'), (r'\bhoms\b', 'horns'),
    (r'\b(?:FAMF|EAME|FAMEA|FANE|EAMF)\b', 'FAME'),
    (r'\bSFLL?I?NG\b|\bSELUNG\b|\bSELLIN[AO]?\b', 'SELLING'), (r'\bSAFFTY\b', 'SAFETY'), (r'\bREFF\b', 'REEF'),
    (r'\bCL\s+AW\b', 'CLAW'), (r'\bSCRON\s+S\b', 'SCROLLS'), (r'\bSCRO[UN]\b', 'SCROLL'),
    (r'\bs\s?(?:c|r)r?o?l{1,2}\b', 'scroll'), (r'\blnk\b', 'luk'), (r'\b(?:Iv|Ivl|lw|lvI)\b(?=\s*\d)', 'lvl'),
    (r'\bL\s?V\s?(?=\d)', 'LV'), (r'\bOEX\b', 'DEX'), (r'\bWTNT\b', 'W INT'), (r'\bH[iΔ]ts\b', 'HATS'),
    (r'\b(?:[RrH]lue|BLUF|Bluf)\s+(?:[nrph]otions?|pots?|pote)\b', 'blue pots'), (r'\bBLUF\b', 'BLUE'),
    (r'\bRert\b', 'Red'), (r'\b(?:[IiHh][nm]aai|unaai|imaai|hmaai|unac[il1]|unag[tdl])\b', 'unagi'),
    (r'(?<=\s\d{2})[nr]\b', '0'), (r'\bpu(?:re|rf|e|r)\s*waters?\b', 'pure water'),
    (r'\bhween\b', 'halloween'), (r'\bchean\b|\bchap\b', 'cheap'), (r'\bcupon\b', 'coupon'),
    (r'\bnegotia[bh]i?[li]?e\b|\bneaotiahle\b|\bnegotiabie\b', 'negotiable'),
    (r'\boffters\b|\boffrs\b|\bofffr\b|\bofffrs\b', 'offers'), (r'\bpole\s?(?:a|am|arm)\b', 'polearm'),
    (r'(?:^|(?<=\s))\|RON\b', 'IRON'), (r'(?<=\d)O(?=[kKmM]\b)', '0'), (r'\bpmo[a-z]{3,}\b', 'pmo'),
    (r'\banvone\b', 'anyone'), (r'\bmanv\b', 'many'), (r'\bioin\b', 'join'), (r'\bmaae\b', 'mage'),
    (r'\blemots\b|\blfmons\b|\blémons\b', 'lemons'), (r'(?<=\d)\s+%', '%'),
    (r'(?:\b[QC]{1,4}\b\s*){3,}', ' '),                                     # 'QCQ Q QQQ Q QQ' crumbs
    (r'(?<=[a-z0-9])(?:Hit)?TheR(?:oad|n)\s*$', ''),                         # screen crumbs 'HitTheRoad'
    (r'(?<=!)[lI1]{2,}', ''), (r'(?<=\)\s)1(?=[A-Z]{3})', ', '),
]
_WORDS_RX = [(re.compile(p, re.I), r) for p, r in _WORDS]


def repair_words(text: str) -> str:
    """Whole-word OCR fixes, never inside [linked item] labels."""
    parts = re.split(r'(\[[^\[\]\n]+\])', text)
    for i in range(0, len(parts), 2):
        seg = parts[i]
        for rx, rep in _WORDS_RX:
            seg = rx.sub(rep, seg)
        # '& NT' / 'LUK NT' -> INT
        seg = re.sub(r'(?<=&\s)NT\b|(?<=LUK\s)NT\b', 'INT', seg)
        # 'Buying ... 65k ea R>Nice clean ...': a second buy marker read as R>
        if re.match(r'(?i)\s*(?:b\s*>|buy)', seg):
            seg = re.sub(r'(?<=\s)R>(?=\s*[A-Za-z])', 'B>', seg)
        # 'B ALL ORE $50EACH $160 IRON': '$' stands for mesos in a trade post
        if re.match(r'(?i)\s*[SB]\s*>', seg) and not re.search(r'(?i)meso|usd|www|u4n', seg):
            seg = re.sub(r'\$\s*(?=\d)', '', seg)
        # '... R>Unagi 400EA', 'R>white potion 250': a mid-line R> before a consumable buys it
        seg = re.sub(r'(?i)(?<=[\s·])R>\s*(?=\d*\s*(?:unagi|pure|water|white|blue|red|orange|mana|elixirs?|scrolls?|potions?|black|iron|ores?)\b)',
                     'B> ', seg)
        # '[Fairy Wing] Sell fairy wing PMO! Buy cromi I 50 wand PM'
        if re.match(r'(?i)\s*(?:sell(?:ing)?|wts)\s+.+?\b(?:pmo|pm)\b.*[!.]\s*(?:buy(?:ing)?|wtb)\s', seg):
            seg = re.sub(r'(?i)^\s*(?:sell(?:ing)?|wts)\s+', ' S> ', seg)
            seg = re.sub(r'(?i)(?<=[!.])\s*(?:buy(?:ing)?|wtb)\s+', ' B> ', seg)
        parts[i] = seg
    return re.sub(r'\s{2,}', ' ', ''.join(parts)).strip()


# ------------------------------------------------------------ stat posts
_STAT_RULES = [
    (r'\+?\s*(\d+)\s*crit(?:ical)?\s*(?:dmg|damage)', r'크리티컬 데미지 +\1'),
    (r'crit(?:ical)?\s*(?:dmg|damage)', '크리티컬 데미지'),
    (r'(?:att|attack|atk|wa)\s*\+\s*(\d+)', r'공격력 +\1'),
    (r'\+\s*(\d+)\s*(?:att|attack|atk|wa)\b', r'공격력 +\1'),
    (r'(?:matt|matk|ma)\s*\+\s*(\d+)', r'마력 +\1'),
    (r'cri(?:t|tical)?\s*\+\s*(\d+)', r'크리티컬 +\1'),
    (r'(\d+)\s*slots?\s*(?:left|remaining)', r'업그레이드 가능 \1회'),
    (r'(?:no|0)\s*slots?', '업그레이드 가능 0회'),
    (r'taking\s+offers?', '가격 제안 받습니다'),
    (r'(?:pm|dm|msg|whisper)\s+me|pmo', '귓말 주세요'),
    (r'\bcrt\b', '크리티컬'),
    (r'hit\s+me\s+up', '연락 주세요'),
    (r'(?:offer|offers)\s*(?:me|pls|please)?', '가격 제안 주세요'),
    (r'(?:level|lvl|lv)\s*(\d+)', r'\1레벨'),
    (r'ch(?:annel)?\s*(\d+)', r'\1채널'),
    (r'fm\s*(\d+)', r'자유시장 \1번 방'),
    (r'\b(?:sell|selling|s>|wts)\b', '팝니다'),
    (r'\b(?:buy|buying|b>|wtb)\b', '삽니다'),
    (r'\bearrings?\b', '귀고리'),
    (r'\bpole(?:arm)?s?\b', '폴암'),
    (r'\band\b', '·'),
    (r'\bobo\b', '가격 협의 가능'),
]
_STAT_RX = [(re.compile(p, re.I), r) for p, r in _STAT_RULES]


def item_stat_post(text: str) -> str | None:
    """'[에메랄드 귀고리] +4 crit damage and 3 slot left! taking offers' and
    '[노가다 목장갑] Sell/ attack+11 cri+2 36m': every English word must be
    understood, otherwise None (the sentence model takes the line)."""
    from .natural_trade import _money
    from .chat_cleanup import _TRADE_RX, _trade_ko, _ITEM_RX, _item_ko
    m = re.match(r'^\s*(\[[^\[\]\n]+\])?\s*(.+?)\s*$', text or '')
    if not m or not m.group(2):
        return None
    link, body = m.group(1) or '', m.group(2)
    if not re.search(r'(?i)crit|att|atk|slot|offer|\+\s*\d|sell|selling', body):
        return None
    value = body
    for rx, rep in _STAT_RX:
        value = rx.sub(rep, value)
    value = re.sub(r'(?<![\w.])(\d+(?:\.\d+)?)\s*([kKmMbB])\b', lambda x: _money(x.group(1)+x.group(2).lower()), value)
    value = _ITEM_RX.sub(lambda x: _item_ko(x.group(1)), value)
    value = _TRADE_RX.sub(lambda x: _trade_ko(x.group(1)), value)
    from .user_glossary import glossary_leftover
    value = glossary_leftover(body, value)
    if re.search(r'[A-Za-z]{2,}', value):
        return None          # something left we do not understand
    value = re.sub(r'\s*(?:/|\||!|,(?!\d))+\s*', ' · ', value)
    value = re.sub(r'(?:\s*·\s*){2,}', ' · ', value).strip(' ·')
    value = re.sub(r'\s{2,}', ' ', value)
    lead = re.match(r'^(팝니다|삽니다)\s*·?\s*(.+)$', value)
    contact = r'^(?:귓말 주세요|가격 제안 주세요|가격 제안 받습니다|연락 주세요|가격 협의 가능)[.\s]*$'
    if lead and not re.search(r'팝니다|삽니다', lead.group(2)) and not re.match(contact, lead.group(2)):
        value = lead.group(2).rstrip(' .')+' '+lead.group(1)
    value = re.sub(r'(팝니다|삽니다)\s+(?=[가-힣])', r'\1. ', value)
    if not re.search('[가-힣]', value):
        return None
    return (link+' '+value).strip() if link else value


# ------------------------------------------------------------ bare scroll
def bare_scroll_price(text: str) -> str | None:
    """'Pet Equip Speed Scroll 60%(53K)' typed without a link or marker."""
    m = re.fullmatch(r'(?i)\s*([A-Za-z][A-Za-z .]{2,40}?scroll(?:\s+for\s+[A-Za-z .]{2,30})?\s*\d{1,3}\s*%)'
                     r'\s*\(?\s*(\d+(?:\.\d+)?\s*[kKmM])\s*\)?[!.]*', text or '')
    if not m:
        return None
    from .scroll_intelligence import scroll_name
    ko = scroll_name('[' + re.sub(r'\s+', ' ', m.group(1)).strip() + ']')
    if not ko:
        return None
    from .natural_trade import _money
    price = re.sub(r"\s+", "", m.group(2)).lower()
    return f'{ko} {_money(price)}'


# ------------------------------------------------------------ game questions
_NOUNS = {'fame': '인기도', 'buff': '버프', 'buffs': '버프', 'leech': '쩔', 'carry': '캐리'}
def item_phrase(text: str, translate=None) -> str:
    """Korean for an item / place / skill phrase inside a question."""
    from .user_glossary import glossary_sentence, glossary_leftover
    from .chat_cleanup import polish_leftover
    value = re.sub(r'\s+', ' ', (text or '').strip(' ?!.~'))
    if value.lower() in _NOUNS:
        return _NOUNS[value.lower()]
    known = glossary_sentence(value)
    if known:
        return known
    if translate is not None and re.search(r'\d|\b(?:att|atk|slots?|clean|scroll)\b', value, re.I):
        # 'wg 10 att' reads best through the item/stat trade parser
        try:
            sold = translate('S> ' + value)
            sold = re.sub(r'\s*팝니다\.?$', '', sold).strip()
            if sold and '팝니다' not in sold and not re.search(r'[A-Za-z]{3,}', sold):
                return sold
        except Exception:
            pass
    out = re.sub(r'\s*삽니다$', '', polish_leftover(value + ' 삽니다'))
    out = glossary_leftover(value, out)
    try:
        from .market_item_terms import replace_market_items
        from .classic_item_index import current_index
        out = current_index().replace_verified(replace_market_items(out))
    except Exception:
        pass
    return out.strip()


_BUFFS = {'hb', 'hs', 'door', 'se', 'mw', 'haste', 'buff', 'buffs', 'bless', 'heal', 'res'}
_ROLES = {'cleric': '클레릭', 'priest': '프리스트', 'bishop': '비숍', 'sin': '어쌔신', 'hermit': '허밋',
          'dit': '시프', 'bandit': '시프', 'mage': '마법사', 'hunter': '헌터', 'xbow': '사수', 'archer': '궁수',
          'bowman': '궁수', 'warrior': '전사', 'fighter': '파이터', 'page': '페이지', 'spearman': '스피어맨',
          'thief': '도적', 'sader': '크루세이더', 'wk': '나이트', 'dk': '드래곤나이트', 'fp': '불독',
          'il': '썬콜', 'ranger': '레인저', 'sniper': '저격수', 'bucc': '바이퍼', 'sair': '캡틴', 'pirate': '해적'}


def game_question(text: str, translate=None) -> str | None:
    """'anyone selling hp pots?', 'pc gfa 60%?', 'how much for wg 10 att?',
    'any cleric for hb?', 'ign is X', 'sell me se?', 'anyone at nath?',
    'farming for dsg', 'leech at ulu 1 3m per hour', 'need door to fm'."""
    def phrase(x):
        return item_phrase(x, translate)

    value = re.sub(r'\s+', ' ', (text or '').strip()).strip(' ?!.~')
    low = value.lower()
    if not low or '[' in low or len(low) > 70:
        return None
    m = re.fullmatch(r"(?:any(?:one|1|body)?|who(?:'?s| is)?|anybody)\s+(selling|sells|sell|buying|buys|buy|has|have|got|with)\s+(.+)", low)
    if m:
        verb = {'sel': '파시는', 'buy': '사시는'}.get(m.group(1)[:3], '있으신')
        return f'{phrase(m.group(2))} {verb} 분 있나요?'
    m = (re.fullmatch(r'(?:pc|p/c|price\s*check)\s*(?:on|for)?\s+(.+)', low)
         or re.fullmatch(r"(?:what'?s|whats|wats|wat'?s)\s+(?:the\s+)?(?:pc|price)\s+(?:for|of|on)\s+(.+)", low))
    if m:
        return f'{phrase(m.group(1))} 시세 아시는 분?'
    m = re.fullmatch(r'(?:how\s+much|hm|hmuch)\s+(?:for|is|are|r)?\s*(?:a|an|the|ur|your)?\s*(.+)', low)
    if m and len(m.group(1)) > 1:
        return f'{phrase(m.group(1))} 얼마예요?'
    m = re.fullmatch(r'any(?:one|1)?\s+([a-z]+)\s+for\s+(.+)', low)
    if m and m.group(1) in _ROLES:
        target = m.group(2).strip()
        verb = '해 줄' if target.split()[0] in _BUFFS else '같이 갈'
        return f'{phrase(target)} {verb} {_ROLES[m.group(1)]} 있나요?'
    m = re.fullmatch(r'(?:my\s+)?ign\s*(?:is|:|=|-)?\s*([a-z0-9_]{3,13})', low)
    if m:
        name = re.search(re.escape(m.group(1)), value, re.I).group()
        return f'제 닉네임은 {name}이에요'
    if re.fullmatch(r'(?:pm|msg|whisper|dm)\s+me\s+(?:ur|your)\s+ign', low):
        return '닉네임 귓말로 알려 주세요'
    if re.fullmatch(r"(?:what'?s|whats)\s+(?:ur|your)\s+ign", low):
        return '닉네임이 뭐예요?'
    m = re.fullmatch(r'sell\s+me\s+(?:ur|your|a|an|the)?\s*(.+)', low)
    if m:
        return f'{phrase(m.group(1))} 파실래요?'
    m = re.fullmatch(r'buy\s+(?:my|mine)\s+(.+)', low)
    if m:
        return f'제 {phrase(m.group(1))} 사실래요?'
    m = re.fullmatch(r'any(?:one|1|body)?\s+(?:at|in)\s+(.+)', low)
    if m:
        return f'{phrase(m.group(1))}에 계신 분 있나요?'
    m = re.fullmatch(r'(?:farming|hunting|grinding|killing|training)\s+(?:for\s+|at\s+|in\s+)?(.+)', low)
    if m:
        return f'{phrase(m.group(1))} 사냥 중이에요'
    m = re.fullmatch(r'(?:(s>|selling|wts|b>|buying|wtb)\s*)?(split\s+|solo\s+)?leech(?:ing)?\s+(?:at|@|in)\s+'
                     r'(.+?)(?:\s+(\d+(?:\.\d+)?\s*[kmb]))?(?:\s*(?:/|per|an|a)\s*(?:hr|hour|h))?', low)
    if m:
        kind = {'split': '분할 ', 'solo': '단독 '}.get((m.group(2) or '').strip(), '')
        price = f' (시간당 {_money_text(m.group(4))})' if m.group(4) else ''
        side = (m.group(1) or '').strip()
        verb = ' 팝니다' if side in ('s>', 'selling', 'wts') else ' 삽니다' if side else ''
        return f'{phrase(m.group(3))} {kind}쩔{verb}{price}'.replace('  ', ' ').strip()
    m = re.fullmatch(r'(?:need|anyone\s+(?:has|have|with)|any)\s+(?:a\s+)?door\s+(?:to\s+)?(.+)', low)
    if m:
        return f'{phrase(m.group(1))} 가는 미스틱 도어 필요해요'
    return None


def _money_text(value: str) -> str:
    from .natural_trade import _money
    return _money(re.sub(r'\s+', '', value).lower())


# ------------------------------------------------------------ casual
_SHORT_WORDS = {
    'always': '항상', 'never': '절대 안 돼요', 'maybe': '아마도요', 'sure': '그래요',
    'nope': '아니요', 'yep': '네', 'yup': '네', 'ing': '진행 중', 'done': '끝났어요',
    'here': '여기요', 'coming': '가는 중이에요', 'omw': '가는 중이에요', 'wait': '잠깐만요',
    'really': '진짜요?', 'why': '왜요?', 'where': '어디요?', 'when': '언제요?', 'who': '누구요?',
    'how': '어떻게요?', 'what': '뭐요?', 'same': '저도요', 'me too': '저도요', 'me': '저요',
    'damn': '젠장', 'how many': '몇 개요?', 'i mean': '제 말은', 'where is he': '그 사람 어디 있어요?',
    'where is she': '그 사람 어디 있어요?', 'where r u': '어디예요?', 'where are you': '어디예요?',
    "ill add you": '추가할게요', "i'll add you": '추가할게요', 'ill join': '참가할게요', "i'll join": '참가할게요',
}


_RMT = re.compile(r'(?i)hotsale|lowest\s+price\s+\d|\$\s?\d+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\s?usd\b|safe\s+mesos|cheap\s+mesos'
                  r'|mscw\s*-?\s*for\s*\d+\s*%\s*off|\bU4N\b|/\s*TW\b.*mesos|mesos?\s*price\s+low')


def rmt_advert(text: str) -> str | None:
    """Mesos-for-money adverts ('WWW. U4N... Mesos Hotsale. Lowest Price 100K
    only $4'): shown as an advert, not translated word by word."""
    if text and _RMT.search(text) and re.search(r'(?i)meso|mscw|u4n|www\.', text):
        return '[메소 현금 거래 광고]'
    return None


def casual_request(text: str) -> str | None:
    value = re.sub(r'\s+', ' ', (text or '').strip()).strip(' .!?~@')
    low = value.lower()
    if low in _SHORT_WORDS:
        return _SHORT_WORDS[low]
    # R18 live chat (the model said '나 를 추가', '관련 기사', 'pq에 가입')
    m = re.fullmatch(r'(?i)(?:pls\s+|please\s+)?add\s+me(?:\s+pls|\s+please)?(?:[,.\s]+(?:i\'?m\s+)?(?:level|lvl|lv)\s*(\d{1,3}))?', value)
    if m:
        return '저 추가해 주세요' + (f' (레벨 {m.group(1)})' if m.group(1) else '')
    m = re.fullmatch(r'(?i)(?:(\w{3,})\s+)?leave\s+(?:the\s+)?(?:pt|party)(?:\s+(idiot|noob|stupid|pls|please|now))?', value)
    if m:
        who = f'{m.group(1)} ' if m.group(1) and m.group(1).lower() not in ('pls', 'please') else ''
        tail = {'idiot': ', 바보야', 'noob': ', 뉴비야', 'stupid': ', 바보야'}.get((m.group(2) or '').lower(), '')
        if who or tail:
            return f'{who}파티에서 나가{tail}'
        return '파티 나갈게요' if not m.group(2) else '파티에서 나가 주세요'
    if re.fullmatch(r"(?i)let[\"'’]?\s?s\s+go+o*", value):
        return '가자!'
    m = re.fullmatch(r'(?i)(\S+?)\s*<+\s*spot\s*steal(?:er|ing)?', value)
    if m:
        return f'{m.group(1)} 자리 도둑이에요'
    m = re.fullmatch(r'(?i)(?:R\s*>\s*|lf\s*|need\s+)(\d)\s+(?:more|ppl|people)(?:\s+(?:pls|plz))?', value)
    if m:
        return f'{m.group(1)}명 더 구해요'                         # 'R> 2 more'
    m = re.fullmatch(r'(?i)(?:looking|lf)\s+for\s+(\d)\s+(?:ppl|people|more|players?)(?:\s+(?:for|in)\s+(?:a\s+|the\s+|my\s+)?(?:party|pt))?', value)
    if m:
        return f'파티원 {m.group(1)}명 구해요'
    # R19 audit: the model read these as '휠 CH10', '지원하다', '감사합니다.'
    m = re.fullmatch(r'(?i)(?:pls\s+|plz\s+)?(?:whisper|whisp|wisp)(?:\s+me)?(?:\s+(?:pls|plz))?'
                     r'(?:\s*(?:@|in|on)?\s*(?:ch|channel|cc)\.?\s*(\d{1,2}))?', value)
    if m:
        return '귓말 주세요' + (f' ({m.group(1)}채널)' if m.group(1) else '')
    if re.fullmatch(r'(?i)(?:(?:pls|plz|please)\s+)?help(?:\s+me)?(?:\s+(?:pls|plz|please))?', value) \
            and value.lower() != 'help':
        return '도와주세요'
    m = re.fullmatch(r'(?i)([a-z][a-z0-9_]{2,12})[,\s]+(?:pls|plz|please)\s+help(?:\s+me)?', value)
    if m:
        return f'{m.group(1)}, 도와주세요'
    m = re.fullmatch(r'(?i)(?:can|could)\s+(you|u|any\s*(?:one|1|body)|some\s*(?:one|1|body))\s+help(?:\s+me)?'
                     r'(?:\s+(?:pls|plz|please))?', value)
    if m:
        return '도와줄 수 있어요?' if m.group(1).lower() in ('you', 'u') else '도와주실 분 있나요?'
    if re.fullmatch(r'(?i)(?:i\s+)?need\s+(?:some\s+)?help(?:\s+(?:pls|plz))?', value):
        return '도움이 필요해요'
    m = re.fullmatch(r'(?i)(?:looking\s+for|searching\s+for|lf|lfg)\s+(?:an?\s+)?(?:(gpq|active|chill|friendly|new|'
                     r'small|big|good|nice|fun)\s+)?guild(?:\s+(?:pls|plz|to\s+join))?', value)
    if m:
        kind = {'gpq': '길드 퀘스트 하는 ', 'active': '활동적인 ', 'chill': '편한 ', 'friendly': '친절한 ',
                'new': '새 ', 'small': '작은 ', 'big': '큰 ', 'good': '좋은 ', 'nice': '좋은 ',
                'fun': '재밌는 '}.get((m.group(1) or '').lower(), '')
        return f'{kind}길드 찾아요'
    m = re.fullmatch(r'(?i)(?:(?:do\s+)?(?:you|u|ya)\s+)?(?:wanna|want\s+to)\s+(?:go\s+|do\s+)?(kpq|lpq|opq|gpq|pq|party|pt|'
                     r'hunt|trade|duo|level|lvl|train)(?:\s+together|\s+with\s+me)?', value)
    if m:
        what = {'kpq': '커닝 파퀘 갈래요?', 'lpq': '루디 파퀘 갈래요?', 'opq': '오르비스 파퀘 갈래요?',
                'gpq': '길드 퀘스트 갈래요?', 'pq': '파티 퀘스트 갈래요?', 'party': '파티 할래요?', 'pt': '파티 할래요?',
                'hunt': '같이 사냥할래요?', 'trade': '거래할래요?', 'duo': '같이 듀오 사냥할래요?',
                'level': '같이 레벨업 할래요?', 'lvl': '같이 레벨업 할래요?', 'train': '같이 사냥할래요?'}
        return what[m.group(1).lower()]
    m = re.fullmatch(r'(?i)i\s+(?:just\s+|really\s+)?(?:wanna|want\s+to)\s+(?:do\s+|go\s+(?:to\s+)?)?(?:the\s+|a\s+)?'
                     r'(bonus(?:\s+(?:round|stage|map))?|sleep|go\s+home|level(?:\s+up)?|lvl|quit|rest|eat|cry)', value)
    if m:
        key = m.group(1).lower().split()[0]
        return {'bonus': '보너스 구간 하고 싶어요', 'sleep': '자고 싶어요', 'go': '집에 가고 싶어요',
                'level': '레벨업 하고 싶어요', 'lvl': '레벨업 하고 싶어요', 'quit': '접고 싶어요',
                'rest': '쉬고 싶어요', 'eat': '밥 먹고 싶어요', 'cry': '울고 싶어요'}[key]
    m = re.fullmatch(r'(?i)(?:any\s*(?:one|1|body)\s+)?(?:have\s+|got\s+)?(?:a\s+|any\s+|some\s+)?spare\s+'
                     r'(mp|hp|mana|white|blue|red|orange)?\s*(?:pots?|potions?)\s*\??'
                     r'(?:\s*(?:i\s+)?ran\s+out\s+(?:of\s+)?(mesos?|money|pots?|potions?))?\s*(ty|thx|thanks|tyvm)?\W*', value)
    if m:
        kind = {'mp': 'MP 포션', 'hp': 'HP 포션', 'mana': '마나 포션', 'white': '하얀 포션', 'blue': '파란 포션',
                'red': '빨간 포션', 'orange': '주황 포션'}.get((m.group(1) or '').lower(), '포션')
        out = f'{kind} 남는 분 있나요?'
        if m.group(2):
            out += ' 메소가 다 떨어졌어요' if m.group(2).lower().startswith(('meso', 'money')) else ' 포션이 다 떨어졌어요'
        return out + (' 고마워요' if m.group(3) else '')
    m = re.fullmatch(r'(?i)(?:\[[^\]]*\]\s*\]?\s*)?(?:gz|grats|gratz|congrats|congratz)\s+([a-z0-9_]{2,13})\s+(?:on|for)\s+'
                     r'(?:level|lvl|lv)\s*(\d{1,3})(?:\s*#\w+)?', value)
    if m:
        return f'{m.group(1)} 님 {m.group(2)}레벨 축하해요'
    m = re.fullmatch(r'(?i)add\s+([a-z0-9_]{3,13})', value)
    if m and m.group(1).lower() not in ('you', 'him', 'her', 'them', 'pls', 'please'):
        return f'{m.group(1)} 친구 추가해 주세요'
    if len(value) <= 60 and re.search(r'(?i)\bfame\s*(?:4|for)\s*fame\b', value):
        return '맞인기도 해요 (서로 인기도 올려 주기)'
    if re.fullmatch(r'(?i)(?:trade\s+fame|fame\s*(?:4|for)\s*fame|f4f)\s*(?:any(?:one|1)?)?', value):
        return '맞인기도 하실 분 있나요?'
    if re.fullmatch(r'(?i)(?:i\s+)?sent\s+(?:the\s+|an?\s+)?inv(?:ite)?(?:\s+again)?', value):
        return '초대 다시 보냈어요' if 'again' in value.lower() else '초대 보냈어요'
    m = re.fullmatch(r'(?i)([a-z][a-z0-9_]{2,12})\s+me', value)
    if m and m.group(1).lower() not in ('add', 'pm', 'msg', 'inv', 'carry', 'buff', 'trade', 'tell', 'call',
                                        'help', 'show', 'give', 'let', 'sell', 'whisper', 'dm', 'invite', 'hb', 'hs'):
        return f'{m.group(1)}, 저요'
    m = re.fullmatch(r'(?i)leave\s+(?:the\s+)?(?:pt|party)\s+(\w{3,})', value)
    if m and m.group(1).lower() not in ('pls', 'please', 'now', 'idiot', 'noob', 'stupid'):
        return f'{m.group(1)}, 파티에서 나가 주세요'
    m = re.fullmatch(r"(?i)(?:(\w{3,})\s+)?(?:you'?re|youre|ur|u r)\s+in\s+(?:the\s+|my\s+)?(?:pt|party)", value)
    if m:
        return (f'{m.group(1)}, ' if m.group(1) else '') + '파티에 들어왔어요'
    if re.fullmatch(r"(?i)i'?m\s+not\s+in\s+(?:a\s+|the\s+)?(?:pt|party)", value):
        return '저 파티에 없어요'
    m = re.fullmatch(r'(?i)(?:i\'?m\s+)?join(?:ing|in)?\s+(k|l)?(pq|pt|party)', value)
    if m:
        name = {'k': '커닝 파퀘', 'l': '루디 파퀘'}.get((m.group(1) or '').lower(),
                                                      '파티' if m.group(2).lower() != 'pq' else '파티 퀘스트')
        return f'{name} 참가할게요'
    if re.fullmatch(r'(?i)f?[a-z]?ame\s*(?:4|for)\s*fame|f4f', value):
        return '맞인기도 해요 (서로 인기도 올려 주기)'
    m = re.fullmatch(r'(?i)any\s*(?:one|1|body)\s+(?:can\s+|could\s+)?help\s+me\s+(?:with\s+)?(.+?)'
                     r'(?:\s+by\s+any\s+chance)?\??', value)
    if m:
        what = re.sub(r'(?i)^(?:some|a|an|the)\s+', '', m.group(1)).strip()
        from .user_glossary import glossary_sentence
        ko = glossary_sentence(what)
        if ko is None:
            from .chat_cleanup import polish_leftover
            ko = polish_leftover(what+' 삽니다').replace(' 삽니다', '')
        return f'혹시 {ko} 좀 도와주실 분 있나요?'
    return None


# ------------------------------------------------------------ hallucination
_HALLUCINATIONS = {'뚱 베어', '인기 카테고리', '프로젝트', '오크나무', '판매가격', '이름 *',
                   '토토사이트', '팟캐스트', '사이트맵', '미즈데라', '· .'}   # R19 audit: unknown words


def guard_hallucination(source: str, result: str) -> str:
    """Known nonsense the offline model emits for unknown short words."""
    out = (result or '').strip()
    if out.strip(' !~.') in _HALLUCINATIONS or '뚱 베어' in out and '뚱' not in source:
        return source.strip()
    # R18 live: 'O O' / 'J-oq!!' -> '₢ 킹', 'ing@' -> '(주)에이치',
    # 'J-ng' -> 'J-ng, 영국': symbols and names the source never had
    # R19 audit: OCR crumbs after a party post came back as 'ღ♥ღ❤ღ❤️'
    if re.search(r'[ღ♥❤♡]', out) and not re.search(r'[ღ♥❤♡]', source or ''):
        out = re.sub(r'[ღ♥❤♡\ufe0f]+', '', out).strip(' ·')
        if not re.search(r'[가-힣A-Za-z0-9]', out):
            return source.strip()
    for junk in ('₢', '(주)'):
        if junk in out and junk not in (source or ''):
            return source.strip()
    out = re.sub(r',\s*(?:영국|미국|일본|중국|프랑스|독일)$', '', out)
    if out.endswith('의 특징') and 'feature' not in (source or '').lower():
        out = out[:-len('의 특징')].rstrip()
    return out
