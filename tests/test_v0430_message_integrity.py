"""Regression cases reported from a real, four-line Maple chat recording.
All tests are deterministic logic tests, not a claim of Windows OCR accuracy.
"""
import unittest
from unittest.mock import patch
import numpy as np

from kain_maple_translator.core import ChatFrameTracker, likely_english, should_translate_body
from kain_maple_translator.uncertain_links import contains_uncertain_link, protect_uncertain_links
from kain_maple_translator.natural_trade import priced_item_list, trade_override
from kain_maple_translator.row_admission import classified_chat_rows, _CLASSIFIED_CACHE

class MessageIntegrityTests(unittest.TestCase):
    def row(self, text='Salad k 삽니다', key='original', y=10):
        return {'nickname':'Hyouddoulssei','body':text,'visual_key':key,
                'rect':(5,y,180,15),'confidence':.96}

    def test_transparent_background_changes_do_not_repeat_same_message(self):
        tracker=ChatFrameTracker()
        self.assertEqual(len(tracker.new([self.row(key='bg_1')])),1)
        for key in ('bg_2','bg_3','bg_4','bg_5'):
            self.assertEqual(tracker.new([self.row(key=key)]),[])

    def test_ocr_text_drift_when_pixels_equal_is_not_new(self):
        tracker=ChatFrameTracker()
        tracker.new([self.row('신사의 콧수염',key='stable')])
        self.assertEqual(tracker.new([self.row('신사의 롯수염',key='stable')]),[])

    def test_changed_price_is_new_even_if_visual_key_same(self):
        tracker=ChatFrameTracker()
        tracker.new([self.row('S> 150k',key='stable')])
        self.assertEqual(len(tracker.new([self.row('S> 160k',key='stable')])),1)

    def test_repeated_actual_new_row_after_scroll_is_kept(self):
        tracker=ChatFrameTracker()
        tracker.new([self.row('same',key='one',y=10),self.row('same',key='two',y=30)])
        result=tracker.new([self.row('same',key='two',y=10),self.row('same',key='three',y=30)])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['visual_key'],'three')

    def test_bracketed_hangul_does_not_disable_english(self):
        cases=('how much for [잉크 앤 워시 말풍선]?',
               'who has [신사의 콧수염]?',
               'gl with [신사의 콧수염] lol')
        for case in cases:
            with self.subTest(case=case):
                self.assertTrue(likely_english(case))
                self.assertTrue(should_translate_body(case))
        self.assertFalse(likely_english('[신사의 콧수염] 삽니다'))

    def test_linked_multi_item_prices_remain_separate(self):
        actual=priced_item_list('S> [요정의 날개] 150k [태극부채] 30k')
        self.assertEqual(actual,'[요정의 날개] 15만 메소, [태극부채] 3만 메소 팝니다')

    def test_polite_contact_does_not_consume_price(self):
        actual=trade_override('WTS [신사의 콧수염] 80k pls pm')
        self.assertIn('8만 메소',actual)
        self.assertNotIn('80k',actual)
        self.assertNotIn('pls',actual)
        self.assertIn('귓말 주세요',actual)

    def test_corrupted_hanja_or_empty_item_link_is_marked_uncertain(self):
        for text in ('S> [人回 买] 80k OBO', 'B> [ ] 10k'):
            self.assertTrue(contains_uncertain_link(text))
            result=protect_uncertain_links(text)
            self.assertEqual(result,text)  # Keep original OCR for diagnosis
        source='S> [신사의 콧수염] 80k'
        self.assertFalse(contains_uncertain_link(source))
        self.assertEqual(protect_uncertain_links(source),source)

    def test_uncertain_colored_glyph_without_banner_does_not_change_general_chat(self):
        image=np.zeros((50,200,3),dtype=np.uint8)
        fake={'nickname':'Neux','body':'oo shops', 'rect':(2,5,100,16),
              'confidence':.99,'source_white_body':False,
              'announcement_hint':False}
        # Isolate the channel-classification decision from OCR and palettes.
        with patch('kain_maple_translator.core.merge_chat_ocr',return_value=[fake]),\
             patch('kain_maple_translator.megaphone.row_appearance',return_value={
                 'kind':'unknown','prefix':'[확성]','tone':'blue','band_color':''}):
            _CLASSIFIED_CACHE.clear()
            try: result=classified_chat_rows([],image,0,0)
            finally: _CLASSIFIED_CACHE.clear()
        self.assertEqual(result[0]['kind'],'normal')
        self.assertEqual(result[0]['tone'],'none')

if __name__=='__main__':
    unittest.main()

class LinkedKoreanSuffixTests(unittest.TestCase):
    def test_korean_trade_suffix_is_recovered_without_replacing_link(self):
        from collections import defaultdict
        from types import SimpleNamespace
        from kain_maple_translator.fast_vision import IncrementalChatOCR

        class Recognizer:
            def __init__(self):
                self.ocr=self
                self.korean_ocr=self
                self.korean_link_ocr=None
            def recognize_lines(self,images):
                return SimpleNamespace(txts=['[신사의 콧수염]'],scores=[.92],word_results=[None])
            def recognize_txt(self,images):
                return SimpleNamespace(txts=['[신사의 콧수염] 팝니다'],scores=[.97])
        engine=IncrementalChatOCR(Recognizer())
        engine.stage=defaultdict(float)
        blank=np.full((18,200,3),255,dtype=np.uint8)
        result=engine._candidates([(blank,blank)])
        self.assertEqual(result[0][0],'[신사의 콧수염] 팝니다')
