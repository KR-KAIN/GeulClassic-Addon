import unittest
from pathlib import Path
import cv2
from kain_maple_translator.hunt_stats import HuntSession, parse_exp_text, parse_meso_text
from kain_maple_translator.hunt_capture import (locate_keyboard,potion_crops,
    slot_occupied,icon_identity,read_potion_amounts,find_exp_label_roi,read_hud)
from kain_maple_translator.layout import hud_panel_geometry

ROOT=Path(__file__).resolve().parents[1]

class MockResult:
    def __init__(self,values,scores):
        self.txts=values;self.scores=scores

class BulkOCR:
    def __init__(self):self.calls=0
    def recognize_lines(self,images):
        self.calls+=1
        return MockResult(['105']*len(images),[.99]*len(images))

class MockLine:
    def __init__(self,text):
        self.text=text;self.confidence=.95;self.rect=(0,0,125,23)
class MockDetect:
    def detect(self,arr,x,y,scale):
        return [MockLine('EXP:5,598[79.40%]')]

class HuntRegressionTests(unittest.TestCase):
    def test_live_exp_when_level_unreadable(self):
        s=HuntSession();s.start();s.observe_exp(None,100,2)
        s.observe_exp(None,125,2.5)
        self.assertEqual(s.gained_exp,25)
        s.observe_exp(15,150,3.0)
        self.assertEqual(s.gained_exp,25) # no artificial level-up
        s.observe_exp(15,170,3.4)
        self.assertEqual(s.gained_exp,45)

    def test_meso_is_observed_balance_change_only(self):
        s=HuntSession();s.start()
        s.observe_meso(None);self.assertIsNone(s.last_meso)
        s.observe_meso(500);s.observe_meso(630)
        self.assertEqual(s.meso_net,130)
        s.observe_meso(600);self.assertEqual(s.meso_net,100)
        s.finish();s.observe_meso(700);self.assertEqual(s.meso_net,100)
        self.assertEqual(parse_meso_text('Mesos: 12,345,678'),12345678)
        self.assertIsNone(parse_meso_text('earned 234 meso exp 100'))

    def test_potion_identity_change_not_blocked_by_stack_reduction(self):
        s=HuntSession();s.start()
        s.observe_slot('Ctrl','red',100);s.observe_slot('Ctrl','red',99)
        self.assertEqual(s.slots['Ctrl'].last_count,99)
        s.observe_slot('Ctrl','red',96)
        self.assertEqual(s.slots['Ctrl'].spent,3)
        s.observe_slot('Ctrl','blue',30);s.observe_slot('Ctrl','blue',29)
        self.assertEqual(s.retired_usage.get('red'),3)
        self.assertEqual(s.slots['Ctrl'].last_count,29)

    def test_fast_batch_potion_ocr(self):
        sample=cv2.imread(str(ROOT/'resources/hunt/keyboard-reference.png'))
        crops=potion_crops(sample,locate_keyboard(sample))
        mock=BulkOCR()
        # Exercise OCR batching independently of the new raster fast path.
        # The real count is now validated by test_v0454, not by a mock that
        # claims the keyboard reference says 105.
        from unittest.mock import patch
        with patch('kain_maple_translator.stack_digits.match_stack_digits',return_value=None):
            readings=read_potion_amounts(mock,crops)
        self.assertEqual(mock.calls,1)
        self.assertEqual(readings['Ctrl'],105)

    def test_keyboard_auto_icon_reference(self):
        sample=cv2.imread(str(ROOT/'resources/hunt/keyboard-reference.png'))
        rect=locate_keyboard(sample)
        self.assertIsNotNone(rect)
        samples=potion_crops(sample,rect,all_slots=True)
        self.assertEqual(len(samples),12)
        self.assertTrue(slot_occupied(samples['Ctrl']))
        self.assertTrue(slot_occupied(samples['End']))
        self.assertTrue(slot_occupied(samples['PgDn']))
        self.assertFalse(slot_occupied(samples['1']))
        self.assertNotEqual(icon_identity(samples['Ctrl']),icon_identity(samples['PgDn']))

    def test_hud_exp_roi_on_game_screenshot_fixture(self):
        # Prefer cropped user-supplied HUD only to avoid packaging a screen.
        path=ROOT/'tests/fixtures/hunt-exp-hud.png'
        if not path.exists():self.skipTest('No screenshot fixture')
        image=cv2.imread(str(path))
        self.assertIsNotNone(find_exp_label_roi(image))
        level,exp,pct=read_hud(MockDetect(),image)
        self.assertEqual(exp,5598)
        self.assertEqual(pct,79.4)

    def test_all_windowed_resolutions_hud_seam(self):
        for w,h in [(800,600),(1024,768),(1280,720),(1366,768),
                    (1920,1080),(1920,1200),(2560,1440)]:
            with self.subTest(size=(w,h)):
                left,right=hud_panel_geometry((0,0,w,h),(0,0,w,h))
                self.assertEqual(left[0],0)
                self.assertEqual(right[0]+right[2],w)
                self.assertEqual(left[1],right[1])
                self.assertEqual(left[3],right[3])
                self.assertGreater(left[2],150)
                self.assertGreater(right[2],150)

    def test_widget_compact_contract_and_no_fake_meso(self):
        src=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        self.assertIn('NATIVE_W=248;NATIVE_H=122',src)  # R15: compact classic stat-window skin
        self.assertNotIn("if 'meso' in measurement:",src)
        self.assertNotIn("self.session.observe_meso(measurement.get('meso'))",src)
        self.assertIn('read_potion_amounts(', (ROOT/'kain_maple_translator/hunt_aux.py').read_text('utf-8'))
        self.assertIn('minimum_update_interval=100',src)
        self.assertIn('potion_crops(', (ROOT/'kain_maple_translator/hunt_aux.py').read_text('utf-8'))

if __name__=='__main__':unittest.main()
