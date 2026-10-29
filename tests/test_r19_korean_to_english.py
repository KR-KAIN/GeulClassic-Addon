"""R19: Korean -> English (the KO > EN composer) for trade, party and chat lines.

Before, everything but a handful of fixed lines went to the sentence model:
'노가다 목장갑 8공 3작 900만에 팝니다' -> 'Nogada Throat 8th 3rd 900m',
'감사합니다' -> 'LOGIN JOIN', '가격 제안 주세요' -> '{{if price_varies}}'.
"""
import unittest
from decimal import Decimal

from kain_maple_translator.ko_trade import korean_post, _parse_money, _won
from kain_maple_translator.natural_chat import korean_chat_phrase, junk_english


class Money(unittest.TestCase):
    def test_korean_units(self):
        cases = {'900만': '9m', '12만': '120k', '1억 2천만': '120m', '1.5억': '150m', '6만5천': '65k',
                 '1백만': '1m', '2천': '2k', '1천5백': '1.5k', '750': '750', '2000원': '2k', '9m': '9m', '1.5m': '1.5m'}
        for text, expected in cases.items():
            self.assertEqual(_won(_parse_money(text)), expected, text)

    def test_round_values_keep_their_zeros(self):
        self.assertEqual(_won(Decimal(150_000_000)), '150m')   # not '15m'
        self.assertEqual(_won(Decimal(100_000)), '100k')


class Trade(unittest.TestCase):
    def check(self, ko, en):
        self.assertEqual(korean_post(ko), en, ko)

    def test_items_options_prices(self):
        self.check('노가다 목장갑 8공 3작 900만에 팝니다', 'S> Work Gloves 8 att 3 slots 9m')
        self.check('노목 10공 7작 1200만 팝니다', 'S> Work Gloves 10 att 7 slots 12m')
        self.check('노목 3작 8공 9백만', 'S> Work Gloves 3 slots 8 att 9m')        # no verb: a sale
        self.check('스틸 이고르 8천에 팝니다', 'S> Steel Igor 8k')
        self.check('천사의 헤일로 35만 팝니다 가격 제안 받아요', 'S> Angel Halo 350k taking offers')
        self.check('이블 스컬 50만 팝니다 흥정 가능', 'S> Evil Skull 500k neg')
        self.check('에메랄드 귀고리 노작 10만에 삽니다', 'B> Emerald Earrings clean 100k')
        self.check('마녀 모자 2만 급처', 'S> Witch Hat 20k quick sale')
        self.check('인기도 5천에 팝니다', 'S> fame 5k')                            # '도' is not a particle here

    def test_scrolls(self):
        self.check('장갑 공격력 60% 주문서 12만 메소에 팝니다', 'S> Glove ATT 60% 120k')
        self.check('장갑 공 60퍼 10만 삽니다', 'B> Glove ATT 60% 100k')
        self.check('귀 인트 60 5만에 삼', 'B> Earring INT 60% 50k')
        self.check('60퍼 장공 15만 삼', 'B> GFA 60% 150k')
        self.check('펫장비 이동속도 60% 4만 2천에 삽니다', 'B> Pet Equip Speed 60% 42k')
        self.check('60% 주문서 200만 메소에 팝니다', 'S> 60% scroll 2m')
        self.check('노목 7공 5작 + 장갑 공격력 60% 주문서 같이 팝니다 800만',
                   'S> Work Gloves 7 att 5 slots + Glove ATT 60% 8m')

    def test_consumables_each_quantity(self):
        self.check('맑은 물 개당 750에 삽니다', 'B> Pure Water 750 ea')
        self.check('맑은물 700 삽니다', 'B> Pure Water 700')
        self.check('엘릭서 100개 개당 2천에 삽니다', 'B> Elixir x100 2k ea')
        self.check('하얀 포션 250, 파란 포션 200 삽니다', 'B> White Potion 250, Blue Potion 200')
        self.check('캐시템 전부 삽니다 개당 1만', 'B> all NX 10k ea')

    def test_place_contact_and_markers(self):
        self.check('월비 표창 1500에 팝니다 3채널 자유시장 5', 'S> Wolbis 1.5k ch3 FM5')
        self.check('아대 공격력 60% 100만 팝니다 자유시장 12', 'S> Claw ATT 60% 1m FM12')   # 12 is the room
        self.check('귀고리 지력 60% 5만에 삽니다 귓 주세요', 'B> Earring INT 60% 50k pm me')
        self.check('S> 노목 900만', 'S> Work Gloves 9m')
        self.check('노목 사실 분 900만', 'S> Work Gloves 9m')
        self.check('엘릭서 파실 분 개당 2천', 'B> Elixir 2k ea')

    def test_trade_and_mixed(self):
        self.check('천사의 헤일로랑 이블 스컬 교환해요', 'T> Angel Halo for Evil Skull')
        self.check('노목 팝니다 / 엘릭서 삽니다', 'S> Work Gloves / B> Elixir')

    def test_party(self):
        self.check('커닝 파퀘 30레벨 이상 2명 모집해요', 'R> KPQ need 2 lv30+')
        self.check('루디 파퀘 참가 원해요', 'J> LPQ')
        self.check('파티 퀘스트 연속 진행 참가 원해요', 'J> PQ rush')
        self.check('커닝 파퀘 껴주세요 25레벨 도적', 'J> KPQ lv25 thief')
        self.check('파티원 2명 구해요', 'LF2M')
        self.check('파티 구해요', 'LFP')
        self.check('레벨 30 클레릭 파티 구해요', 'LFP lv30 cleric')

    def test_not_a_post(self):
        for line in ('안녕하세요', '어디서 사냥해요', '이거 얼마예요', '커닝 파퀘 하실 분'):
            self.assertIsNone(korean_post(line), line)

    def test_unknown_words_use_the_fallback_or_decline(self):
        self.assertIsNone(korean_post('나무 지팡이 팝니다 5천'))          # no Korean is ever handed back
        self.assertEqual(korean_post('나무 지팡이 팝니다 5천', lambda s: 'Wooden Staff'), 'S> Wooden Staff 5k')


class Chat(unittest.TestCase):
    def test_everyday_phrases(self):
        cases = {'감사합니다': 'ty', '네': 'yes', '아니요': 'no', '귓 주세요': 'pm me', '가격 제안 주세요': 'pm me offers',
                 '축하해요': 'congrats!', '잘가요': 'bye', 'ㅋㅋㅋ': 'lol', '얼마예요?': 'how much?',
                 '고마워용': 'ty', '몇 레벨이에요?': 'what level are you?'}
        for ko, en in cases.items():
            self.assertEqual(korean_chat_phrase(ko), en, ko)

    def test_junk_guard(self):
        for junk in ('About Us', 'LOGIN JOIN', '{{if price_varies}}', 'No.1'):
            self.assertTrue(junk_english(junk), junk)
        for fine in ('S> Work Gloves 9m', 'Where are you training?', 'Thanks!'):
            self.assertFalse(junk_english(fine), fine)


if __name__ == '__main__':
    unittest.main()
