"""v0.4.9: no fictitious scroll names and preserve Korean item links."""
import unittest
from kain_maple_translator.core import should_translate_body
from kain_maple_translator.scroll_intelligence import scroll_name
from kain_maple_translator.scroll_context import scroll_reference
from kain_maple_translator.natural_trade import trade_override
from kain_maple_translator.translation import Translator

class ClassicScrollAndKoreanItemTests(unittest.TestCase):
    def setUp(self):
        self.tr = Translator()

    def test_real_pet_scroll_names_and_tiers(self):
        self.assertEqual(scroll_name('Pet Equip Speed Scroll: Intermediate'),
                         '펫 장비 이동속도 60% 주문서')
        self.assertEqual(scroll_name('Pet Equip Speed Scroll Lesser'),
                         '펫 장비 이동속도 100% 주문서')
        self.assertEqual(scroll_name('Pet Equip Jump Scroll: Greater'),
                         '펫 장비 점프력 10% 주문서')

    def test_full_scroll_listing_not_partial_translated(self):
        self.assertIn('펫 장비 이동속도 60% 주문서',
                      self.tr.translate('S> Pet Equip Speed Scroll: Intermediate 90k','en-ko'))
        self.assertIn('장공 60% 주문서',self.tr.translate('B> GFA 60%','en-ko'))

    def test_korean_item_name_kept_in_megaphone_sales(self):
        cases=[
            ('S> [한글 아이템명] 500k PMO','[한글 아이템명]'),
            ('B> [펫 장비 이동속도 주문서: 중급] 90k','[펫 장비 이동속도 주문서: 중급]'),
            ('S> [별빛 날개 모자] 1.5m','[별빛 날개 모자]'),
        ]
        for src,item in cases:
            with self.subTest(src=src):
                self.assertTrue(should_translate_body(src,.90))
                result=self.tr.translate(src,'en-ko')
                self.assertIn(item,result)
                self.assertIn('메소',result)
                self.assertNotIn('S>',result)
                self.assertNotIn('B>',result)

    def test_already_korean_non_market_chat_is_not_retranslated(self):
        self.assertFalse(should_translate_body('안녕하세요. 오늘도 좋은 하루!',.90))

    def test_ocr_corruption_does_not_fabricate_scroll_item(self):
        for sample in ('Bazlud att +10', 'ER .I / [III]', 'I Speed: LV30 Warrior pants'):
            with self.subTest(sample=sample):
                self.assertIsNone(scroll_name(sample))
                self.assertIsNone(scroll_reference(sample))

    def test_korean_item_plus_offer_without_price(self):
        out=self.tr.translate('S> [노란 리본] PMO','en-ko')
        self.assertIn('[노란 리본]',out)
        self.assertIn('팝니다',out)
        self.assertIn('귓말',out)

    def test_price_preserved_for_existing_trade(self):
        self.assertEqual(self.tr.translate('S> GFA 60% 790k','en-ko'),
                         '장공 60% 주문서 79만 메소에 팝니다')

if __name__=='__main__':unittest.main()
