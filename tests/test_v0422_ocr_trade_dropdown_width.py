"""Regression for live 2026-10-24 Classic megaphone + UI reports."""
from __future__ import annotations
import unittest
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import patch
import numpy as np
import cv2
from kain_maple_translator.core import merge_chat_ocr, should_translate_body
from kain_maple_translator.translation import Translator
from kain_maple_translator.vision import (Line, _dedupe_ocr_boxes, TextRecognizer,
    colorful_chat_regions, enhance_colored_chat)

ROOT=Path(__file__).resolve().parents[1]
@dataclass
class Box:
    text:str
    rect:tuple
    confidence:float=0.86

class RealScreenshotRegressions(unittest.TestCase):
    def test_meba_korean_selling_statement(self):
        self.assertTrue(should_translate_body('MEBA 삽니다',.9))
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('not general AI')):
            self.assertEqual(Translator().translate('MEBA 삽니다','en-ko'),'메바 삽니다')
    def test_korean_item_for_price_with_english_remnant(self):
        source='[화이트 초코 버니] for 450k. Also have Blank Eye Patc E'
        self.assertTrue(should_translate_body(source,.86))
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('not general AI')):
            result=Translator().translate(source,'en-ko')
        self.assertIn('45만 메소',result)
        self.assertIn('[화이트 초코 버니]',result)
        self.assertIn('Blank Eye Patc E',result)
        self.assertIn('있습니다',result)
    def test_broken_ocr_does_not_hallucinate_missing_item_name(self):
        from kain_maple_translator.megaphone_item_translation import translate_announcement_trade
        result=translate_announcement_trade('[화이트 초코 버니] for 450k. Also have Blank Eye Patc E')
        self.assertNotIn('Blank Eye Patch',result)
    def test_comma_price_preserved(self):
        from kain_maple_translator.megaphone_item_translation import translate_announcement_trade
        self.assertIn('45만 메소',translate_announcement_trade('[화이트 초코 버니] for 450k'))
    def test_reflow_multiline_chat_continuation(self):
        result=merge_chat_ocr([Box('Sami : [화이트 초코 버니] for 450k.',(10,40,300,18)),
                               Box('Also have Blank Eye Patc E',(14,61,270,18))])
        self.assertEqual(len(result),1)
        self.assertIn('Also have Blank Eye Patc E',result[0]['body'])
    def test_nonadjacent_ocr_is_not_attached(self):
        result=merge_chat_ocr([Box('Anna: S> meba',(10,40,150,16)),
                               Box('Quest log updated',(10,75,220,18))])
        self.assertEqual(len(result),1)
        self.assertNotIn('Quest',result[0]['body'])
    def test_longer_complete_ocr_outvotes_fragment(self):
        result=_dedupe_ocr_boxes([Line('noran : MEBA',.99,(8,10,275,20)),
                                  Line('noran : MEBA 삽니다',.73,(8,10,275,20))])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].text,'noran : MEBA 삽니다')
    def test_consecutive_distinct_lines_not_merged(self):
        result=_dedupe_ocr_boxes([Line('A : first',.91,(8,10,240,18)),
                                  Line('B : second',.91,(8,36,240,18))])
        self.assertEqual(len(result),2)
    def test_color_region_detects_yellow_pink_megaphones(self):
        frame=np.full((100,420,3),30,dtype=np.uint8)
        frame[10:34]=[10,180,230]
        frame[54:79]=[188,145,205]
        cv2.putText(frame,'S> MEBA',(10,28),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
        self.assertEqual(len(colorful_chat_regions(frame)),2)
    def test_no_color_retry_on_normal_grayscale_chat(self):
        frame=np.full((45,420,3),20,dtype=np.uint8)
        self.assertEqual(colorful_chat_regions(frame),[])
        self.assertEqual(enhance_colored_chat(frame).shape,frame.shape)
    def test_colored_crop_is_secondary_when_main_is_incomplete(self):
        frame=np.full((60,400,3),30,dtype=np.uint8)
        frame[10:42]=[10,180,230]
        inst=TextRecognizer.__new__(TextRecognizer)
        calls=[]
        def f(image,x,y,scale):
            calls.append((x,y,image.shape))
            if len(calls)==1:return [Line('Rox : Also have Blank Eye Patc E',.83,(5,12,280,16))]
            return [Line('Rox : Also have Blank Eye Patch',.85,(5,12,300,16))]
        with patch.object(TextRecognizer,'_detect_once',side_effect=f):
            result=inst.detect(frame,0,0)
        self.assertGreaterEqual(len(calls),2)
        self.assertTrue(any('Patch' in row.text for row in result))
    def test_all_chat_panes_disable_horizontal_scroll(self):
        text=(ROOT/'kain_maple_translator/main.py').read_text('utf-8')
        self.assertIn('scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)',text)
        self.assertIn('content.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)',text)
        self.assertIn('row.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)',text)
        self.assertIn('caption.setWordWrap(True)',text)
    def test_dropdown_safe_while_popup_active(self):
        text=(ROOT/'kain_maple_translator/main.py').read_text('utf-8')
        self.assertIn("getattr(QApplication, 'activePopupWidget', lambda: None)()",text)
        self.assertIn('self.mode.setMaxVisibleItems(8)',text)
    def test_ocr_uses_bounded_color_retry(self):
        text=(ROOT/'kain_maple_translator/vision.py').read_text('utf-8')
        self.assertIn('for x,y,w,h in colorful_chat_regions(bgr):',text)
        self.assertIn('return bands[:2]',text)

if __name__=='__main__':unittest.main()
