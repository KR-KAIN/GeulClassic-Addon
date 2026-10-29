import unittest
from unittest.mock import patch
from kain_maple_translator.glossary import (
    TERMS, SOURCE_URL, rule_translate, money_ko,
    expand_for_mt, normalize_mt_result,
)
from kain_maple_translator.translation import Translator
from kain_maple_translator.core import likely_english


class GlossaryTests(unittest.TestCase):
    def test_source_and_range(self):
        self.assertTrue(SOURCE_URL.startswith('https://meowdb.com/'))
        self.assertGreaterEqual(len(TERMS), 60)

    def test_trading(self):
        samples = {
            'S> 60% scroll 2m': '60% 주문서 200만 메소에 팝니다',
            'B> clean claw': '미강화 아대 삽니다',
            'J> kPQ': '커닝 파퀘 참가 원해요',
            'R> kPQ need 2': '커닝 파퀘 2명 모집해요',
            'WTS Fame': '인기도 팝니다',
            'a/w 10m': '즉시 구매가 1,000만 메소',
            'c/o 5m': '현재 최고 제시가 500만 메소',
            'res 3m': '최소 판매가 300만 메소',
            'cc plz': '채널 좀 바꿔 주세요',
            'stop KS': '스틸하지 마세요',
            'FM4 CH9': '9채널 자유시장 4번 방',
            'S> 60% scroll 2m @ FM4 CH9': '60% 주문서 200만 메소에 팝니다 (9채널 자유시장 4번 방)',
            'S> claw 100k ea': '아대 개당 10만 메소에 팝니다',
        }
        for text, expected in samples.items():
            with self.subTest(text=text):
                self.assertEqual(Translator().translate(text, 'en-ko'), expected)

    def test_reverse(self):
        self.assertEqual(Translator().translate('커닝 파퀘 3명 모집해요', 'ko-en'), 'R> kPQ need 3')
        self.assertEqual(Translator().translate('60% 주문서 200만 메소에 팝니다', 'ko-en'), 'S> 60% scroll 2m')

    def test_money(self):
        self.assertEqual(money_ko('1.5m'), '150만 메소')
        self.assertEqual(money_ko('100k'), '10만 메소')
        self.assertEqual(money_ko('2b'), '20억 메소')
        self.assertIsNone(money_ko('2meters'))

    def test_context_is_not_blind(self):
        self.assertIsNone(rule_translate('clean the room', 'en-ko'))
        self.assertEqual(expand_for_mt('clean the room', 'en-ko'), 'clean the room')
        self.assertEqual(expand_for_mt('S> clean claw 2m', 'en-ko'), 'Selling: unscrolled claw 2 million mesos')
        self.assertEqual(expand_for_mt('cc plz', 'en-ko'), 'change channel plz')

    def test_nick_not_sent_to_offline_model(self):
        with patch('kain_maple_translator.translation.translate_generic', return_value='안녕하세요') as mt:
            result = Translator().translate('Player123: hello there', 'en-ko')
            self.assertEqual(result, 'Player123 : 안녕하세요')
            self.assertEqual(mt.call_count, 1)
            self.assertEqual(mt.call_args[0][0], 'hello there')
        self.assertEqual(Translator().translate('Player123: S> 60% scroll 2m', 'en-ko'), 'Player123 : 60% 주문서 200만 메소에 팝니다')

    def test_terms_prepared_for_local_mt(self):
        with patch('kain_maple_translator.translation.translate_generic', return_value='커닝시티 파티 퀘스트에서 같이 할래요') as mt:
            result = Translator().translate('Anyone for kPQ?', 'en-ko')
            self.assertEqual(result, '커닝 파퀘 하실 분?')
            self.assertEqual(mt.call_count, 0)  # high-confidence game chat bypasses MT

    def test_short_trade_lines_ocr(self):
        self.assertTrue(likely_english('S> 2m', .9))
        self.assertTrue(likely_english('B> 10%', .8))
        self.assertFalse(likely_english('>', .99))


if __name__ == '__main__':
    unittest.main()
