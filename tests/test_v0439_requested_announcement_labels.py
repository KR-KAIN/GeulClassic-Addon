"""Requested color signatures: gray/일확, pink/고확, mint/하이퍼, yellow/아확."""
import unittest
import cv2
import numpy as np
from kain_maple_translator.megaphone import Band, classify, detect_band, row_appearance
from kain_maple_translator.vision import Line
from kain_maple_translator.row_admission import classified_chat_rows, _CLASSIFIED_CACHE


def swatch(rgb):
    background=tuple(reversed(rgb))
    img=np.full((40,560,3),background,dtype=np.uint8)
    cv2.putText(img,'Alice : S> [BWG] 5m',(8,25),cv2.FONT_HERSHEY_SIMPLEX,.56,(10,10,10),1,cv2.LINE_AA)
    return img


class RequestedAnnouncementLabels(unittest.TestCase):
    def setUp(self):
        _CLASSIFIED_CACHE.clear()

    def test_color_labels_ignore_item_presence(self):
        for tone,prefix in [('gray','[일확]'),('pink','[고확]'),
                            ('cyan','[하이퍼]'),('green','[하이퍼]'),
                            ('yellow','[아확]')]:
            for body in ('hi there','S> [BWG]','[Hat] [Glove]'):
                with self.subTest(tone=tone,body=body):
                    row=classify(Band(tone,'#dfafad',.95),body)
                    self.assertEqual(row['prefix'],prefix)
                    self.assertNotEqual(row['kind'],'normal')
                    self.assertEqual(row['band_color'],'#dfafad')

    def test_pink_mint_yellow_real_pixel_bands(self):
        for rgb,tone,prefix in [((227,160,184),'pink','[고확]'),
                                 ((61,211,190),'cyan','[하이퍼]'),
                                 ((247,194,34),'yellow','[아확]')]:
            with self.subTest(rgb=rgb):
                image=swatch(rgb)
                band=detect_band(image,(3,4,320,24))
                self.assertEqual(band.tone,tone)
                row=row_appearance(image,(3,4,320,24),(0,0),'S> [BWG]')
                self.assertEqual(row['prefix'],prefix)

    def test_no_banner_white_normal_chat_has_no_badge(self):
        image=np.full((40,560,3),25,dtype=np.uint8)
        cv2.putText(image,'Alice : S> BWG 5m',(8,25),cv2.FONT_HERSHEY_SIMPLEX,.56,(242,242,242),1,cv2.LINE_AA)
        row=classified_chat_rows([Line('Alice : S> BWG 5m',.99,(4,4,320,25))],image,0,0)[0]
        self.assertEqual(row['kind'],'normal',row)
        self.assertEqual(row['prefix'],'')

    def test_grey_blue_text_is_ilhwak(self):
        image=np.full((40,560,3),(180,169,150),dtype=np.uint8)
        cv2.putText(image,'Alice : sale',(4,25),cv2.FONT_HERSHEY_SIMPLEX,.56,(132,66,7),1,cv2.LINE_AA)
        band=detect_band(image,(4,4,310,24))
        self.assertEqual(band.tone,'gray')
        self.assertEqual(classify(band,'sale')['prefix'],'[일확]')

    def test_bannerless_verified_glyph_uses_same_color_label(self):
        image=np.full((34,650,3),25,dtype=np.uint8)
        cv2.putText(image,'Alice : S> WG 220k',(5,24),cv2.FONT_HERSHEY_SIMPLEX,.65,(200,100,240),1,cv2.LINE_AA)
        row=row_appearance(image,(2,8,250,20),(0,0),'S> WG 220k',{'body_start':80,'item_ranges':[]})
        self.assertEqual(row['tone'],'pink')
        self.assertEqual(row['prefix'],'[고확]')

if __name__=='__main__': unittest.main()
