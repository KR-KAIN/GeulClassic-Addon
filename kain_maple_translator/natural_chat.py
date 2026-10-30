"""Conservative MapleStory conversational phrasing, offline.

Never invent sellers, prices, quantities or party roles. Apply narrow whole-phrase
shortcuts before MT; polish only high-confidence Korean calques after MT.
"""
from __future__ import annotations
import re

# Ambiguous chat with game-specific meanings. First match wins.
_PHRASES_EN_KO = (
    (r'(?:hey|hi|hello|yo)[,\s]+(?:guys|everyone|everybody|all|folks|people|yall|y\x27all)', '다들 안녕!'),
    (r'(?:hey|hi|hello|yo)[,\s]+(?:guy|man|dude|bro|buddy|mate)', '안녕!'),
    (r'(?:what\x27?s|whats)\s+up(?:[,\s]+(?:guys|everyone))?', '다들 뭐 해요?'),
    (r'(?:how(?:\x27s| is)\s+it\s+going|how\s+(?:are|r)\s+(?:you|u))', '잘 지내요?'),
    (r'(?:anyone|anybody|any1|any1 here|any1 wanna|anyone wanna|anyone want to)\s+(?:wanna\s+)?(?:join\s+(?:a\s+)?party|party\s*\??)', '파티하실 분?'),
    (r'(?:anyone|anybody|any1)\s+(?:up\s+)?for\s+(?:kpq|kerning\s+pq)', '커닝 파퀘 하실 분?'),
    (r'(?:anyone|anybody|any1)\s+(?:up\s+)?for\s+(?:lpq|ludi\s+pq)', '루디 파퀘 하실 분?'),
    (r'(?:anyone|anybody)\s+(?:wanna|want\s+to)\s+party', '파티하실 분?'),
    (r'(?:looking\s+for|lf|need)\s+(?:a\s+)?cleric\s+(?:for\s+)?(?:kpq|kerning\s+pq)', '커닝 파퀘 클레릭 구해요'),
    (r'(?:looking\s+for|lf|need)\s+(?:a\s+)?cleric\s+(?:for\s+)?(?:lpq|ludi\s+pq)', '루디 파퀘 클레릭 구해요'),
    (r'(?:lf|looking\s+for|need)\s+(?:a\s+)?(cleric|priest|healer|warrior|mage|thief|archer)', None),
    (r'(?:where\s+(?:should|can)\s+we|where\s+do\s+we)\s+(?:train|grind|level)', '어디서 사냥할까요?'),
    (r'(?:where\s+(?:are|r)\s+(?:you|u)\s+(?:training|grinding)|where\s+do\s+(?:you|u)\s+train)', '어디서 사냥해요?'),
    (r'(?:can|could)\s+(?:you|u)\s+(?:invite|inv)\s+(?:me|my\s+char)', '파티 초대 좀 해주세요'),
    (r'(?:can|could)\s+i\s+(?:join|come\s+with\s+you)', '저도 껴도 될까요?'),
    (r'(?:inv|invite)\s+(?:me|pls|please|plz)', '파티 초대 좀 해주세요'),
    (r'(?:how\s+much\s+(?:for\s+)?(?:this|that|it)|how\s+much\s+is\s+(?:this|that|it))', '이거 얼마예요?'),
    (r'(?:how\s+much|hm)', '얼마예요?'),
    (r'(?:can|could)\s+(?:you|u)\s+(?:lower\s+(?:the\s+)?price|go\s+lower|do\s+(?:a\s+)?discount)', '조금 깎아주실 수 있나요?'),
    (r'(?:wait|hold\s+on|hang\s+on)\s+(?:a\s+)?(?:sec|second|moment|min|minute|pls|plz|please)', '잠깐만요'),
    (r'(?:brb|be\s+right\s+back)', '금방 올게요'),
    (r'(?:omw|on\s+my\s+way|i(?:\s+am|\s*\x27m)?\s+coming)', '지금 가요'),
    (r'(?:let\x27?s|lets)\s+(?:go\s+)?(?:to\s+)?(?:fm|free\s+market)', '자유시장 가요'),
    (r'(?:stop\s+ks|dont\s+ks|don\x27t\s+ks|no\s+ks\s+pls)', '스틸하지 마세요'),
    (r'(?:thanks|thank\s+you|thx|ty|tysm)', '고마워요'),
    (r'(?:no\s+problem|no\s+worries|np|all\s+good)', '괜찮아요'),
    (r'(?:sorry|sry|my\s+bad|mb)', '미안해요'),
    (r'(?:gg|ggwp|good\s+game)', '수고했어요'),
    (r'(?:hey|hi|hello|yo)', '안녕하세요'),
    (r'(?:bye|cya|see\s+ya|see\s+you)', '또 봐요'),
    (r'(?:nice|good\s+job|gj|well\s+done)', '잘했어요!'),
    (r'(?:i\s+need\s+help|help\s+me\s+pls|help\s+me\s+please)', '도와주세요'),
    (r'(?:what\s+level\s+(?:are|r)\s+(?:you|u)|(?:your|ur)\s+lvl\??)', '레벨 몇이에요?'),
    (r'(?:change\s+channel\s+pls|cc\s+plz|cc\s+pls)', '채널 좀 옮겨주세요'),
)
_COMPILED_EN = [(re.compile(r'^'+p+r'$', re.I), value) for p,value in _PHRASES_EN_KO]
_ROLES={'cleric':'클레릭','priest':'프리스트','healer':'힐러','warrior':'전사','mage':'마법사','thief':'도적','archer':'궁수'}

_PHRASES_KO_EN={
    '파티 초대 좀 해주세요':'Inv me pls',
    '저도 껴도 될까요':'Can I join?',
    '파티하실 분':'Anyone wanna party?',
    '커닝 파퀘 하실 분':'Anyone for KPQ?',
    '어디서 사냥해요':'Where are you training?',
    '어디서 사냥할까요':'Where should we train?',
    '잠깐만요':'One sec',
    '지금 가요':'On my way',
    '금방 올게요':'BRB',
    '이거 얼마예요':'How much for this?',
    '조금 깎아주실 수 있나요':'Can you lower the price a bit?',
    '레벨 몇이에요':'What level are you?',
    '스틸하지 마세요':'Please stop KS',
    '안녕하세요':'Hi!',
    '고마워요':'Thanks!',
    '미안해요':'Sorry',
}
# R19: everyday game chat the sentence model turned into 'About Us', 'LOGIN
# JOIN', '{{if price_varies}}' ... (each row: Korean variants -> chat English)
_KO_EN_CHAT = (
    (('안녕', '하이', 'ㅎㅇ', '안녕하세여', '반가워요', '반갑습니다'), 'hi'),
    (('감사합니다', '감사해요', '고맙습니다', '고마워', '고마워요', 'ㄱㅅ', '감사', '땡큐', '감사합니당'), 'ty'),
    (('네', '넹', '넵', '예', '응', 'ㅇㅇ', '그래요', '좋아요', '콜'), 'yes'),
    (('ㅇㅋ', '오케이', '알겠어요', '알겠습니다', '오키'), 'ok'),
    (('아니요', '아니', '아뇨', 'ㄴㄴ', '아니에요', '싫어요'), 'no'),
    (('잠시만요', '잠깐', '잠시만', '잠만', 'ㅈㅁ'), 'one sec'),
    (('얼마예요', '얼마에요', '얼마인가요', '얼마요', '얼마', '가격이 어떻게 되나요', '얼마에 파세요', '얼마에 팔아요'), 'how much?'),
    (('귓 주세요', '귓말 주세요', '귓주세요', '귓 ㄱ', '귓말 부탁해요', '귓 부탁해요', '귓'), 'pm me'),
    (('가격 제안 주세요', '가격 제시해 주세요', '가격 제안해 주세요', '제시 주세요'), 'pm me offers'),
    (('축하해요', '축하합니다', 'ㅊㅋ', 'ㅊㅊ', '추카', '축하드려요'), 'congrats!'),
    (('잘가요', '안녕히 가세요', '바이', 'ㅂㅂ', 'ㅂㅇ', '잘 가요', '다음에 봐요'), 'bye'),
    (('좋은 하루 되세요', '좋은 하루', '즐거운 하루 되세요'), 'have a nice day'),
    (('같이 사냥해요', '같이 사냥하실 분', '같이 사냥할래요', '사냥 같이 해요'), 'anyone want to train together?'),
    (('몇 레벨이에요', '레벨이 몇이에요', '몇렙이에요', '몇 렙이에요', '몇렙', '몇 레벨'), 'what level are you?'),
    (('죄송해요', '죄송합니다', 'ㅈㅅ', '미안', '쏘리'), 'sorry'),
    (('괜찮아요', '괜찮습니다', '상관없어요'), "it's ok"),
    (('천만에요', '별말씀을요'), 'np'),
    (('수고하셨습니다', '수고하셨어요', '수고했어요', 'ㅅㄱ', '수고'), 'gg'),
    (('수고하세요',), 'take care'),
    (('도와주세요', '도움 주세요', '헬프'), 'help pls'),
    (('어디예요', '어디세요', '어디 계세요', '어디에요'), 'where are you?'),
    (('가는 중이에요', '가는 중', '가고 있어요'), 'omw'),
    (('거래해요', '거래 가능해요', '거래 가능하세요', '거래할래요', '거래 ㄱ'), 'trade?'),
    (('팔렸어요', '팔림', '판매 완료', '팔았어요'), 'sold'),
    (('아직 있어요', '아직 팔아요', '아직 파세요', '아직 있나요'), 'still selling?'),
    (('깎아주세요', '조금만 깎아주세요', '좀 깎아주세요', '할인 돼요', '네고 돼요'), 'can you lower the price?'),
    (('비싸요', '너무 비싸요', '비싸네요'), 'too expensive'),
    (('거래 감사합니다', '거래 감사해요', '거래 고마워요'), 'ty for the trade'),
    (('친추해요', '친구 추가해 주세요', '친추 해주세요', '친추 ㄱ', '친구 추가 해주세요'), 'add me'),
    (('초대해 주세요', '초대 좀 해주세요', '초대 부탁해요', '파티 초대 부탁해요'), 'inv pls'),
    (('파티 나갈게요', '파티 나갈께요', '파티 탈퇴할게요'), 'leaving party'),
    (('채널 옮길게요', '채널 바꿀게요'), 'cc'),
    (('렉', '렉 걸려요', '렉 심해요', '렉이 심해요'), 'lag'),
    (('잠수', '잠수할게요', '잠수 탈게요', '자리 비울게요'), 'afk'),
    (('먼저 갈게요', '먼저 나갈게요', '가볼게요', '이만 갈게요'), 'gtg'),
    (('굿', '굳', '좋네요', '나이스', '좋다'), 'nice'),
    (('대박', '와', '우와'), 'wow'),
    (('뭐해요', '뭐 해요', '뭐하세요'), 'what are you doing?'),
    (('사냥터 추천해 주세요', '어디서 사냥해야 돼요', '사냥터 추천'), 'where should I train?'),
    (('파티 하실 분', '파티 할 사람', '파티하실분'), 'anyone wanna party?'),
    (('스틸 그만하세요', '스틸 하지 마세요', '스틸 ㄴㄴ'), 'stop KS pls'),
    (('제 자리예요', '제 자리입니다', '여기 제 자리예요'), 'this is my spot'),
    (('채널 옮겨 주세요', '채널 옮겨주세요', '채널 좀 옮겨 주세요'), 'cc pls'),
)
_KO_EN_TABLE = {k: v for keys, v in _KO_EN_CHAT for k in keys}

# R20.3: everyday game talk the sentence model turned into nonsense ('여기는
# 내자리야' -> "What's New", '같이 사냥할래?' -> 'How to get started?'), as the
# short chat English Maple players write. Whole short lines only, matched
# without spaces and with any usual sentence ending.
_END = r'(?:요|용|여|야|임|이야|이에요|예요|에요|이요|입니다|습니다|다|죠|지|네|음|어|아|ㅇ|ㅎ|ㅋ)*'
_ASK = r'(?:요|용|여|까|까요|ㄱ|ㄱㄱ|\?)*'
_KO_EN_RULES = tuple((re.compile(p), en) for p, en in (
    # spots and hunting grounds
    (r'(?:여기|이자리|이곳|이맵)?(?:는|은|가)?(?:내|제|우리)(?:자리|사냥터|맵|구역|채널)' + _END, 'this is my spot'),
    (r'(?:여기|이자리|이곳)(?:는|은)?(?:주인|임자)(?:있어|있음|있습니다|있다|있는데)' + _END, 'this spot is taken'),
    (r'(?:자리|여기)?(?:좀)?(?:비켜|양보해|비워|빼)(?:줘|주세요|주실래요|줄래|주라|주실수있나요|주시겠어요)' + _ASK, 'pls find another spot'),
    (r'(?:이|여기)?맵(?:에)?(?:빈)?자리(?:있어|있나|있음|있을까|있습니까)' + _ASK, 'any free spot here?'),
    (r'(?:같이|함께)(?:사냥|파밍|렙업|퀘|퀘스트|파퀘)(?:할래|하실래|해|할까|하자|하실분|할사람|ㄱ|가능)' + _ASK + _END, 'wanna train together?'),
    (r'(?:같이|함께)(?:해|하자|할래|하실래|ㄱㄱ|가|갈래|가실래)' + _ASK + _END, 'wanna go together?'),
    # kill stealing, channels
    (r'(?:누가|왜)?(?:내|제)?몹(?:을|좀)?(?:뺏|스틸|가져가|채가|훔쳐)\w{0,6}', 'pls stop ksing'),
    (r'(?:스틸|뺏기|ks)(?:하지마|ㄴㄴ|그만|하지마세요|그만해|그만하세요)\w{0,3}', 'stop ks pls'),
    (r'채널(?:좀)?(?:옮겨|바꿔|이동해|옮기세요)(?:줘|주세요|주실래요|줄래)?' + _ASK, 'cc pls'),
    # coming and going
    (r'(?:잠깐|잠시|금방)?(?:쉬었다|쉬다|화장실|밥먹고|다녀|씻고)(?:올게|올께|옴|올|오겠습니다|올게요|올께요)' + _END, 'brb'),
    (r'(?:지금|금방|곧)(?:갈게|갈께|가요|가는중|감|갑니다)' + _END, 'omw'),
    (r'(?:나중에|또|담에|다음에)(?:봐|봐요|뵈요|뵐게요|봅시다|만나요)' + _END, 'cya'),
    (r'(?:잘자|굿밤|잘자요|좋은밤)' + _END, 'gn'),
    (r'(?:어서와|어서오세요|웰백|웰컴백|왔어|오셨어요|오셨네요)' + _END, 'wb'),
    # replies
    (r'(?:모르겠|몰라|모름|모르겠어|모르겠네|ㅁㄹ)' + _END, 'idk'),
    (r'(?:됐어|신경쓰지마|신경쓰지마세요|아무것도아니|됐습니다)' + _END, 'nvm'),
    (r'(?:진짜|정말|레알|ㄹㅇ|실화)\?+', 'really?'),
    (r'(?:ㄹㅇ|리얼|진짜임|진짜로)' + _END, 'fr'),
    (r'(?:농담|장난|농담이|장난이)' + _END, 'jk'),
    (r'(?:인정|ㅇㅈ|맞아|맞아요|맞습니다)' + _END, 'true'),
    (r'(?:화이팅|파이팅|행운을빌어|행운을빌게|굿럭)' + _END, 'gl'),
    (r'(?:즐겜|즐거운게임|재밌게하세요|즐겁게하세요)' + _END, 'hf'),
    (r'(?:잘했어|잘했어요|나이스|굿잡|잘하시네요|잘하네)' + _END, 'gj'),
    (r'(?:ㄱㄱ|고고|가자|갑시다|ㄱㄱㄱ)' + _END, 'go go'),
    (r'(?:ㄴㅇㅅ|나이스)' + _END, 'nice'),
    # requests
    (r'(?:버프|뻐프)(?:좀)?(?:주세요|줘|부탁해요|부탁|가능)' + _ASK, 'buff pls'),
    (r'(?:힐|힐좀)(?:주세요|줘|부탁해요|부탁|가능)' + _ASK, 'heal pls'),
    (r'(?:잠깐만|잠시만)(?:기다려|기달려)(?:줘|주세요|요)?' + _END, 'wait pls'),
    (r'(?:귓|귓말|귀말)(?:할게|할께|드릴게|보낼게)' + _END, "i'll pm you"),
    (r'(?:어디서|어디에서)(?:사|구해|구하|팔아|파)' + _ASK + _END, 'where can i get it?'),
    (r'(?:파세요|팔아요|팔아|파나요|파시나요|판매중)' + _ASK, 'selling?'),
    (r'(?:살게|살께|구매할게|사겠습니다|제가살게)' + _END, "i'll buy"),
    # happenings
    (r'(?:렙업|레벨업|렙업했|레벨업했|업했)' + _END + r'!*', 'lvl up!'),
    (r'(?:오늘)?(?:레벨|렙|lv)?(\d{1,3})(?:레벨|렙)?(?:찍었|달성했|달성|됐|되었|찍음|찍었어)' + _END + r'!*',
     lambda m: f'hit lvl {m.group(1)}!'),
    (r'(?:죽었|죽음|사망|죽었어)' + _END, 'i died'),
    (r'(?:렉|랙)(?:걸려|걸림|심해|심하네|미쳤)' + _END, 'lag'),
    (r'(?:포션|물약|포트|약)(?:이|을|도)?(?:다)?(?:떨어졌|떨어짐|없어|없음|다씀|다썼|바닥)' + _END, 'out of pots'),
    (r'(?:돈|메소|메르)(?:이|가|도)?(?:없어|없음|부족해|부족|없네)' + _END, 'no mesos'),
    (r'(?:이맵|여기)?(?:은|는)?(?:몹|몬스터|몬스터들|몹들)(?:이|가)?(?:너무)?(?:세|쎄|강해|강하네|세네|쎄네)' + _END, 'mobs are too strong here'),
    (r'(?:보스|보스몹)(?:는|가)?(?:언제|몇시에)(?:나와|나오|젠|리젠|떠|뜸|나오나)' + _ASK + _END, 'when does the boss spawn?'),
    (r'(?:좀)?도와(?:주실수있나|줄수있어|주실래|줄래|주실수있어)' + _ASK + _END, 'can you help me?'),
    (r'(?:오늘|지금|이따|오늘저녁에|저녁에|오늘밤)?(?:같이)?(?:파티퀘스트|파퀘|파티|pq)(?:같이)?(?:하실|할|도실|돌|가실|갈)(?:분|사람)'
     r'(?:있나|있어|있음|있으신가|구해|구함|계신가|계세)?' + _ASK + _END, 'anyone wanna PQ?'),
    (r'(?:이|이거|이아이템|이템|이건)?(?:얼마에|얼마로)(?:팔면|팔아야|파는게|팔까)(?:될까|돼|되나|좋을까|되|하나)?' + _ASK + _END,
     'how much should i sell this for?'),
    (r'(?:이|이거|이아이템|이템|이건)?(?:얼마에|얼마로)(?:사면|사야|사는게|살까)(?:될까|돼|되나|좋을까|되|하나)?' + _ASK + _END,
     'how much should i pay for this?'),
    (r'길드(?:에)?(?:가입|들어가)(?:하고싶|하고싶어|하고싶습니다|할래|하고싶은데|하고싶어요|싶어)' + _END, 'i wanna join a guild'),
    (r'(?:내일)(?:다시)?(?:접속|들어올|올)(?:할게|할께|게|께|게요|께요)?' + _END, 'ill be on tmr'),
    (r'(?:이따|나중에|좀있다)(?:다시)?(?:접속|들어올|올)(?:할게|할께|게|께|게요|께요)?' + _END, 'ill be on later'),
))


def korean_chat_phrase(source: str) -> str | None:
    """Everyday Korean chat -> chat English, or None ('ㅋㅋㅋ' -> 'lol')."""
    text = re.sub(r'\s+', ' ', str(source or '')).strip(' .!?~…')
    if re.fullmatch(r'[ㅋ]{2,}', text):
        return 'lol'
    if re.fullmatch(r'[ㅎ]{2,}', text):
        return 'haha'
    if re.fullmatch(r'[ㅠㅜ]{2,}', text):
        return 'T_T'
    hit = _KO_EN_TABLE.get(text) or _KO_EN_TABLE.get(text.replace(' ', ''))
    if hit:
        return hit
    # '…요' / '…용' endings: '고마워용', '감사해요오'
    base = re.sub(r'(?:용|요오+|여)$', '요', text)
    hit = _KO_EN_TABLE.get(base)
    if hit:
        return hit
    compact = re.sub(r'\s+', '', str(source or '')).strip('.!~…').lower()
    if len(compact) <= 20:
        for pattern, english in _KO_EN_RULES:
            m = pattern.fullmatch(compact)
            if m:
                return english(m) if callable(english) else english
    return None


# R20.3: English the sentence model wrote, in the short forms Maple chat uses
_CHAT_FORMS = tuple((re.compile(p, re.I), short) for p, short in (
    (r"\bthank you (?:very|so) much\b", 'ty so much'),
    (r"\bthank you\b|\bthanks\b", 'ty'),
    (r"\bplease\b", 'pls'),
    (r"\b(?:i'?ll )?be right back\b", 'brb'),
    (r"\bi (?:do not|don'?t) know\b", 'idk'),
    (r"\bby the way\b", 'btw'),
    (r"\bnever ?mind\b", 'nvm'),
    (r"\bi (?:have|need) to go\b|\bi'?ve got to go\b|\bgot to go\b", 'gtg'),
    (r"\b(?:i'?m )?on my way\b", 'omw'),
    (r"\baway from (?:the )?keyboard\b", 'afk'),
    (r"\bgood game\b", 'gg'),
    (r"\bgood luck\b", 'gl'),
    (r"\bhave fun\b", 'hf'),
    (r"\bwelcome back\b", 'wb'),
    (r"\bno problem\b", 'np'),
    (r"\byou'?re welcome\b", 'yw'),
    (r"\bin my opinion\b", 'imo'),
    (r"\bto be honest\b", 'tbh'),
    (r"\boh my god\b", 'omg'),
    (r"\bright now\b", 'rn'),
    (r"\bjust kidding\b", 'jk'),
    (r"\bsee you(?: later| next time)?\b", 'cya'),
    (r"\bgood night\b", 'gn'),
    (r"\b(?:send me a |private )?(?:message|whisper) me\b", 'pm me'),
    (r"\bchange (?:the )?channels?\b", 'cc'),
    (r"\bkill ?steal(?:ing)?\b", 'ks'),
    (r"\blooking for (?:a )?party\b", 'LFP'),
    (r"\blooking for (?:more |party )?members\b", 'LFM'),
    (r"\bparty quests?\b", 'PQ'),
    (r"\bexperience points?\b|\bexperience\b", 'exp'),
    (r"\bmesos?\b", 'meso'),
    (r"\bcongratulations\b", 'congrats'),
    (r"\bto level up\b", 'to lvl up'),
))


def chatify_english(text: str) -> str:
    """'Thank you, please wait' -> 'ty, pls wait' (sentence-model output only)."""
    out = str(text or '')
    for pattern, short in _CHAT_FORMS:
        out = pattern.sub(short, out)
    return re.sub(r'\s{2,}', ' ', out).strip()


def faithful_english(source: str, english: str, back) -> bool:
    """Does the English say what the Korean said? It is turned back into
    Korean (back) and must share enough two-letter Hangul pieces with the
    source: "What's New" for '여기는 내자리야' shares none."""
    ko = re.sub(r'[^가-힣]', '', str(source or ''))
    if len(ko) < 4:
        return True               # too short to judge; the tables cover these
    try:
        again = re.sub(r'[^가-힣]', '', str(back(english) or ''))
    except Exception:
        return True
    a = {ko[i:i + 2] for i in range(len(ko) - 1)}
    b = {again[i:i + 2] for i in range(len(again) - 1)}
    if not b:
        return False
    return 2 * len(a & b) / (len(a) + len(b)) >= FAITHFUL_MIN


FAITHFUL_MIN = 0.12


# What the sentence model produces for short Korean it does not know
_KO_EN_JUNK = re.compile(r'^(?:about us|login join|join us|no\.\s*1|what is it\??|i\'?m going|contact us|home|menu)\.?$'
                         r'|\{\{|\}\}', re.I)


def junk_english(result: str) -> bool:
    return bool(_KO_EN_JUNK.search((result or '').strip()))

# Only safe, high-confidence fixes, on Korean sentences, never names/numbers.
_KOREAN_CALQUES = (
    (r'어디에서\s*(?:훈련|트레이닝)(?:을)?\s*(?:하세요|합니까|하고\s*있나요)', '어디서 사냥해요'),
    (r'당신은\s*몇\s*레벨(?:입니까|인가요)', '레벨 몇이에요'),
    (r'당신은\s*어디에\s*(?:있습니까|있나요)', '어디 있어요'),
    (r'제가\s*당신의\s*파티에\s*참여할\s*수\s*있습니까', '저도 파티 껴도 될까요'),
    (r'파티에\s*참가하기를\s*원합니다', '파티 끼고 싶어요'),
    (r'나를\s*초대해\s*주세요', '초대 좀 해주세요'),
    (r'당신의\s*파티에\s*저를\s*초대해\s*주세요', '파티 초대 좀 해주세요'),
    (r'몇\s*개의\s*메소', '메소 얼마'),
)
_CALQUE_RE=[(re.compile(p),v) for p,v in _KOREAN_CALQUES]


def _trim(text: str) -> str:
    return re.sub(r'\s+', ' ', str(text or '').strip()).strip(' .!?~…')


def phrase_override(source: str, direction: str) -> str | None:
    """Prefer exact game chat intents. No aggressive subphrase rewriting."""
    if direction == 'en-ko':
        candidate=_trim(source)
        # Protect encoded prices/long commercial messages from conversational rewrite.
        if re.search(r'\b\d+(?:\.\d+)?\s*[kmb]\b|\b(?:wts|wtb|wtt)\b|[SBTRJ]\s*>',candidate,re.I):
            return None
        for rx,result in _COMPILED_EN:
            match=rx.fullmatch(candidate)
            if match:
                if result is None:
                    return f'{_ROLES[match.group(1).lower()]} 구해요'
                return result
        return None
    if direction == 'ko-en':
        return _PHRASES_KO_EN.get(_trim(source)) or korean_chat_phrase(source)
    return None


def polish_translation(source: str, result: str, direction: str) -> str:
    """Conservative post-edit of MT output, preserving numbers and proper names."""
    if direction != 'en-ko' or not result or not re.search('[가-힣]',result):
        return result
    original=result
    for regex,replacement in _CALQUE_RE:
        result=regex.sub(replacement,result)
    # Never accept a rewrite that drops digit sequences (price/level/channel).
    if re.findall(r'\d+(?:[.,]\d+)*', original) != re.findall(r'\d+(?:[.,]\d+)*',result):
        return original
    return result
