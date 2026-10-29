"""Regression for Windows replay failure in v0.4.30 (line 81)."""
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from kain_maple_translator.vision import Line
from kain_maple_translator.row_admission import classified_chat_rows, _CLASSIFIED_CACHE
from kain_maple_translator.megaphone import row_appearance


def image(foreground, background=(25,25,25), text='Alice ; S> WG 220k'):
    pixels=np.full((32,650,3),background,dtype=np.uint8)
    cv2.putText(pixels,text,(5,24),cv2.FONT_HERSHEY_SIMPLEX,.65,foreground,1,cv2.LINE_AA)
    return pixels


class ColorGateRegression(unittest.TestCase):
    def setUp(self):
        _CLASSIFIED_CACHE.clear()

    def test_bannerless_magenta_body_is_not_demoted_to_general(self):
        # Matches the failing second iteration in scripts/replay_ocr_fixtures.py.
        pixels=image((200,100,240))
        row=classified_chat_rows([Line('Alice ; S> WG 220k',.98355,(2,8,208,20))],pixels,0,0)[0]
        self.assertNotEqual(row['kind'],'normal',row)
        self.assertEqual(row['tone'],'pink',row)
        self.assertTrue(row.get('glyph_color_confirmed'),row)
        self.assertFalse(row.get('band_color'),row)

    def test_uncertain_classification_without_real_pixel_proof_is_general(self):
        # Keep the important v0.4.30 ordinary-chat safety net.
        pixels=image((245,245,245))
        fake={'nickname':'Alice','body':'oo shops','rect':(2,8,208,20),
              'confidence':.99,'announcement_hint':False}
        with patch('kain_maple_translator.core.merge_chat_ocr',return_value=[fake]), \
             patch('kain_maple_translator.megaphone.row_appearance',return_value={
                 'kind':'unknown','prefix':'[확성]','tone':'pink',
                 'band_color':'','text_color':'#dc5db8'}):
            row=classified_chat_rows([],pixels,0,0)[0]
        self.assertEqual(row['kind'],'normal',row)
        self.assertEqual(row['tone'],'none',row)

    def test_real_white_body_with_colored_nickname_stays_general(self):
        pixels=np.full((32,650,3),(25,25,25),dtype=np.uint8)
        cv2.putText(pixels,'Alice ;',(5,24),cv2.FONT_HERSHEY_SIMPLEX,.65,(200,100,240),1,cv2.LINE_AA)
        cv2.putText(pixels,'S> WG 220k',(105,24),cv2.FONT_HERSHEY_SIMPLEX,.65,(245,245,245),1,cv2.LINE_AA)
        row=classified_chat_rows([Line('Alice ; S> WG 220k',.99,(2,8,300,20))],pixels,0,0)[0]
        self.assertEqual(row['kind'],'normal',row)
        self.assertTrue(row.get('source_white_body'),row)

    def test_colored_banner_stays_announcement(self):
        pixels=image((30,70,80),(195,220,95))
        row=classified_chat_rows([Line('Alice ; S> WG 220k',.99,(2,8,208,20))],pixels,0,0)[0]
        self.assertNotEqual(row['kind'],'normal',row)
        self.assertEqual(row['tone'],'cyan',row)

    def test_no_announcement_on_plain_white_chat(self):
        pixels=image((245,245,245))
        row=classified_chat_rows([Line('Alice ; S> WG 220k',.99,(2,8,208,20))],pixels,0,0)[0]
        self.assertEqual(row['kind'],'normal',row)
        self.assertFalse(row.get('glyph_color_confirmed',False))


if __name__=='__main__': unittest.main()
