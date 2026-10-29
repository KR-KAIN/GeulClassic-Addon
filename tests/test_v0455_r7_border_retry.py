"""R7 OCR ROI border rescue: no model changes and no false positive row."""
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.fast_vision import ink_rows_border_retry, InkRow
from kain_maple_translator.layout import dock_to_side


class BorderRetryTests(unittest.TestCase):
    @staticmethod
    def sample():
        # Synthetic semitransparent chat pane with a bright left bezel and
        # right scrollbar, simulating a slightly overwide game capture ROI.
        img=np.full((93,675,3),(196,168,147),dtype=np.uint8)
        for line,text in enumerate(('Seller: claw 10m','Merchant: glov att 60','Buyer: PM OFFER','Seller: 7k')):
            cv2.putText(img,text,(8,18+19*line),cv2.FONT_HERSHEY_SIMPLEX,.47,(58,20,12),1,cv2.LINE_AA)
        img[:,0:3]=(241,245,242)
        img[:,-28:]=(199,216,236)
        img[0:2,:]=(230,237,241)
        return img

    def test_empty_uniform_background_no_extra_rows(self):
        rows,uncertain,used=ink_rows_border_retry(np.full((82,670,3),127,np.uint8))
        self.assertEqual(rows,[])
        self.assertEqual(used,0)

    def test_normal_input_keeps_first_pass_exactly(self):
        frame=np.full((80,500,3),160,np.uint8)
        for y in (20,40,60):
            cv2.putText(frame,'Selling maple',(10,y),cv2.FONT_HERSHEY_SIMPLEX,.4,(15,15,15),1)
        rows,uncertain,used=ink_rows_border_retry(frame)
        self.assertEqual(used,0)

    def test_border_only_original_retries_and_restores_coordinates(self):
        frame=np.zeros((93,675,3),dtype=np.uint8)
        neutral=np.full((20,120,3),255,dtype=np.uint8)
        border=InkRow((0,85,675,8),frame[85:93].copy(),frame[85:93].copy(),b'border')
        line1=InkRow((10,12,120,20),neutral,neutral,b'one')
        line2=InkRow((11,32,115,20),neutral,neutral,b'two')
        def fake_segment(image,hint=None):
            return ([border],True) if image.shape[1]==675 else ([line1,line2],False)
        with patch('kain_maple_translator.fast_vision.ink_rows',side_effect=fake_segment):
            rows,uncertain,used=ink_rows_border_retry(frame)
        self.assertEqual(used,1)
        self.assertFalse(uncertain)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0].rect[0],13)  # original x + 3px trim

    def test_dock_snaps_flush_to_game_edge(self):
        box,status=dock_to_side((0,0,1457,822),(0,0,1856,822),396,140,'right',True,gap=0)
        self.assertEqual(status,'outside')
        self.assertEqual(box[0],1457)

if __name__=='__main__': unittest.main()
