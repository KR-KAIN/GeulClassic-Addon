"""Regression tests for the real 2026-10-25 EXP. label and window behavior."""
import unittest
from pathlib import Path
import cv2
import numpy as np
from kain_maple_translator.hunt_stats import HuntSession, parse_exp_text
from kain_maple_translator.hunt_capture import read_hud_info, find_exp_label_roi,locate_keyboard

ROOT=Path(__file__).resolve().parents[1]

class FakeResult:
    def __init__(self,text):
        self.txts=[text];self.scores=[.96]

class FakeHUD:
    def __init__(self): self.reads=0
    def recognize_lines(self,images):
        self.reads+=1
        return FakeResult('LV. 15' if self.reads<=1 else 'EXP. 5,598 [79.40%]')
    def detect(self,*args):return []

class FailHud:
    def recognize_lines(self,images):return FakeResult('noise')
    def detect(self,*args):return []

class Tests(unittest.TestCase):
    def test_real_game_exp_dot_not_dropped(self):
        for value in ('EXP. 5,598 [79.40%]', 'EXP.5,598[79.40%]',
                      'EXP: 5,598 [79.40%]', 'EXP 5,598 [79.40%]'):
            with self.subTest(value=value):
                self.assertEqual(parse_exp_text(value),(None,5598,79.4))

    def test_real_game_snapshot_roi_detected(self):
        im=cv2.imread(str(ROOT/'tests/fixtures/hunt-exp-hud.png'))
        if im is None:self.skipTest('HUD screenshot fixture not present')
        self.assertIsNotNone(find_exp_label_roi(im))
        # The EXP fixture deliberately includes only the EXP/HUD region.
        # Test the keyboard locator with its own genuine keyboard sample.
        keyboard=cv2.imread(str(ROOT/'resources/hunt/keyboard-reference.png'))
        self.assertIsNotNone(keyboard)
        self.assertIsNotNone(locate_keyboard(keyboard))
        # An EXP-only screenshot must NOT be misclassified as a keyboard.
        self.assertIsNone(locate_keyboard(im))

    def test_direct_label_recognition_no_detector_dependency(self):
        im=cv2.imread(str(ROOT/'tests/fixtures/hunt-exp-hud.png'))
        self.assertIsNotNone(im)
        lv,exp,pct,reason=read_hud_info(FakeHUD(),im)
        self.assertEqual((lv,exp,pct),(15,5598,79.4))
        self.assertIn('EXP 게이지',reason)

    def test_hud_failure_explains_why_not_zero(self):
        im=cv2.imread(str(ROOT/'tests/fixtures/hunt-exp-hud.png'))
        _,exp,_,reason=read_hud_info(FailHud(),im)
        self.assertIsNone(exp)
        self.assertIn('읽지 못함',reason)

    def test_gained_exp_after_successful_reading(self):
        session=HuntSession();session.start()
        session.observe_exp(15,5598,79.40)
        session.observe_exp(15,5688,79.45)
        self.assertEqual(session.gained_exp,90)
        session.finish()

    def test_pin_is_user_controlled_not_forced(self):
        src=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        self.assertIn("self.cfg.get('hunt_widget_always_on_top',False)",src)
        self.assertIn("Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint",src)
        self.assertIn("if self._pinned: flags |= Qt.WindowType.WindowStaysOnTopHint",src)
        self.assertIn("self.pin_btn.clicked.connect(self.toggle_pin)",src)

    def test_capture_fallback_and_diagnostics(self):
        src=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        self.assertNotIn("misses>=6",src)
        self.assertIn("next_wgc_retry",src)
        self.assertIn("'exp_diag':exp_diag",src)
        self.assertIn('read_hud_info(',src)

if __name__=='__main__':unittest.main()
