"""Complete headword coverage for NiaMeowDB Classic glossary (2026-10-23).

Only short *independently written* Korean equivalents are stored, not the
publisher's explanations. Ambiguous words are for reference/context; the
runtime glossary rule interpreter remains conservative for ordinary prose.
"""
from __future__ import annotations

SOURCE_URL = 'https://meowdb.com/msclassic/ko/guides/maplestory-classic-glossary'
# category -> (English headword/aliases, short Korean rendition)
CATALOG = {
    '일반 및 메타': [
        ('MS','메이플스토리'), ('MSCW / MS Classic','메이플스토리 클래식 월드'),
        ('pre-BB','빅뱅 업데이트 이전'), ('GMS / KMS / JMS / EMS','글로벌·한국·일본·유럽 메이플스토리'),
        ('Big Bang','빅뱅 업데이트'), ('OSMS / Old School MS','옛날 메이플스토리'),
    ],
    '레벨링과 EXP': [
        ('EXP','경험치'), ('grind','반복 사냥'), ('level up / ding','레벨업'),
        ('train','파티 사냥'), ('leech','경험치 쩔'), ('power level / PL','빠른 레벨업 지원'),
        ('party bonus','파티 경험치 보너스'), ('mob rate','몬스터 등장 밀도'),
        ('respawn wave','몬스터 재생성 주기'),
    ],
    '직업과 전직': [
        ('Beginner','초보자'), ('1st job','1차 전직'), ('2nd job','2차 전직'),
        ('3rd job / 4th job','3차·4차 전직'), ('branch','직업 분기'),
        ('job advancement','전직'), ('pure / pure stat','순수 스탯 빌드'),
        ('dexless / strless / lukless','보조 능력치 미투자 빌드'),
        ('hybrid','혼합 스탯 빌드'), ('STR / DEX / INT / LUK','힘·민첩·지력·운'),
    ],
    '스탯과 AP': [
        ('AP','능력치 포인트'), ('AP Reset','능력치 초기화'),
        ('SP','스킬 포인트'), ('SP Reset','스킬 초기화'),
        ('secondary stat','보조 스탯'),
    ],
    '스킬과 SP': [
        ('prereq','선행 조건'), ('max level','최대 스킬 레벨'),
        ('active skill','액티브 스킬'), ('passive skill','패시브 스킬'),
        ('buff','버프'), ('booster','공격속도 부스터'), ('mastery','무기 마스터리'),
    ],
    '전투와 데미지': [
        ('HP / MP','체력·마나'), ('WATK / W.ATK','무기 공격력'),
        ('Magic / MATK','마법 공격력'), ('ATK Power','추가 공격력'),
        ('PDEF / MDEF','물리·마법 방어력'), ('ACC / AVOID','명중·회피'),
        ('range','최소·최대 대미지 범위'), ('one-shot','한 방 처치'),
        ('KB','넉백'), ('mastery floor','최소 대미지 보정'),
        ('crit','치명타'), ('elemental advantage','속성 상성 우위'),
        ('status','상태 이상'),
    ],
    '장비와 주문서': [
        ('slots','강화 슬롯'), ('clean','미강화 장비'),
        ('(+N) after an item name','아이템 추가 능력치 표기'),
        ('scroll','주문서'), ('Lesser scroll','하급 주문서'),
        ('Intermediate scroll','중급 주문서'), ('Greater scroll','상급 주문서'),
        ('Chaos scroll','카오스 주문서'),
        ('60% scroll / 10% scroll / 100% scroll','성공률별 강화 주문서'),
        ('slot fest / scroll fest','주문서 강화 이벤트'), ('god roll','강화 대성공 아이템'),
        ('brick / boomed','강화 실패로 파괴됨'), ('overall / overalls','한벌옷'),
        ('Sauna Robe','사우나 가운'), ('untradeable','거래 불가'),
    ],
    '파티와 PQ': [
        ('party','파티'), ('leader','파티장'), ('PQ','파티 퀘스트'),
        ('kPQ / Kerning PQ','커닝 파퀘'), ('LPQ / Ludi PQ','루디 파퀘'),
        ('KS / kill steal','스틸'), ('lurk','보스 대기'),
        ('train (파티)','파티 사냥'), ('carry','캐리'),
        ('loot / party loot','아이템 획득 방식'), ('ninja loot','아이템 무단 줍기'),
    ],
    '경제와 거래': [
        ('mesos','메소'), ('NX','넥슨 캐시'), ('Cash Shop','캐시샵'),
        ('FM / Free Market','자유시장'), ('merchant / merching','장사·되팔이'),
        ('store permit','개인 상점 허가증'), ('gacha / gachapon','뽑기'),
        ('trade','거래'), ('c/o','현재 최고 제시가'), ('a/w','즉시 구매가'),
        ('RES / RES MET','최저 판매가·최저가 달성'),
        ('FM4 CH9','9채널 자유시장 4번 방'), ('ea','개당'),
        ('NX trash / junk NX','불필요한 캐시 아이템'),
    ],
    '콘텐츠와 보스': [
        ('Forgotten Hollow','잊혀진 은신처'), ('Zelya','젤리아'),
        ('boss','보스'), ('mini-boss / rare','중간 보스·희귀 몬스터'),
        ('Mushmom','머쉬맘'), ('Jr. Balrog','주니어 발록'),
        ('Zakum','자쿰'), ('hidden street','히든 스트리트'),
        ('dungeon','던전'), ('subway','지하철'),
    ],
    '커뮤니티 슬랭': [
        ('noob / newb','초보'), ('vet / veteran','베테랑'),
        ('afk','자리 비움'), ('brb','곧 돌아옴'), ('gg','수고했어요'),
        ('rip','아이고 망했다'), ('sniping','보스 선점 가로채기'),
        ('gach / gachapon\'d','뽑기 운'), ('cc','채널 변경'),
        ('@@ / guide me','길 안내 부탁해요'), ('boomed','강화 실패로 파괴됨'),
        ('B>','삽니다'), ('S>','팝니다'), ('T>','교환합니다'),
        ('WTS / WTB / WTT','판매·구매·교환 희망'),
        ('J>','참가 희망'), ('R>','파티 모집'),
    ],
}


def headwords() -> list[tuple[str,str,str]]:
    return [(name, ko, cat) for cat, pairs in CATALOG.items() for name,ko in pairs]


# Headwords containing several distinct abbreviations need individual meanings,
# not a shared expanded label (GMS != KMS and WTS != WTB).
ALIAS_OVERRIDES = {
    'gms':'글로벌 메이플스토리', 'kms':'한국 메이플스토리',
    'jms':'일본 메이플스토리', 'ems':'유럽 메이플스토리',
    '3rd job':'3차 전직', '4th job':'4차 전직',
    'dexless':'덱스리스', 'strless':'힘 미투자 빌드',
    'lukless':'럭리스', 'str':'힘', 'dex':'민첩',
    'int':'지력', 'luk':'운', 'hp':'체력', 'mp':'마나',
    'pdef':'물리 방어력','mdef':'마법 방어력',
    'acc':'명중률','avoid':'회피율',
    'wts':'팝니다', 'wtb':'삽니다', 'wtt':'교환합니다',
    'res':'최소 판매가', 'res met':'최소 판매가 충족',
    '60% scroll':'60% 주문서', '10% scroll':'10% 주문서',
    '100% scroll':'100% 주문서',
}

def term_index() -> dict[str, tuple[str,str]]:
    result = {}
    for name,ko,cat in headwords():
        for alias in name.split(' / '):
            alias = alias.strip()
            # Parenthetical explanatory annotations are not part of a command.
            if alias:
                result[alias.casefold()] = (ALIAS_OVERRIDES.get(alias.casefold(),ko),cat)
    return result
