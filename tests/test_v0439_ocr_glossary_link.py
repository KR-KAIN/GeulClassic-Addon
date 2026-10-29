"""v0.4.39 chat admission / damaged link / shorthand regressions."""
import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from kain_maple_translator.core import (RepeatGuard, ChatFrameTracker,
                                          should_translate_body, merge_chat_ocr)
from kain_maple_translator.vision import Line
from kain_maple_translator.glossary import rule_translate, money_ko
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.linked_ocr import repair_corrupt_bracket
from kain_maple_translator.uncertain_links import protect_uncertain_links, contains_uncertain_link


class Tests(unittest.TestCase):
    def test_repeat_1_8_seconds(self):
        guard=RepeatGuard()
        self.assertEqual(guard.seconds,1.8)
        self.assertTrue(guard.is_new('chat','S> 5m',0))
        self.assertFalse(guard.is_new('chat','S> 5m',1.2))
        self.assertTrue(guard.is_new('chat','S> 5m',1.9))

    def test_mixed_language_and_trade_price_gate(self):
        for text in ('Selling maple umbrella 5m','S> [한글아이템] PMO',
                     'm.att 23 팝니다', '150k', 'GFA 60%', 'LF> party',
                     'WTB BWG', 'Clean Slate Scroll 10%', 'WS 10%'):
            with self.subTest(text=text):
                self.assertTrue(should_translate_body(text,.35))
        self.assertFalse(should_translate_body('S> BWG 1m', .29))
        self.assertFalse(should_translate_body('안녕하세요',.9))

    def test_merge_low_confidence(self):
        parsed=merge_chat_ocr([Line('Player: Selling maple umbrella 5m',.35,(0,0,250,13))])
        self.assertEqual(len(parsed),1)
        self.assertEqual(parsed[0]['body'],'Selling maple umbrella 5m')

    def test_unchanged_frame_and_scroll_not_duplicated(self):
        def row(name,body,key,y):
            return {'nickname':name,'body':body,'visual_key':key,'rect':(1,y,140,12)}
        t=ChatFrameTracker()
        first=[row('Joe','same','a',0),row('Joe','hello','b',20)]
        self.assertEqual(len(t.new(first)),2)
        self.assertEqual(t.new(first),[])
        updated=[row('Joe','hello','b',0),row('Joe','same','c',20)]
        self.assertEqual([r['visual_key'] for r in t.new(updated)],['c'])
        self.assertEqual(t.new(updated),[])
        new=[row('Joe','hello','b',0),row('Joe','changed','d',20)]
        self.assertEqual([r['body'] for r in t.new(new)],['changed'])

    def test_korean_scrolls_existing_resolved_first(self):
        self.assertIn('장공',rule_translate('GFA 60%','en-ko'))
        self.assertIn('백의 주문서',rule_translate('WS','en-ko'))
        self.assertIn('한손검 공격력 주문서',rule_translate('Scroll for One-Handed Sword for ATT 60%','en-ko'))
        self.assertIn('완드 마력 주문서',rule_translate('Scroll for Wand for Magic ATT 70%','en-ko'))
        self.assertIn('가격',rule_translate('PMO','en-ko'))
        self.assertEqual(money_ko('5m'),'500만 메소')
        self.assertEqual(money_ko('2b'),'20억 메소')
        self.assertEqual(money_ko('500k'),'50만 메소')

    def test_corrupt_link_full_row_korean_fallback(self):
        raw='B> [人回 买] 50m'
        self.assertEqual(repair_corrupt_bracket(raw,'B> [신사의 콧수염] 50m',.94),
                         'B> [신사의 콧수염] 50m')
        self.assertIsNone(repair_corrupt_bracket(raw,'B> [신사의 콧수염] 60m',.99))
        self.assertIsNone(repair_corrupt_bracket(raw,'B> [신사의 콧수염] 50m',.7))
        self.assertIsNone(repair_corrupt_bracket('B> [Clean Claw] 50m','B> [신사의 콧수염] 50m',.98))

    def test_preserve_unrecognized_label_for_diagnostics(self):
        raw='B> [人回 买] 50m'
        self.assertTrue(contains_uncertain_link(raw))
        self.assertEqual(protect_uncertain_links(raw),raw)
        self.assertNotIn('아이템명 확인 필요',protect_uncertain_links(raw))

    def test_full_korean_retry_route_for_broken_link(self):
        class Engine:
            def __init__(self):
                self.ocr=self
                self.korean_ocr=self
                self.korean_link_ocr=None
            def recognize_lines(self, images):
                return SimpleNamespace(txts=['B> [人回 买] 50m'],scores=[.97],word_results=[None])
            def recognize_txt(self, images):
                return SimpleNamespace(txts=['B> [신사의 콧수염] 50m'],scores=[.94])
        engine=IncrementalChatOCR(Engine())
        engine.stage=defaultdict(float)
        blank=np.full((20,270,3),255,dtype=np.uint8)
        read=engine._candidates([(blank,blank)])
        self.assertEqual(read[0][0], 'B> [신사의 콧수염] 50m')

    def test_padding_and_interval_contract(self):
        import inspect
        from kain_maple_translator.fast_vision import ink_rows
        src=inspect.getsource(ink_rows)
        detect=inspect.getsource(IncrementalChatOCR.detect)
        self.assertIn('int(xs[0])-8',src)
        self.assertIn('int(xs[-1])+9',src)
        self.assertIn("self.clock()-self._last_at < .04",detect)
        self.assertIn('self.recovery_gate.block_reason(',detect)
        self.assertIn('self.recovery_gate.record(',detect)


if __name__=='__main__': unittest.main()
