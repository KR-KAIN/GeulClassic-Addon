"""Regression for red megaphones skipped when ordinary OCR has hits."""
from __future__ import annotations
import unittest
from unittest.mock import patch
import numpy as np
import cv2
from kain_maple_translator.megaphone import detect_band, classify
from kain_maple_translator.vision import TextRecognizer, red_announcement_regions, red_background_difference


def banner(rgb):
    image=np.full((65,400,3),(28,28,28),dtype=np.uint8)
    image[17:36,:] = (rgb[2],rgb[1],rgb[0])
    cv2.putText(image,'KAIN : S> Red Hat 2m',(12,31),cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1)
    return image


class RedMegaphoneTests(unittest.TestCase):
    def test_bright_red_banner_is_not_pink_or_normal(self):
        image=banner((224,49,43))
        band=detect_band(image,(10,16,300,20))
        self.assertEqual(band.tone,'red')
        category=classify(band,'S> Red Hat 2m')
        self.assertEqual(category['kind'],'unknown')
        self.assertEqual(category['prefix'],'[확성]')

    def test_pink_megaphone_regression(self):
        pink=banner((227,160,184))
        self.assertEqual(detect_band(pink,(10,16,300,20)).tone,'pink')

    def test_red_text_on_dark_chat_triggers_targeted_ocr(self):
        img=np.full((58,400,3), 22, dtype=np.uint8)
        cv2.putText(img,'Sam : RED SHOUT SALE 2M',(10,30),cv2.FONT_HERSHEY_SIMPLEX,.65,(35,50,220),2)
        self.assertTrue(red_announcement_regions(img))

    def test_no_retries_on_ordinary_chat(self):
        img=np.full((58,400,3), 22, dtype=np.uint8)
        cv2.putText(img,'Sam : normal message',(10,30),cv2.FONT_HERSHEY_SIMPLEX,.65,(240,240,240),2)
        self.assertEqual(red_announcement_regions(img),[])

    def test_clean_text_outvotes_high_confidence_incomplete_fragment(self):
        from kain_maple_translator.vision import Line, _dedupe_ocr_boxes
        rows=[Line('KAIN',.97,(10,19,150,14)),
              Line('KAIN: S> Red Hat 2m',.79,(10,19,150,14))]
        self.assertEqual(_dedupe_ocr_boxes(rows)[0].text, 'KAIN: S> Red Hat 2m')

    def test_red_background_is_normalized(self):
        img=banner((224,49,43))
        enhanced=red_background_difference(img[17:36])
        self.assertEqual(enhanced.shape,img[17:36].shape)
        self.assertGreater(len(np.unique(enhanced[:,:,0])),1)

    def test_ocr_diagnostic_contains_red_candidate_status(self):
        from pathlib import Path
        code=(Path(__file__).resolve().parents[1]/'kain_maple_translator/worker.py').read_text('utf-8')
        self.assertIn("'red_candidates': red_candidates",code)
        gui=(Path(__file__).resolve().parents[1]/'kain_maple_translator/main.py').read_text('utf-8')
        self.assertIn('빨간 확성기 후보 영역',gui)

    def test_secondary_pass_even_if_normal_pass_succeeds(self):
        img=banner((224,49,43))
        inst=TextRecognizer.__new__(TextRecognizer)
        calls=[]
        def fake_detect(image,left,top,scale):
            calls.append((left,top,image.shape))
            from kain_maple_translator.vision import Line
            if len(calls)==1:
                return [Line('General: hi', .92, (5,0,150,12))]
            return [Line('KAIN : S> Red Hat 2m', .85, (5,19,160,14))]
        with patch.object(TextRecognizer,'_detect_once',autospec=False,side_effect=fake_detect):
            result=inst.detect(img,0,0)
        self.assertGreaterEqual(len(calls),2)
        self.assertTrue(any('Red Hat' in row.text for row in result))

if __name__=='__main__':unittest.main()
