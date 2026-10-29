"""R10: deterministic market shorthand regression; no model or game access."""
import unittest
from kain_maple_translator.natural_trade import trade_override, general_chat_override, _item
from kain_maple_translator.translation import Translator


class TestR10TradeTerms(unittest.TestCase):
    def setUp(self):
        self.tr = Translator()

    def test_uncertain_s_less_never_assumed_sell(self):
        out = self.tr.translate_fast('S< Tons of junk nx 16k!', 'en-ko')
        self.assertIn('거래 방향 확인 필요', out)
        self.assertIn('잡캐시템', out)
        self.assertIn('1만 6천 메소', out)
        self.assertNotIn('팝니다', out)
        self.assertNotIn('삽니다', out)

    def test_uncertain_s_less_unknown_item_not_forced(self):
        self.assertIsNone(trade_override('S< UNKNOWN THING 16k'))

    def test_incomplete_buy_fragment(self):
        out = self.tr.translate_fast('B> for 170k need 2 more only pm', 'en-ko')
        self.assertIn('품목 미표기', out)
        self.assertIn('2개 더 삽니다', out)
        self.assertIn('17만 메소', out)
        self.assertIn('개당 여부 미표기', out)
        self.assertIn('귓말만', out)
        self.assertNotIn('for 170k', out)

    def test_guard_unrecognized_partial_market_clause(self):
        self.assertIsNone(trade_override('B> for 170k need only pm'))
        self.assertIsNone(trade_override('B> sword need 2 more only pm'))

    def test_scroll_bow_alias_only_with_percentage(self):
        self.assertEqual(_item('BOW 60%'), '활 공격력 주문서 60%')
        self.assertEqual(_item('Xbow 30%'), '석궁 공격력 주문서 30%')
        self.assertEqual(_item('bow'), 'bow')
        out=self.tr.translate_fast('B> BOW 60% 100k', 'en-ko')
        self.assertIn('활 공격력 주문서 60%', out)
        self.assertIn('10만 메소', out)
        self.assertIn('삽니다', out)

    def test_junk_nx(self):
        self.assertEqual(_item('junk NX'), '잡캐시템')
        self.assertIn('잡캐시템', self.tr.translate_fast('S> junk NX 16k', 'en-ko'))

    def test_fame_exchange_only_exact(self):
        self.assertEqual(general_chat_override('fame - fame and trade'), '인기도 맞교환합니다')
        self.assertEqual(self.tr.translate_fast('fame for fame', 'en-ko'), '인기도 맞교환합니다')
        self.assertIsNone(general_chat_override('Flame - fame and trade'))
        self.assertIsNone(general_chat_override('Fame is useful'))

    def test_existing_sp_reset_price_and_ea(self):
        self.assertEqual(self.tr.translate_fast('S> SP RESET 10k ea','en-ko'),
                         'SP 초기화권 팝니다. 개당 1만 메소')

    def test_hangul_item_link_unchanged(self):
        out=self.tr.translate_fast('S> [장갑 공격력 주문서] 450k','en-ko')
        self.assertIn('[장갑 공격력 주문서]', out)
        self.assertIn('45만 메소',out)
        self.assertEqual(out.count('[장갑 공격력 주문서]'),1)

    def test_nickname_kept_separate(self):
        out=self.tr.translate_fast('Alice : B> BOW 60% 100k','en-ko')
        self.assertTrue(out.startswith('Alice : '))
        self.assertIn('활 공격력 주문서 60%', out)
        self.assertIn('10만 메소',out)

    def test_normal_prose_no_trade_inference(self):
        self.assertIsNone(trade_override('Can I buy bow?'))
        self.assertIsNone(general_chat_override('This bow is great'))

    def test_batched_path_uses_same_override(self):
        rows=['S> SP RESET 10k ea', 'B> BOW 60% 100k', 'fame for fame']
        expected=[self.tr.translate_fast(v,'en-ko') for v in rows]
        self.assertEqual(self.tr.translate_many(rows,'en-ko'),expected)


if __name__=='__main__':
    unittest.main()
