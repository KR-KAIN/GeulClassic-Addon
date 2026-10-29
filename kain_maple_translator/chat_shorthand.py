"""Exact game-chat intents plus guarded expansions for the offline model.

Never autocorrect item names, prices, stats, nicknames, URLs or unknown tokens.
"""
from __future__ import annotations
import re

_PQ = {'kpq': '커닝 파퀘', 'lpq': '루디 파퀘', 'opq': '오르비스 파퀘',
       'lmpq': '루디 미로 파퀘', 'hpq': '헤네시스 파퀘'}
_ROLES = {'cleric': '클레릭', 'priest': '프리스트', 'sin': '표도',
          'dit': '시프', 'warrior': '전사', 'mage': '마법사', 'archer': '궁수'}
_EXACT = {
    'ye ye': '응 응',
    'oh': '아',
    'obo': '가격 협의 가능',
    'pmo':'가격 제안은 귓말로 주세요', 'pm me':'귓말 주세요',
    'tysm':'정말 고마워', 'ty':'고마워', 'np':'괜찮아',
    'lmk':'알려줘', 'dm me':'개인 메시지 주세요', 'sry':'미안해', 'mb':'내 실수야',
    'tyvm': '정말 고마워', 'thx a lot': '정말 고마워', 'tysm bro': '정말 고마워',
    'ty bro': '고마워', 'thx bro': '고마워', 'np bro': '괜찮아',
    'idk tbh': '솔직히 잘 모르겠어', 'tbh idk': '솔직히 잘 모르겠어',
    'idc': '난 상관없어', 'iirc': '내 기억이 맞다면', 'afaik': '내가 알기로는',
    'ttyl': '나중에 얘기하자', 'bbl': '이따 다시 올게', 'gtg': '나 가봐야 해',
    'g2g': '나 가봐야 해', 'cya later': '나중에 봐', 'wya': '어디야?',
    'wyd': '뭐 해?', 'hbu': '너는?', 'wbu': '너는?', 'jk': '농담이야',
    'dw': '걱정하지 마', 'glhf': '행운을 빌어, 재밌게 해', 'ggwp': '수고했어, 잘했어',
    'inv me pls': '파티 초대 좀 해주세요', 'inv me plz': '파티 초대 좀 해주세요',
    'pt me': '파티 초대해주세요', 'pt pls': '파티 초대해주세요',
    'cc pls': '채널 좀 바꿔 주세요', 'cc plz': '채널 좀 바꿔 주세요',
    'brb 1 sec': '잠깐 자리 비울게', 'brb a sec': '잠깐 자리 비울게',
    'need hs': '홀리 심볼 필요해요', 'hs pls': '홀리 심볼 좀 주세요',
    'hs plz': '홀리 심볼 좀 주세요', 'haste pls': '헤이스트 좀 주세요',
    'hb pls': '하이퍼 바디 좀 주세요', 'hb plz': '하이퍼 바디 좀 주세요',
    'se pls': '샤프 아이즈 좀 주세요', 'bless pls': '블레스 좀 주세요',
}
_GUARD = re.compile(r'https?\s*:|www\.|discord\.gg|\[[^\]]*\]|'
                    r'(?i:\b(?:wts|wtb|wtt|pmo|a/w|c/o)\b)|'
                    r'(?i:[SBTR]\s*[>＞])|\d\s*%|\d+(?:\.\d+)?\s*[kmb]\b|'
                    r'\b(?:str|dex|int|luk|atk|att|matk|gfa|gma)\b', re.I)


def shorthand_translation(text: str) -> str | None:
    value = re.sub(r'\s+', ' ', text.strip()).strip(' .!?~').casefold()
    if value in _EXACT:
        return _EXACT[value]
    m = re.fullmatch(r'(?:please\s+)?where\s+(?:r\s+u|are\s+you|are\s+u)(?:\s+(rn|right now))?',value)
    if m:
        return '지금 어디 있어요?' if m.group(1) else '어디 있어요?'
    pq = '|'.join(_PQ)
    m = re.fullmatch(r'(lfm|r>)\s*(\d+)?\s*('+pq+r')(?:\s+(?:pls|plz))?', value)
    if m:
        amount = m.group(2)
        return _PQ[m.group(3)]+(f' {amount}명 구해요' if amount else ' 인원 구해요')
    m = re.fullmatch(r'(?:lf|lfg|j\s*>?)\s*('+pq+r')(?:\s+(?:pls|plz))?', value)
    if m:
        return _PQ[m.group(1)]+(' 참가 원해요' if value.startswith('j') else ' 파티 구해요')
    # In the source video, cc identifies a channel range in a question;
    # expanding it to the command "change channel" changes the meaning.
    m=re.fullmatch(r'only\s+(?:cc|ch)\s+(\d+)\s*-\s*(\d+)\s+can\s+pq',value)
    if m:
        return f'{m.group(1)}~{m.group(2)}채널에서만 파티 퀘스트 할 수 있어요?'
    m=re.fullmatch(r"it(?:s|'s)\s+ch\s+(\d+)\s*-\s*(\d+)(?:\s+(?:bro|brother|brotheer))?",value)
    if m:
        return f'{m.group(1)}~{m.group(2)}채널이야'
    m = re.fullmatch(r'lfm\s+('+pq+r')\s+(?:need\s+)?('+'|'.join(_ROLES)+r')', value)
    if m:
        return _PQ[m.group(1)]+' '+_ROLES[m.group(2)]+' 구해요'
    m = re.fullmatch(r'cc\s*(?:ch\s*)?(\d{1,3})(?:\s+(?:pls|plz))?', value)
    if m:
        return m.group(1)+'채널로 옮겨주세요'
    m = re.fullmatch(r'brb\s+(\d+)\s*(?:m|min|mins|minutes)', value)
    if m:
        return m.group(1)+'분 정도 자리 비울게'
    return None


_EXPAND = {
    'idk': 'I do not know', 'idc': 'I do not care', 'imo': 'in my opinion',
    'imho': 'in my opinion', 'tbh': 'to be honest', 'btw': 'by the way',
    'afaik': 'as far as I know', 'iirc': 'if I remember correctly',
    'rn': 'right now', 'atm': 'at the moment', 'asap': 'as soon as possible',
    'brb': 'I will be right back', 'afk': 'away from keyboard',
    'omw': 'on my way', 'nvm': 'never mind', 'plz': 'please', 'pls': 'please',
    'ppl': 'people', 'any1': 'anyone', 'some1': 'someone', 'every1': 'everyone',
    'cuz': 'because', 'bcuz': 'because', 'wanna': 'want to', 'gonna': 'going to',
    'lmk':'let me know', 'sry':'sorry', 'ty':'thank you',
    'gotta': 'have to', 'kinda': 'kind of', 'thx': 'thanks', 'tysm': 'thank you so much',
}
_TOKENS = re.compile(r"\b(?:"+'|'.join(sorted(_EXPAND, key=len, reverse=True))+r")\b", re.I)


def expand_shorthand(text: str) -> str:
    if re.search(r'https?\s*:|www\.|discord\.gg',text,re.I):
        return text
    if '[' in text:
        parts=re.split(r'(\[[^\]]*\])',text)
        if len(parts)==1:
            # OCR can lose a closing bracket. Recursing on the unchanged
            # input used to exhaust the stack and abort the current frame.
            return text
        return ''.join(part if i%2 else expand_shorthand(part) for i,part in enumerate(parts))
    if _GUARD.search(text):
        return text
    value = _TOKENS.sub(lambda m: _EXPAND[m.group().casefold()], text)
    value = re.sub(r'\b(where|how|what)\s+r\s+u\b',r'\1 are you',value,flags=re.I)
    value = re.sub(r'\bur\s+(lvl|level|name|party)\b',r'your \1',value,flags=re.I)
    value = re.sub(r'\bur\s+(welcome|right)\b',r'you are \1',value,flags=re.I)
    # Single letters are ambiguous; expand only these grammatical contexts.
    value = re.sub(r'\b(can|could|would|do|are|thank|see)\s+u\b', r'\1 you', value, flags=re.I)
    value = re.sub(r'\bu\s+r\b', 'you are', value, flags=re.I)
    return value


def trade_suffix(text: str):
    if not re.match(r'^\s*(?:[SBT]\s*>|wts\b|wtb\b|wtt\b|selling\b|buying\b)', text, re.I):
        return None
    match = re.fullmatch(r'(.+?)\s+(obo|or best offer|negotiable|nego)[.!]?\s*', text, re.I)
    if match and len(match.group(1).strip()) > 3:
        return match.group(1).strip(), '가격 협의 가능'
    match = re.fullmatch(r'(.+?\d+(?:\.\d+)?\s*[kmb])\s+firm[.!]?\s*', text, re.I)
    if match:
        return match.group(1).strip(), '가격 고정'
    return None
