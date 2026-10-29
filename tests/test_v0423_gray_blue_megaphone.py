"""Grey megaphone: muted slate background and blue lettering, no gold dependency."""
import unittest
import cv2
import numpy as np
from kain_maple_translator.megaphone import detect_band, classify, row_appearance
from kain_maple_translator.vision import (Line, TextRecognizer,
    gray_blue_announcement_regions, enhance_gray_blue_chat, _dedupe_ocr_boxes)


class GrayBlueMegaphoneTests(unittest.TestCase):
    def gray_banner(self, underline=False, text=True):
        # Real gray-megaphone reference has approx RGB(150,169,180)
        image=np.full((50,600,3),(180,169,150),dtype=np.uint8)
        if text:
            cv2.putText(image, 'GhostOfBlyat : ALL YOU LVL 20-29', (4,17),
                        cv2.FONT_HERSHEY_SIMPLEX, .54,(132,66,7),1,cv2.LINE_AA)
            cv2.putText(image, 'NOOBS, PLAY KPQ, NOT TAKE SPACE', (35,37),
                        cv2.FONT_HERSHEY_SIMPLEX, .46,(132,66,7),1,cv2.LINE_AA)
        if underline:
            image[48:,:,:]=(40,173,212)
        return image

    def test_gray_banner_without_gold_border_detected(self):
        image=self.gray_banner()
        band=detect_band(image,(4,2,300,19))
        self.assertEqual('gray',band.tone)
        self.assertEqual('#96a9b4',band.background)
        self.assertEqual('unknown',classify(band,'ALL YOU LVL 20-29')['kind'])
        self.assertEqual('[일확]',classify(band,'ALL YOU LVL 20-29')['prefix'])
        self.assertEqual('gray',row_appearance(image,(4,2,300,19),(0,0),'PLAY KPQ')['tone'])
        self.assertTrue(gray_blue_announcement_regions(image))

    def test_gold_border_is_irrelevant(self):
        gold=self.gray_banner(underline=True)
        no_gold=self.gray_banner(underline=False)
        self.assertEqual('gray',detect_band(gold,(4,2,300,19)).tone)
        self.assertEqual('gray',detect_band(no_gold,(4,2,300,19)).tone)
        self.assertTrue(gray_blue_announcement_regions(gold))
        self.assertTrue(gray_blue_announcement_regions(no_gold))

    def test_background_alone_not_a_megaphone(self):
        img=self.gray_banner(text=False)
        self.assertEqual('none',detect_band(img,(3,2,300,19)).tone)
        self.assertEqual([],gray_blue_announcement_regions(img))
        img[48:,:,:]=(40,173,212)
        self.assertEqual([],gray_blue_announcement_regions(img))

    def test_blue_glyphs_on_dark_normal_chat_not_grey(self):
        image=np.full((50,600,3),30,dtype=np.uint8)
        cv2.putText(image,'GhostOfBlyat : chat', (4,24),
                    cv2.FONT_HERSHEY_SIMPLEX,.6,(132,66,7),1)
        self.assertEqual('none',detect_band(image,(4,2,300,19)).tone)
        self.assertEqual([],gray_blue_announcement_regions(image))

    def test_existing_pink_red_and_yellow_do_not_change(self):
        for rgb, expected in [((227,160,184),'pink'),((247,194,34),'yellow'),
                              ((217,60,46),'red'),((61,211,190),'cyan')]:
            bgr=np.full((50,600,3),tuple(reversed(rgb)),dtype=np.uint8)
            cv2.putText(bgr,'abc : message', (2,17),cv2.FONT_HERSHEY_SIMPLEX,.6,(2,2,2),1)
            self.assertEqual(expected,detect_band(bgr,(2,3,300,19)).tone)
            self.assertEqual([],gray_blue_announcement_regions(bgr))

    def test_localized_gray_blue_retry_even_if_main_ocr_finds_other_chat(self):
        base=self.gray_banner()
        rgb=enhance_gray_blue_chat(base)
        self.assertEqual(base.shape,rgb.shape)
        self.assertGreater(int(np.median(rgb[5:12,300:550])),220)
        self.assertLess(int(np.min(rgb[6:20,5:300])),60)

        reader=TextRecognizer.__new__(TextRecognizer)
        calls=[]
        def detect_once(image,left,top,scale):
            calls.append((image.copy(),left,top,scale))
            if len(calls)==1:
                return [Line('Samurai : ordinary message', .93, (10,500,220,18))]
            return [Line('GhostOfBlyat : ALL YOU LVL 20-29 NOOBS PLAY KPQ',
                         .87,(left+5,top+5,440,20))]
        reader._detect_once=detect_once
        output=reader.detect(base,110,220,1.8)
        self.assertGreaterEqual(len(calls),2)
        self.assertTrue(any('GhostOfBlyat' in item.text for item in output))
        self.assertEqual(110,calls[0][1])
        self.assertEqual(220,calls[0][2])

    def test_no_unbounded_retries_on_normal_chat(self):
        base=np.full((55,600,3),(30,30,30),dtype=np.uint8)
        reader=TextRecognizer.__new__(TextRecognizer)
        calls=[]
        def once(*args):
            calls.append(1)
            return [Line('Normal : hi',.95,(10,15,140,20))]
        reader._detect_once=once
        reader.detect(base,0,0,1.8)
        self.assertEqual(1,len(calls))


if __name__ == '__main__':
    unittest.main()
