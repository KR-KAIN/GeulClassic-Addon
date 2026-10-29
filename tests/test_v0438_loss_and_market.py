"""v0.4.38 regression: conservative OCR refresh and complete scroll rules."""
import unittest
from kain_maple_translator.core import should_translate_body, ChatFrameTracker
from kain_maple_translator.scroll_context import scroll_reference
from kain_maple_translator.glossary import rule_translate

class Tests(unittest.TestCase):
    def test_unbracketed_sale(self):
        self.assertTrue(should_translate_body('Selling maple umbrella 5m', .97))
    def test_scroll_keyword_in_mixed_chat(self):
        self.assertTrue(should_translate_body('장비 ATT 60% offer', .97))
        self.assertTrue(should_translate_body('GFA 60%', .97))
    def test_do_not_translate_korean_only(self):
        self.assertFalse(should_translate_body('한글 아이템 팝니다', .95))
    def test_short_price_context(self):
        self.assertTrue(should_translate_body('3m', .90))
    def test_scroll_for_sword(self):
        self.assertEqual(scroll_reference('Scroll for One-Handed Sword for ATT 60%'),'한손검 공격력 주문서 60%')
    def test_scroll_for_wand(self):
        self.assertEqual(scroll_reference('Scroll for Wand for Magic ATT 70%'),'완드 마력 주문서 70%')
    def test_gfa_not_overall(self):
        self.assertIn('장공', rule_translate('GFA 60%','en-ko'))
    def test_existing_ws_css(self):
        self.assertIn('백의', rule_translate('WS','en-ko'))
        self.assertIn('순백', rule_translate('CSS','en-ko'))
    def test_stationary_message_not_duplicate(self):
        t=ChatFrameTracker()
        def r(text,key):return {'nickname':'Alice','body':text,'visual_key':key}
        self.assertEqual(len(t.new([r('S> GFA 60%','a')])),1)
        self.assertEqual(t.new([r('S> GFA 60%','b')]),[])
    def test_scrolled_line_does_not_duplicate(self):
        t=ChatFrameTracker()
        def r(text,key):return {'nickname':'Alice','body':text,'visual_key':key}
        t.new([r('A','1'),r('B','2')]);self.assertEqual(len(t.new([r('B','3'),r('C','4')])),1)
    def test_new_repeat_can_follow_scroll(self):
        t=ChatFrameTracker()
        def r(text,key):return {'nickname':'Alice','body':text,'visual_key':key}
        t.new([r('Repeat','1'),r('Next','2')]);self.assertEqual(len(t.new([r('Next','2'),r('Repeat','3')])),1)

if __name__ == '__main__':unittest.main()
