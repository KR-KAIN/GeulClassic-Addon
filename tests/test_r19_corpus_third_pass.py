"""R19 corpus audit, third pass: OCR misspellings and short chat lines the
offline model got wrong ('휠 CH10', '감사합니다.', '나를 도울 수 있습니다')."""
import unittest

from kain_maple_translator.chat_cleanup import party_post, prepare_chat
from kain_maple_translator.chat_fixups import casual_request
from kain_maple_translator.scroll_intelligence import scroll_trade
from kain_maple_translator.translation import Translator


class OcrWords(unittest.TestCase):
    def test_misspellings(self):
        self.assertEqual(prepare_chat('S> Famle 50k'), 'S> FAME 50k')
        self.assertIn('staff magic attack 60%', prepare_chat('S> Staf magic at 60% 300k'))
        self.assertIn('earring', prepare_chat('B> Eamtng int 60%'))
        self.assertIn('60%', prepare_chat('S> Glove att 6n% 120k'))
        self.assertIn('ATT', prepare_chat('S> ΔTT 60% gloves'))
        self.assertIn('shoe', prepare_chat('B> sho speed 60%').lower())
        self.assertEqual(prepare_chat('can vou help me'), 'can you help me')
        self.assertEqual(prepare_chat('loong for gpq guild'), 'looking for gpq guild')
        self.assertNotIn('11111', prepare_chat('11111 S> warrior gloves 50k'))

    def test_trade_marker(self):
        self.assertTrue(prepare_chat('BXSCROLLS NO DEE').startswith('B> '))


class Scrolls(unittest.TestCase):
    def test_stat_first_with_helm(self):
        self.assertEqual(scroll_trade('S> STR 60% helm'), '투구 힘 60% 주문서 팝니다')
        self.assertEqual(scroll_trade('S> strength 60% helm'), '투구 힘 60% 주문서 팝니다')
        self.assertEqual(scroll_trade('S> helm str 60%'), '투구 힘 60% 주문서 팝니다')

    def test_no_scroll_without_rate(self):
        self.assertIsNone(scroll_trade('S> str helm'))


class ShortChat(unittest.TestCase):
    def test_whisper(self):
        self.assertEqual(casual_request('WHISPER CH10'), '귓말 주세요 (10채널)')
        self.assertEqual(casual_request('whisper me pls'), '귓말 주세요')

    def test_help(self):
        self.assertEqual(casual_request('pls help'), '도와주세요')
        self.assertEqual(casual_request('help me plz'), '도와주세요')
        self.assertEqual(casual_request('squishy pls help'), 'squishy, 도와주세요')
        self.assertEqual(casual_request('can u help me'), '도와줄 수 있어요?')
        self.assertEqual(casual_request('can anyone help me'), '도와주실 분 있나요?')
        self.assertEqual(casual_request('need help'), '도움이 필요해요')
        self.assertIsNone(casual_request('help'))

    def test_guild_and_party(self):
        self.assertEqual(casual_request('looking for gpq guild'), '길드 퀘스트 하는 길드 찾아요')
        self.assertEqual(casual_request('lf active guild'), '활동적인 길드 찾아요')
        self.assertEqual(casual_request('looking for 2 ppl for party'), '파티원 2명 구해요')
        self.assertEqual(casual_request('lf for 3 more'), '파티원 3명 구해요')

    def test_party_posts(self):
        self.assertEqual(party_post(prepare_chat('d>PQ RUSH')), '파티 퀘스트 연속 진행 참가 원해요')
        self.assertEqual(party_post(prepare_chat('J>KPQ BONlS')), '커닝 파퀘 보너스 구간 참가 원해요')


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = Translator(body_only=True)

    def tr(self, text):
        return self.t.translate(text, 'en-ko')

    def test_lines(self):
        self.assertEqual(self.tr('WHISPER CH10'), '귓말 주세요 (10채널)')
        self.assertEqual(self.tr('Sauishy pls help'), 'squishy, 도와주세요')
        self.assertEqual(self.tr('S> STRENGTH 60% helm'), '투구 힘 60% 주문서 팝니다')
        self.assertEqual(self.tr('S> Staf magic at 60% 300k'), '스태프 마력 60% 주문서 30만 메소에 팝니다')
        self.assertEqual(self.tr('B> Shoe Speed 10% scroll'), '신발 이동속도 10% 주문서 삽니다')
        self.assertEqual(self.tr('S> granet 2k each'), '가넷 팝니다. 개당 2천 메소')

    def test_no_def(self):
        out = self.tr('BXSCROLLS NO DEE')
        self.assertTrue(out.startswith('주문서 삽니다'), out)
        self.assertIn('방어력 주문서 제외', out)

    def test_fourth_pass(self):
        # party post followed by a trade post keeps the trade intact
        out = self.tr('J PQ bonus CandvCanez· S> Fame 5k')
        self.assertTrue(out.startswith('파티 퀘스트 보너스 구간 참가 원해요'), out)
        self.assertIn('인기도', out)
        self.assertIn('팝니다', out)
        # OCR crumbs never come back as hearts
        self.assertNotRegex(self.tr('JPQ BONus @@@@②@@ Denyey ·Po Rom s @@@@@@'), '[ღ♥❤]')
        self.assertEqual(self.tr('B>ALL NX YOU DONT WANT 1OK EA!'), '안 쓰는 캐시템 전부 삽니다. 개당 1만 메소')
        out = self.tr('B>SCROLLS NO DEFB>ALL NX YOU DONT WANT 1OK EA!')
        self.assertIn('주문서 삽니다 (방어력 주문서 제외)', out)
        self.assertIn('안 쓰는 캐시템 전부 삽니다', out)
        self.assertEqual(self.tr('i iust wanna honus round!'), '보너스 구간 하고 싶어요')
        self.assertEqual(self.tr('u wanna trade?'), '거래할래요?')
        self.assertEqual(self.tr('wanna pq?'), '파티 퀘스트 갈래요?')
        self.assertEqual(self.tr('S>60% bow atk 95k!'), '활 공격력 60% 주문서 9만 5천 메소에 팝니다')
        self.assertEqual(self.tr('Ruvina Farina L1IK 60% 65k ea 1111111 R>Nire clean Fmerald Farrinas'),
                         '귀고리 행운 60% 주문서 삽니다. 개당 6만 5천 메소 · 미강화 에메랄드 귀고리 삽니다')
        self.assertEqual(self.tr('WWW. U4N . (0 /TW->Mesos Hotsale,Lowest Price 100K only$4 4'), '[메소 현금 거래 광고]')
        self.assertEqual(self.tr('RPO RUSH MAX HASTE'), '커닝 파퀘 연속 진행 참가 원해요 (헤이스트 있음)')
        self.assertEqual(self.tr('J> RUSH LVL 35 with HASTE'), '파티 퀘스트 연속 진행 참가 원해요 (35레벨, 헤이스트 있음)')
        self.assertEqual(self.tr('R>Sauishv Shne'), '물컹물컹한 신발 삽니다')
        self.assertEqual(self.tr('SELLING SOME NX CLOTHES!!!'), '캐시 옷!!! 팝니다')
        self.assertEqual(self.tr('S> Ink and wash thought ring 700k'), '수묵화 말풍선 반지 팝니다. 가격 70만 메소')
        self.assertEqual(self.tr('[요정의 날개] Sell fairy wing PMO! Buy cromi I 50 wand PM'),
                         '[요정의 날개] 팝니다. 귓말 주세요 · 크로미 I 50 완드 삽니다. 귓말 주세요')
        self.assertEqual(self.tr('S> (3) claw att 60% 170k each --——- S clean Work Gtoves 2.5k each'),
                         '(3) 아대 공격력 60% 팝니다. 개당 17만 메소 · 미강화 노가다 목장갑 팝니다. 개당 2천 500 메소')
        out = self.tr('B> Level 40 Bowman PANTS/TOP (m). WHISPER')
        self.assertNotIn('WHISPER', out)
        self.assertIn('귓말 주세요', out)
        self.assertNotIn('ea ch', prepare_chat('S> wg 190k each'))

    def test_fifth_pass(self):
        self.assertEqual(self.tr('J.PQ RUSH,'), '파티 퀘스트 연속 진행 참가 원해요')
        self.assertEqual(self.tr('B>scroll for wand magic att 60% u'), '완드 마력 60% 주문서 삽니다')
        self.assertEqual(self.tr('huvina nure water700u'), '맑은 물 700 삽니다')
        self.assertEqual(self.tr('B>TOBI 1.1M S>+2 BAZLUD PMO'),
                         '토비 표창 삽니다. 가격 110만 메소 · +2 베즐러드 팝니다. 귓말 주세요')
        self.assertEqual(self.tr('S>WOL BIS 2K EACH @@@@@@'), '월비 표창 팝니다. 개당 2천 메소')
        self.assertEqual(self.tr('J>PQ RUSHHHHHHHHHHHHKIIM 32@@'), '파티 퀘스트 연속 진행 참가 원해요 (32레벨)')
        self.assertEqual(self.tr('B>1evel30 claw'), '레벨 30 아대 삽니다')
        self.assertEqual(self.tr('[장팔사모] S>this c/o 700k'), '[장팔사모] · 이 아이템 팝니다. 현재 최고 제시가 70만 메소')
        self.assertEqual(self.tr('B> All your junk nx 15keaeech'), '잡캐시템 전부 삽니다. 개당 1만 5천 메소')
        self.assertEqual(self.tr('S> Mithril Pole Arm 59 att 100k'), '미스릴 폴암 59 공격력 팝니다. 가격 10만 메소')
        self.assertIn('오팔의 원석', self.tr('B>Opal ores'))
        self.assertIn('가격 제안 받습니다', self.tr('S > White Label Ring 500k > open to offers, ty'))
        # a real cash-for-mesos advert keeps its label, '$' stays for RMT detection
        self.assertEqual(self.tr('WTS mesos $5 per 100k www.mesoshop.com'), '[메소 현금 거래 광고]')
        self.assertEqual(self.tr('Ball is life'), self.tr('Ball is life'))
        self.assertFalse(prepare_chat('Ball is life').startswith('B>'))

    def test_live_session(self):
        for line in ('b>scrolls J>bonus~', 'h>scrolls 1>honus', 'b>scrolls, J>bonus~', 'h>scrolls Ahonus', 'b>scrolls Ibonus:'):
            self.assertEqual(self.tr(line), '주문서 삽니다 · 파티 퀘스트 보너스 구간 참가 원해요', line)
        self.assertEqual(self.tr('S> WOLBIE THROWING STARS 1.5K EACH @@©@@@@ T> 2 WOL BIFS FOR FAMF @@@@'),
                         '월비 표창 팝니다. 개당 1천 500 메소 · 2 월비 표창 → 인기도 교환')
        self.assertEqual(self.tr('anyone spare mp pots? ran out of mesos tyyyyy~~'),
                         'MP 포션 남는 분 있나요? 메소가 다 떨어졌어요 고마워요')
        self.assertEqual(self.tr('T>Tiger mask or prison pants for cute mouse ears trade me@@@@@@'),
                         '타이거 마스크 또는 죄수복 하의 → 귀여운 쥐 귀 교환해요. 거래 걸어주세요')
        self.assertEqual(self.tr('S> STEEL IGNOR (LVL 20 CLAW) 8K LESS THAN SHOP@@@@@@'),
                         '스틸 이고르 (레벨 20 아대) 8천 메소 (상점가보다 저렴) 팝니다')
        self.assertEqual(self.tr('B>halo can swap NX items/messos'), '천사의 헤일로 삽니다 (캐시 아이템/메소 교환 가능)')
        self.assertEqual(self.tr('DPO honus'), '파티 퀘스트 보너스 구간 참가 원해요')
        self.assertEqual(self.tr('J)> PQ@@@@@@3QqQ@ΦeΦ@@'), '파티 퀘스트 참가 원해요')
        self.assertEqual(self.tr('R>Rlack Crvetal Ores 150n ea'), '흑수정 원석 삽니다. 개당 1500')
        self.assertEqual(self.tr('JPQ:2016whoadude:@@@@@@'), '파티 퀘스트 참가 원해요 · 2016whoadude')
        self.assertEqual(self.tr('B>CHINESE HAT 15K starting @@@@'), 'CHINESE 모자 1만 5천 메소부터 삽니다')
        self.assertIn('귓말로 가격 제안 주세요', self.tr('[Frameless Glasses] B> FRAMELESS GLASSES! WHISPER OF FER'))
        self.assertIn('펫 이동속도 60%', self.tr('B>PET SPEED 60 =42k ea'))
        # '750Meen' is '750 meso', never 750M (7억 5천만)
        self.assertEqual(self.tr('R>PureWater 750Meen'), '맑은 물 750 메소 삽니다')
        self.assertNotIn('억', self.tr('I>PQ V 2:@@@@@@ Krvsta·R>PureWater 750Meen'))
        self.assertEqual(self.tr('S> wand 2Mea'), '완드 팝니다. 개당 200만 메소')
        self.assertEqual(self.tr('ANY JPQ@@@@@@@@e@@@e6c2@@@2a'), '파티 퀘스트 참가 원해요 (아무 파티나)')
        self.assertEqual(self.tr('J)PQ stage in BONUS @@@@@'), '파티 퀘스트 보너스 구간 참가 원해요')
        self.assertEqual(self.tr('S>ToBi Throwing Stars 1.3m @@@@@@'), '토비 표창 팝니다. 가격 130만 메소')
        self.assertEqual(self.tr('R> KPQ 24 rogue!'), '커닝 파퀘 모집해요 (24레벨, 도적)')
        self.assertEqual(self.tr('R> 2 more'), '2명 더 구해요')
        self.assertIn('파란 포션', self.tr('BUYING BLUE POTIONSSS!@#!@!@#@!'))
        self.assertIn('장갑 마력 60% 주문서', self.tr('S GLOVES MAGIC ATT 60% I 20OR DaIA'))
        # 'PM ME' keeps the space before the next word
        self.assertIn('PM ME YClacconabach', prepare_chat('S>ANGEL HALO 370K PM ME YClacconabach'))
        self.assertEqual(self.tr('JPQ> RusH2@@@e@@@'), '파티 퀘스트 연속 진행 참가 원해요')
        # 'a bonus' in a sentence is not a party marker
        self.assertNotIn('J>', prepare_chat('i got a bonus today'))

    def test_level_plus(self):
        self.assertEqual(party_post(prepare_chat('R> Rush Lv 25+ only!')), '파티 퀘스트 연속 진행 모집해요 (25레벨 이상만)')
        self.assertEqual(party_post(prepare_chat('R> KPQ lvl 30+')), '커닝 파퀘 모집해요 (30레벨 이상)')


if __name__ == '__main__':
    unittest.main()
