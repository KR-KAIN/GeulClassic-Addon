"""Use observed word confidence and numeric agreement, never fuzzy digit fixes."""
import re
from collections import Counter
from .trade_stats import critical_spans,numeric_signature,_PAIR,_GEAR_RX,_GEARS,_SHORT_STATS,_stat

_DOMAIN=re.compile(r'(?i)(?<![A-Za-z])(?:att|atk|attk|watk|watt|matk|matt|attack|gfa|gma|scrolls?|scr)(?![A-Za-z])|공격력|마력|주문서')
_GEAR_FIELD=re.compile(r'(?i)\b(?:gloves?|claw|wand|staff|dagger|sword|cape|overall|shoes?)\s+(\S{2,12})')
_AMBIGUOUS_PRICE=re.compile(r'(?i)(?<!\w)\d[\dO]*O[\dO]*[kmb](?!\w)')


def price_read_resolves(base, alternate):
    """Choose a real alternate OCR read of 50K over 5OK, never invent one."""
    if not _AMBIGUOUS_PRICE.search(base[0]) or alternate[1]<max(.85,base[1]-.03):
        return False
    normalized=_AMBIGUOUS_PRICE.sub(lambda m:re.sub('[Oo]','0',m.group()),base[0])
    return re.sub(r'\s+','',normalized)==re.sub(r'\s+','',alternate[0])


def known_terms(text):
    # Rank only terms literally present in a real candidate; never replace a
    # guessed glyph with the closest dictionary word or alter a digit.
    found={}
    for m in _PAIR.finditer(text):
        found[m.span(1)]=('gear',_GEARS[m.group(1).casefold()])
        found[m.span(2)]=('stat',_stat(m.group(2)))
    for m in re.finditer(r'(?<![A-Za-z_])('+_GEAR_RX+r')(?![A-Za-z_])',text,re.I):
        found[m.span()]=('gear',_GEARS[m.group().casefold()])
    for m in _SHORT_STATS.finditer(text):found[m.span()]=('stat',_stat(m.group()))
    for m in re.finditer(r'(?i)(?<![A-Za-z_])(?:scrolls?|scr)(?![A-Za-z_])',text):found[m.span()]=('scroll','scroll')
    for m in re.finditer(r'(?i)(?<![A-Za-z_])(?:kfan|korean\s+fan|gfa|gma)(?![A-Za-z_])',text):
        value=re.sub(r'\s+',' ',m.group().casefold())
        found[m.span()]=('alias','kfan' if value=='korean fan' else value)
    return Counter(found.values())


def loses_known_terms(base,alternate):
    return bool(known_terms(base)-known_terms(alternate))


def critical_floor(text, confidences):
    if len(confidences)!=len(text):return None
    spans=critical_spans(text)
    spans += [m.span(1) for m in _GEAR_FIELD.finditer(text)]
    values=[float(confidences[i]) for a,b in spans for i in range(a,b) if not text[i].isspace()]
    return min(values) if values else None


def needs_critical_retry(text, confidences):
    if _AMBIGUOUS_PRICE.search(text):
        return True
    relevant=bool(_DOMAIN.search(text) or (_GEAR_FIELD.search(text) and re.search(r'\d\s*%',text)))
    floor=critical_floor(text,confidences) if relevant else None
    return floor is not None and floor<.82


def same_numeric_fields(a,b):
    return numeric_signature(a)==numeric_signature(b)


def prefer_critical_read(base, alternate, base_confidences, alt_confidences):
    if not same_numeric_fields(base[0],alternate[0]):return False
    if loses_known_terms(base[0],alternate[0]):return False
    before=critical_floor(base[0],base_confidences)
    after=critical_floor(alternate[0],alt_confidences)
    return (before is not None and after is not None and after>before+.08 and
            alternate[1]>=base[1]-.02)
