import unittest
from pathlib import Path
import cv2

ROOT=Path(__file__).resolve().parents[1]

from kain_maple_translator.hunt_stats import parse_exp_text
from kain_maple_translator.hunt_capture import locate_keyboard_near_hud, potion_crops, slot_occupied, _fixed_1080p_keyboard_boxes

class Grounding1080pTests(unittest.TestCase):
    def test_parse_exp_text_accepts_dot_thousands(self):
        lv,exp,pct=parse_exp_text('LV. 16 EXP. 7.465 [84.45%]')
        self.assertEqual((lv,exp,round(pct,2)),(16,7465,84.45))

    def test_1080p_fixed_keyboard_fallback_finds_bottom_right_panel(self):
        path=ROOT/'tests/fixtures/hunt-1080p-user-screenshot.png'
        if not path.exists():
            self.skipTest('1080p user fixture not bundled')
        image=cv2.imread(str(path))
        box=locate_keyboard_near_hud(image)
        self.assertIsNotNone(box)
        crops=potion_crops(image,box)
        self.assertTrue(slot_occupied(crops['Ctrl']))
        self.assertTrue(slot_occupied(crops['PgDn']))
