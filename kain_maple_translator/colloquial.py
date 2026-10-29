"""Korean Maple chat micro-translations and safe chat rewrites.

High-confidence whole sentences only. Do not infer facts from corrupted OCR.
"""
from __future__ import annotations
import re

_SINGLE = {
 'hi':'안녕', 'hii':'안녕', 'hiii':'안녕', 'hey':'안녕', 'heyy':'안녕',
 'hello':'안녕하세요', 'hollo':'안녕하세요', 'helo':'안녕하세요', 'hallo':'안녕하세요',
 'helloo':'안녕하세요', 'yo':'안녕', 'sup':'뭐 해?', 'wassup':'뭐 해?',
 'gm':'좋은 아침!', 'gn':'잘 자', 'good morning':'좋은 아침이에요',
 'good night':'잘 자요', 'good evening':'좋은 저녁이에요',
 'hiya':'안녕', 'wb':'다시 왔네', 'brb':'금방 올게',
 'afk':'잠수 중', 'ty':'고마워', 'thx':'고마워',
 'tysm':'진짜 고마워', 'thanks':'고마워', 'thank you':'고마워요',
 'np':'괜찮아', 'yw':'별말을 다 해', 'nvm':'신경 쓰지 마',
 'lol':'ㅋㅋㅋ', 'lmao':'ㅋㅋㅋ', 'omg':'헐', 'rip':'아이고',
 'gg':'수고했어', 'gj':'잘했어', 'gratz':'축하해',
 'gz':'축하해', 'congrats':'축하해', 'sry':'미안',
 'sorry':'미안해', 'mb':'내 실수야', 'idk':'모르겠어',
 'ikr':'그러니까', 'wdym':'무슨 뜻이야?', 'fr':'진짜로',
 'wtf':'뭐야 이게', 'ok':'알겠어', 'okay':'알겠어',
 'k':'응', 'kk':'알겠어', 'sure':'좋아', 'nope':'아니',
 'yes':'응', 'yeah':'응', 'yep':'응', 'nah':'아니',
 'how are you':'잘 지내세요?', 'how r u':'잘 지내요?',
 'how are u':'잘 지내요?', 'how you doing':'잘 지내요?',
 'im good':'저는 잘 지내요', "i'm good":'저는 잘 지내요',
 'im fine':'전 괜찮아요', "i'm fine":'전 괜찮아요',
 'nice to meet you':'반가워요', 'nice to meet u':'반가워요',
 'good luck':'행운을 빌어요', 'gl':'행운을 빌어',
 'hf':'재밌게 해', 'glhf':'재밌게 해',
 'lets go':'가자', "let's go":'가자', 'one sec':'잠깐만요',
 'sec':'잠깐만', 'wait':'잠깐만', 'wait pls':'잠깐만요',
 'are you there':'거기 있어요?', 'u there':'거기 있어요?',
 'here':'여기야', 'coming':'지금 가', 'omw':'가는 중',
 'what happened':'무슨 일 있어요?', 'what happened here':'여기 무슨 일 있었어요?',
 'i need help':'도와주세요', 'help pls':'도와주세요',
 'hi guys':'다들 안녕하세요', 'hi everyone':'다들 안녕하세요', 'hi all':'다들 안녕하세요',
 'hello guys':'다들 안녕하세요', 'hello everyone':'다들 안녕하세요',
 'hello all':'다들 안녕하세요', 'hollo everyone':'다들 안녕하세요',
 'ty all':'다들 고마워요', 'thanks everyone':'다들 고마워요',
 'good job everyone':'다들 수고했어요', 'see you':'또 봐요',
 'see ya':'또 봐요', 'cya':'또 봐', 'bye':'잘 가',
}

# Changes allowed only where full text clearly communicates the same meaning.
_SENTENCES=(
 (r'(?:can|could) (?:someone|anyone|somebody) (?:help|assist) (?:me|us)', '누가 좀 도와주실 수 있나요?'),
 (r'why (?:did|would) they nerf (?:the )?bow', '왜 활을 너프한 거죠?'),
 (r'(?:they|devs) (?:are |r )?nerfing (?:the )?bow', '활을 너프하고 있네요'),
 (r'(?:they|devs) (?:are |r )?buffing (?:the )?sin', '표도를 버프하고 있네요'),
 (r'(?:is|are) (?:this|these) (?:good|worth it)', '이거 괜찮은가요?'),
 (r'(?:how|where) do i (?:get|find) (?:this|that)', '이거 어디서 구해요?'),
 (r'(?:lets|let\'s) (?:do|run) (?:some )?kpq', '커닝 파퀘 가요'),
 (r'(?:lets|let\'s) (?:do|run) (?:some )?lpq', '루디 파퀘 가요'),
)
_COMPILED=tuple((re.compile(r'^(?:'+expr+r')$',re.I),result) for expr,result in _SENTENCES)


def conversational_shortcut(message:str)->str|None:
    cleaned=re.sub(r'\s+',' ',str(message).strip())
    # Avoid extracting a greeting from trade texts, URLs or proper item names.
    if not cleaned or re.search(r'(?i)(?:[SBTRJ]\s*>|https?://|\d+(?:\.\d+)?[kmb]\b)', cleaned):
        return None
    phrase=re.sub(r'[.!?~…]+$','',cleaned).strip().casefold()
    if phrase in _SINGLE:
        return _SINGLE[phrase]
    for regexp,replacement in _COMPILED:
        if regexp.fullmatch(phrase):return replacement
    return None


# Limited post-editing on outputs from the general AI model only: keep names,
# prices and uncertain OCR unchanged. Longer multi-word utterances are polite.
_POLITE_ENDINGS = (
    ('알았어', '알았어요'), ('끝났어', '끝났어요'), ('왔어', '왔어요'),
    ('괜찮아', '괜찮아요'), ('필요해', '필요해요'), ('좋아', '좋아요'),
    ('싫어', '싫어요'), ('모르겠어', '모르겠어요'), ('몰라', '몰라요'),
    ('없어', '없어요'), ('있어', '있어요'), ('기다려', '기다려요'),
    ('고마워', '고마워요'), ('미안해', '미안해요'),
    ('어디야', '어디예요'), ('뭐해', '뭐해요'), ('맞아', '맞아요'),
    ('가자', '같이 가요'), ('하자', '같이 해요'),
)

def polite_long_message(source: str, translated: str) -> str:
    # Longer sentence = three or more lexical words. Market texts, numeric
    # prices and URLs are never altered by this optional post-edit.
    source=str(source or '').strip()
    if len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",source)) < 3:
        return translated
    if re.search(r'(?i)(?:[SBTRJ]\s*>|\b(?:wts|wtb|a/w|c/o)\b|https?://)',source):
        return translated
    text=str(translated or '')
    matched=re.match(r'(?s)^(.*?)([.!?~…]*)$',text)
    if not matched:return text
    body,punct=matched.groups()
    for ending, polite in _POLITE_ENDINGS:
        if body.endswith(ending):
            # For common suffixes, change only a terminal whole morpheme.
            # e.g. '그냥 좋아' -> '그냥 좋아요', not item/proper-name tokens.
            return body[:-len(ending)] + polite + punct
    return text

def polish_chat_result(source:str,result:str)->str:
    """Correct a handful of known EN/KO mixed fragments after local MT."""
    if not re.search('[가-힣]',result):return result
    substitutions=(
      (r'(?i)\bmesos?\b','메소'),
      (r'(?i)\b(?:plz|pls)\b','부탁해요'),
      (r'(?i)\b(?:pm\s*me|pmo)\b','귓말 주세요'),
      (r'(?i)\bnerfing\b','너프하는 중'),
      (r'(?i)\bnerfed\b','너프됐어요'),
      (r'(?i)\bbuffing\b','버프하는 중'),
      (r'(?i)\bdefame\b','인기도 내리기'),
      (r'(?i)\bks(?:er)?\b','자리 스틸'),
      (r'(?i)\bnoob\b','초보'),
    )
    value=result
    for pattern,repl in substitutions:
        value=re.sub(pattern,repl,value)
    return polite_long_message(source,value)
