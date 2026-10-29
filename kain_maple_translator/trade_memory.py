"""Validated trade templates and lossless item/number slots for local MT."""
from collections import OrderedDict
from dataclasses import dataclass
import re

from .glossary import money_ko

_SLOT = re.compile(r'\[[^\[\]\r\n]{1,100}\]|(?<![\w.])\d+(?:[.,]\d+)*(?:\s*[kmb](?!\w)|\s*%)?(?!\w)', re.I)
_PRICE = re.compile(r'^\d+(?:\.\d+)?\s*[kmb]$', re.I)


@dataclass(frozen=True)
class Slot:
    marker: str
    kind: str
    source: str


@dataclass
class ProtectedText:
    masked: str
    slots: list

    def values(self):
        from .megaphone_item_translation import localized_item_text
        return {slot.marker: (localized_item_text(slot.source) if slot.kind == 'item'
                 else money_ko(slot.source) if slot.kind == 'price' else slot.source)
                for slot in self.slots}

    def restore(self, result):
        # Every marker must survive exactly once. Duplicate/deleted/foreign
        # slots are rejected; an item or amount is never guessed back in.
        expected = [slot.marker for slot in self.slots]
        result = re.sub(r'(?i)kain(?:item|price|number)[a-z]+token', lambda m: m.group().upper(), result or '')
        found = re.findall(r'KAIN(?:ITEM|PRICE|NUMBER)[A-Z]+TOKEN', result)
        if sorted(found) != sorted(expected):
            return None
        if re.findall(r'\d+(?:[.,]\d+)*',result) != re.findall(r'\d+(?:[.,]\d+)*',self.masked):
            return None
        values = self.values()
        for marker in expected:
            result = result.replace(marker, values[marker])
        return result


def protect_values(text):
    if 'KAINTOKEN' in text or re.search(r'KAIN(?:ITEM|PRICE|NUMBER)[A-Z]+TOKEN', text):
        return ProtectedText(text, [])
    slots = []
    def replace(match):
        raw = match.group()
        kind = 'item' if raw.startswith('[') else 'price' if _PRICE.fullmatch(raw) else 'number'
        # Alphabetic IDs avoid a model treating slot IDs as numeric amounts.
        n = len(slots)
        label = ''
        while True:
            label = chr(65+n%26)+label
            n = n//26-1
            if n < 0:
                break
        marker = 'KAIN'+kind.upper()+label+'TOKEN'
        slots.append(Slot(marker, kind, raw))
        return marker
    return ProtectedText(_SLOT.sub(replace, text), slots)


def safe_slot_translation(plan, translate):
    """Translate masked context; use anchored clauses if a marker is lost.

    Fallback NEVER submits the real item/price to the model. Each surrounding
    text fragment is translated separately and the original slots restored.
    """
    if not plan.slots:
        return translate(plan.masked)
    try:
        candidate = translate(plan.masked)
    except Exception as ex:
        if not getattr(ex, 'recoverable_translation_failure', False):
            raise
        candidate = ''
    restored = plan.restore(candidate)
    if restored is not None:
        return restored
    pieces = re.split('('+'|'.join(re.escape(s.marker) for s in plan.slots)+')', plan.masked)
    values = plan.values()
    out = []
    for part in pieces:
        if part in values:
            out.append(values[part])
        elif part.strip():
            core = part.strip()
            short = re.fullmatch(r'(?i)(mesos?|meso|ea|each|k|m)([!.?~]*)', core)
            if short:
                out.append({'ea': '개당', 'each': '개당'}.get(short.group(1).lower(), '메소') + short.group(2))
                continue
            if re.search('[A-Za-z가-힣]', core):
                translated = translate(core)
                if re.findall(r'\d+(?:[.,]\d+)*',translated) != re.findall(r'\d+(?:[.,]\d+)*',core):
                    translated = core
                # A failed contextual fragment is kept, not silently omitted.
                out.append(translated if translated.strip() else core)
            else:
                out.append(core)
    return ' '.join(out)


def normalize_chat_input(text):
    # Repair corrupted trade prefixes ONLY with independent trade evidence.
    match = re.match(r'^\s*(?:5>|s\))\s*(.+)$', text, re.I)
    if match and (re.search(r'\[[^\]]+\]|\d+(?:\.\d+)?[kmb]\b', match.group(1), re.I)):
        text = 'S> '+match.group(1)
    # Known elongated words only; never collapse letters in arbitrary names.
    common = {'PLEASE','WHERE','ARE','YOU','WHAT','HOW','DO','CAN','SOMEONE','ANYONE',
              'HELP','ME','THANK','THANKS','THE','THIS','THAT','IS','NOT','TO','GO','ALL','PLAY'}
    # Normalize only known English words, outside linked item labels.
    parts = re.split(r'(\[[^\]]+\])', text)
    for i in range(0,len(parts),2):
        # A short decimal fraction before an explicit k/m/b price unit.
        # Do not reinterpret three-digit comma groups or linked item labels.
        parts[i]=re.sub(r'(?i)(?<![\w.,])([0-9]+)\s*\.\s*([0-9]+)(?=\s*[kmb]\b)',r'\1.\2',parts[i])
        parts[i]=re.sub(r'(?i)(?<![\w.,])([0-9]+),\s*([0-9]{1,2})(?=\s*[kmb]\b)',r'\1.\2',parts[i])
        for pattern,replacement in ((r'\bplease{2,}\b','please'),(r'\bthanks{2,}\b','thanks'),
                                    (r'\bpl[sz]{2,}\b','please')):
            parts[i]=re.sub(pattern,replacement,parts[i],flags=re.I)
        parts[i] = re.sub(r'\b[A-Z]{2,}\b', lambda m: m.group().lower() if m.group() in common else m.group(), parts[i])
    return ''.join(parts)


def split_clauses(text):
    # Do not split S>, a/w, c/o, URLs, fractions or item-link contents.
    parts = re.split(r'(\[[^\]]+\])', text)
    joined = []
    for i, part in enumerate(parts):
        if i%2:
            joined.append(part)
        else:
            joined.append(re.sub(r'\s*\|\s*|\s+/\s+|\s*;\s*', '\x1f', part))
    return [part.strip() for part in ''.join(joined).split('\x1f') if part.strip()]


class TradeMemory:
    def __init__(self, capacity=512):
        self.cache = OrderedDict()
        self.capacity = capacity
        self.hits = 0
        self.compiled = 0

    def translate(self, text):
        if re.search(r'https?://|www\.|discord\.gg', text, re.I):
            return None
        plan = protect_values(text)
        if not any(s.kind == 'item' for s in plan.slots):
            return None
        key = re.sub(r'\s+', ' ', plan.masked).strip().casefold()
        if key in self.cache:
            self.hits += 1
            self.cache.move_to_end(key)
            template = self.cache[key]
        else:
            item = r'(KAINITEM[A-Z]+TOKEN)'
            price = r'(KAINPRICE[A-Z]+TOKEN)'
            action = r'(S\s*>|B\s*>|WTS|WTB|selling|buying)'
            offer = r'(?:pm\s*(?:me\s*)?offers?|pmo|pm\s*offers?|pm|whisper(?:\s+me)?)'
            template = None
            plain_offer=r'(?:this[.!]?\s*)?offers?\s+please[.!]?'
            m=re.fullmatch(item+r'\s*'+action+r'\s*'+plain_offer,plan.masked,re.I)
            if m:
                template=m.group(1)+(' 팝니다' if m.group(2).lower().replace(' ','') in ('s>','wts','selling') else ' 삽니다')+'. 가격을 제안해 주세요'
            m = re.fullmatch(r'I\s+(bought|sold)\s+'+item+r'\s+for\s+'+price+r'(?:\s+(yesterday|today))?[.!]?',plan.masked,re.I)
            if m:
                verb,label,amount,when=m.groups()
                template = ('어제 ' if when and when.lower()=='yesterday' else '오늘 ' if when else '')+label+' '+amount+'에 '+('샀어요' if verb.lower()=='bought' else '팔았어요')
            # Existing single-item PMO form intentionally keeps its wording.
            m = re.fullmatch(item+r'\s*'+offer+r'[.!]?', plan.masked, re.I)
            if m:
                template = m.group(1)+' 가격 제안은 귓말로 주세요'
            m = re.fullmatch(item+r'\s*'+action+r'\s*(?:this[.!]?\s*)?'+offer+r'[.!]?', plan.masked, re.I)
            if m:
                template = m.group(1)+(' 팝니다' if m.group(2).lower().replace(' ','') in ('s>','wts','selling') else ' 삽니다')+'. 가격 제안은 귓말로 주세요'
            m = re.fullmatch(item+r'\s*'+action+r'\s*(?:for\s+)?'+price+r'(?:\s+(OBO|firm|PMO|PM\s*offers?))?[.!]?', plan.masked, re.I)
            if m:
                label, verb, amount, suffix=m.groups()
                template=label+' '+amount+'에'+(' 팝니다' if verb.lower().replace(' ','') in ('s>','wts','selling') else ' 삽니다')
                if suffix:
                    template+='. '+('가격 협의 가능' if suffix.lower()=='obo' else '가격 고정' if suffix.lower()=='firm' else '귓말 주세요')
            m = re.fullmatch(action+r'\s*'+item+r'(?:\s+(?:for\s+)?'+price+r')?(?:\s+(OBO|firm|PMO|PM\s*offers?))?[.!]?',plan.masked,re.I)
            if m:
                verb, label, amount, suffix = m.groups()
                template = label+(' '+amount+'에' if amount else '')+(' 팝니다' if verb.lower().replace(' ','') in ('s>','wts','selling') else ' 삽니다')
                if suffix:
                    template += '. '+('가격 협의 가능' if suffix.lower()=='obo' else '가격 고정' if suffix.lower()=='firm' else '귓말 주세요')
            if template is None:
                return None
            if plan.restore(template) is None:
                return None
            self.cache[key] = template
            self.compiled += 1
            while len(self.cache)>self.capacity:
                self.cache.popitem(last=False)
        return plan.restore(template)
