"""Literal gear/stat translation; keep every observed bonus and success rate.

No numeric OCR correction and no invented scroll type. Korean item links are
authoritative and unknown English item links remain visible.
"""
from __future__ import annotations
import re
from collections import Counter

_GEARS={'glove':'장갑','gloves':'장갑','claw':'아대','dagger':'단검',
        'sword':'검','1h sword':'한손검','2h sword':'두손검','one-handed sword':'한손검',
        'one handed sword':'한손검','shield':'방패','cape':'망토','bow':'활',
        'crossbow':'석궁','xbow':'석궁','staff':'스태프','wand':'완드','spear':'창',
        'polearm':'폴암','pole arm':'폴암','shoe':'신발','shoes':'신발',
        'earring':'귀고리','earrings':'귀고리','helmet':'투구','hat':'모자',
        'overall':'전신갑옷','top':'상의','bottom':'하의','pants':'하의'}
_GEARS.update({'1h axe':'한손도끼','2h axe':'두손도끼','1h bw':'한손둔기','2h bw':'두손둔기',
               'knuckle':'너클','gun':'건','topwear':'상의','bottomwear':'하의','pet equip':'펫 장비','pet equipment':'펫 장비'})
_GEAR_RX='|'.join(re.escape(x) for x in sorted(_GEARS,key=len,reverse=True))
_MAGIC=r'(?:magic\s*(?:attack|att|atk)|m\s*\.\s*(?:attack|att|atk)|matk|matt)'
_WEAPON=r'(?:weapon\s*(?:attack|att|atk)|w\s*\.\s*(?:attack|att|atk)|watk|watt|attk|atk|att|wa)'
_SHORT_STATS=re.compile(r'(?<![A-Za-z_])('+_MAGIC+'|'+_WEAPON+r')(?![A-Za-z_])',re.I)
_STAT_VALUE=re.compile(r'(?<![A-Za-z_])(?:\d+\s*(?:'+_MAGIC+'|'+_WEAPON+r')(?![A-Za-z_])|(?:'+_MAGIC+'|'+_WEAPON+r')\s*[+＋−-]?\s*\d+)',re.I)
_ALL_STATS=r'(?:'+_MAGIC+'|'+_WEAPON+r'|attack|defen[cs]e|def|dex|str|int|luk|hp|mp|accuracy|acc|avoid|evasion|speed|spd|jump|crit(?:ical)?)'
_LABELS={'attack':'공격력','defense':'방어력','defence':'방어력','def':'방어력',
         'dex':'민첩','str':'힘','int':'지력','luk':'행운','hp':'체력','mp':'마나',
         'accuracy':'명중률','acc':'명중률','avoid':'회피율','evasion':'회피율',
         'speed':'이동속도','spd':'이동속도','jump':'점프력','crit':'크리티컬','critical':'크리티컬'}
_PAIR=re.compile(r'(?<![A-Za-z_])('+_GEAR_RX+r')\s*(?:for\s+)?('+_ALL_STATS+r')(?![A-Za-z_])',re.I)
_SCROLL=re.compile(r'(?<![A-Za-z_])('+_GEAR_RX+r')\s*(?:for\s+)?('+_ALL_STATS+r')\s*'
                   r'([+＋−-]\s*\d{1,3}\s+)?(100|70|60|30|10|1)\s*[%％]'
                   r'(?:\s+(?:scrolls?|scr)\b)?',re.I)
_TIER_SCROLL=re.compile(r'(?<![A-Za-z_])('+_GEAR_RX+r')\s+(?:for\s+)?('+_ALL_STATS+r')'
                        r'\s+(?:scroll\s*[:;]?\s*)?(lesser|intermediate|greater)\b',re.I)
_ALIAS_SCROLL=re.compile(r'(?<![A-Za-z_])(gfa|gma)(?![A-Za-z_])(?:\s*(100|70|60|30|10|1)\s*[%％])?',re.I)
_ATTR_VALUE=re.compile(r'(?i)(?<![A-Za-z_])(?:\d+\s*(?:dex|str|int|luk|hp|mp|def|acc|avoid|spd|jump|crit)\b|(?:dex|str|int|luk|hp|mp|def|acc|avoid|spd|jump|crit)\s*[+−-]?\s*\d+)')
_DEAL=re.compile(r'^\s*((?:\[[^\]\r\n]+\]\s*)*)(S\s*>|B\s*>|WTS\b|WTB\b|selling\b|buying\b)\s*(.+)$',re.I|re.S)
_LINKS=re.compile(r'(\[[^\[\]\r\n]+\])')
_CRITICAL=re.compile(r'(?<![A-Za-z_])(?:'+_MAGIC+'|'+_WEAPON+r'|attack|gfa|gma|scrolls?|scr)(?![A-Za-z_])|[+＋−-]\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*[%％]',re.I)


def _stat(word):
    key=re.sub(r'\s+',' ',word.casefold()).strip()
    if re.fullmatch(_MAGIC,key,re.I):return '마력'
    if re.fullmatch(_WEAPON,key,re.I):return '공격력'
    return _LABELS.get(key,word)


def alternative_stat_offers(text):
    """Read a fully consumed series of stat/price alternatives.

    The video has both '+8magicatk for 300k +12magicatk for600k' and
    'atk+7 400K +8 550K'. Retain signed stats and their respective prices.
    Bare B/S is accepted only with this complete two-option grammar.
    """
    deal=re.fullmatch(r'([BS])\s*(?:>\s*)?(.+)',text,re.I)
    if not deal:
        return None
    verb,body=deal.groups()
    stat=r'(?:'+_MAGIC+'|'+_WEAPON+r')'
    option=re.compile(r'(?:(?P<before>'+stat+r')\s*)?'
        r'(?P<value>[+]\s*\d+)\s*(?P<after>'+stat+r')?\s*'
        r'(?:for\s*)?(?P<price>\d+(?:\.\d+)?\s*[kmb])\b',re.I)
    matches=list(option.finditer(body))
    if not 2<=len(matches)<=8:
        return None
    name=body[:matches[0].start()].strip()
    if not name or not re.search('[A-Za-z가-힣]',name):
        return None
    cursor=matches[0].start()
    last_stat=None
    output=[]
    from .natural_trade import _item, _money
    for match in matches:
        if body[cursor:match.start()].strip():
            return None
        if match.group('before') and match.group('after'):
            return None
        label=match.group('before') or match.group('after')
        if label:
            last_stat=_stat(label)
        if last_stat is None:
            return None
        value=re.sub(r'\s+','',match.group('value'))
        output.append(f'{last_stat} {value}: {_money(match.group("price"))}')
        cursor=match.end()
    if body[cursor:].strip(' .!'):
        return None
    name=re.sub(r'(?i)^([0-9]+)\s*lv\b',r'\1레벨',name)
    action='삽니다' if verb.upper()=='B' else '팝니다'
    return _item(name)+' '+action+'. '+' / '.join(output)


def critical_spans(text):
    return [(m.start(),m.end()) for m in _CRITICAL.finditer(text)]


def numeric_signature(text):
    """Prices/levels/bonuses/rates must agree before adopting an OCR retry."""
    text=str(text).translate(str.maketrans({'％':'%','＋':'+','−':'-'}))
    return (tuple(re.findall(r'\d+(?:[.,]\d+)*',text)),
            tuple(re.sub(r'\s+','',v) for v in re.findall(r'\d+(?:\.\d+)?\s*%',text)),
            tuple(re.sub(r'\s+','',v) for v in re.findall(r'(?<!\d)[+-]\s*\d+(?:\.\d+)?',text)))


def stat_signature(text):
    labels=r'공격력|마력|민첩|힘|지력|행운|방어력|체력|마나|명중률|회피율|이동속도|점프력|크리티컬'
    number=r'[+＋−-]?\s*\d+(?:\.\d+)?'
    pairs=[]
    for m in re.finditer(r'('+labels+r')\s*('+number+r')(?![\d.]|\s*[kmb%％])',text,re.I):
        pairs.append((m.group(1),re.sub(r'\s+','',m.group(2))))
    for m in re.finditer(r'(?<![\d.])('+number+r')\s*('+labels+r')',text):
        pairs.append((m.group(2),re.sub(r'\s+','',m.group(1))))
    return Counter(pairs)


def _plain_terms(text):
    # Short labels are only expanded alongside an observed numeric stat.
    text=re.sub(r'(?i)\bCRI(?=\s*[+−-]?\s*\d)','크리티컬',text)
    text=re.sub(r'(?i)(?<=\d)\s*CRI\b',' 크리티컬',text)
    text=re.sub(r'(?i)\bCD(?=\s*[+−-]?\s*\d)','크리티컬 데미지',text)
    text=re.sub(r'(?i)(?<=\d)\s*CD\b',' 크리티컬 데미지',text)
    text=re.sub(r'(?i)\bwork\s+gloves?\b','노가다 목장갑',text)
    def scroll(m):
        bonus=(m.group(3).strip()+' ') if m.group(3) else ''
        return _GEARS[m.group(1).casefold()]+' '+_stat(m.group(2))+' '+bonus+m.group(4)+'% 주문서'
    text=_SCROLL.sub(scroll,text)
    from .scroll_intelligence import scroll_name
    text=_TIER_SCROLL.sub(lambda m:scroll_name(m.group()) or m.group(),text)
    text=_ALIAS_SCROLL.sub(lambda m:('장갑 공격력' if m.group(1).casefold()=='gfa' else '장갑 마력')+
                          (' '+m.group(2)+'%' if m.group(2) else '')+' 주문서',text)
    text=_PAIR.sub(lambda m:_GEARS[m.group(1).casefold()]+' '+_stat(m.group(2)),text)
    text=re.sub(r'(?i)\bcrit(?:ical)?\s+(?:dmg|damage)\b','크리티컬 데미지',text)
    text=_SHORT_STATS.sub(lambda m:_stat(m.group()),text)
    # The full word "attack" is a stat only with a numeric field or colon.
    text=re.sub(r'(?i)(?<![A-Za-z_])attack(?=\s*(?:[+−-]?\s*\d|:))','공격력',text)
    text=re.sub(r'(?i)(?<=\d)\s*attack\b',' 공격력',text)
    for label in ('dex','str','int','luk','hp','mp','def','acc','avoid','spd','jump','crit'):
        text=re.sub(r'(?i)(?<![A-Za-z_])'+label+r'(?=\s*[+−-]?\s*\d)',_LABELS[label],text)
        text=re.sub(r'(?i)(?<=\d)\s*'+label+r'\b',' '+_LABELS[label],text)
    text=re.sub(r'(?i)(?<!\w)k\s*-?\s*fan(?![A-Za-z_])','태극부채',text)
    text=re.sub(r'(?i)\bWG\b','노가다 목장갑',text)
    # A generic gear word here is explicitly in a stat/scroll transaction.
    text=re.sub(r'(?<![A-Za-z_])('+_GEAR_RX+r')(?![A-Za-z_])',lambda m:_GEARS[m.group().casefold()],text,flags=re.I)
    text=re.sub(r'(?i)\b(?:scrolls?|scr)\b','주문서',text)
    text=re.sub(r'(?<=\d)(?=공격력|마력|민첩|힘|지력|행운)',' ',text)
    text=re.sub(r'(공격력|마력|민첩|힘|지력|행운)(?=\d)',r'\1 ',text)
    return text


def _link_terms(link):
    if re.search('[가-힣]',link):
        from .item_link_protection import protect_hangul_links
        return protect_hangul_links(link)
    from .megaphone_item_translation import localized_item_text
    known=localized_item_text(link)
    if known!=link:return known
    known=known_scroll_link(link)
    if known!=link:return known
    inner=link[1:-1]
    # Translate a fully recognized field label literally, including clipped
    # '[Attack:]'. Do not fabricate the missing equipment or success rate.
    m=re.fullmatch(r'\s*('+_ALL_STATS+r')\s*:\s*('+_GEAR_RX+r')?\s*',inner,re.I)
    if m:
        return '['+_stat(m.group(1))+':'+(' '+_GEARS[m.group(2).casefold()] if m.group(2) else '')+']'
    return link


def known_scroll_link(link):
    if re.search('[가-힣]',link):return link
    from .scroll_intelligence import scroll_name
    label=scroll_name(link)
    if label:return '['+label+']'
    inner=link[1:-1]
    if _SCROLL.fullmatch(inner.strip()):
        return '['+_plain_terms(inner.strip())+']'
    return link


def localize_stat_terms(text):
    parts=_LINKS.split(text)
    for i,part in enumerate(parts):
        parts[i]=_link_terms(part) if i%2 else _plain_terms(part)
    return ''.join(parts)


def translate_stat_trade(text):
    deal=_DEAL.fullmatch(text)
    if not deal:return None
    from .chat_shorthand import trade_suffix
    if trade_suffix(text) is not None:return None
    prefix,verb,body=deal.groups()
    from .megaphone_item_translation import _EQUIPMENT_STATS
    if _EQUIPMENT_STATS.search(body):return None
    # Keep established single-scroll/exact-form wording; this path handles
    # the mixed or stat-bearing listings the old full-match parser missed.
    from .scroll_intelligence import scroll_trade
    if scroll_trade(text) is not None:return None
    if not (re.search('공격력|마력',body) or _STAT_VALUE.search(body) or _PAIR.search(body) or
            _ALIAS_SCROLL.search(body) or _ATTR_VALUE.search(body) or re.search(r'(?i)\battack\s*[:+\d]',body)):
        return None
    localized=localize_stat_terms(body)
    from .natural_trade import trade_override
    action='팝니다' if verb.lower().replace(' ','') in ('s>','wts','selling') else '삽니다'
    translated=trade_override(verb+' '+localized) or localized+' '+action
    # A downstream trade shortcut may format money, but may not drop a rate
    # or change +1 into +2 / treat an enhancement marker as attack points.
    original_sig=numeric_signature(localized)
    candidate_sig=numeric_signature(translated)
    if original_sig[1:]!=candidate_sig[1:] or stat_signature(localized)!=stat_signature(translated):
        translated=localized+' '+action
    if prefix.strip():
        translated=localize_stat_terms(prefix.strip())+' · '+translated
    return translated
