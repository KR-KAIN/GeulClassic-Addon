import unittest
from pathlib import Path
import cv2
from kain_maple_translator.hunt_stats import HuntSession, parse_exp_text
from kain_maple_translator.hunt_capture import locate_keyboard, potion_crops, icon_identity, recognize_amount

class HuntSessionTests(unittest.TestCase):
    def test_timer_starts_only_on_start(self):
        now=[10.]
        s=HuntSession(clock=lambda:now[0]);now[0]=100.
        self.assertEqual(s.elapsed_label,'00:00:00')
        s.start();now[0]=163.
        self.assertEqual(s.elapsed_label,'00:01:03')
        s.finish();now[0]=999.
        self.assertEqual(s.elapsed_label,'00:01:03')
        s.start();self.assertEqual(s.elapsed_label,'00:00:00')
    def test_exp_gain_and_level_up_estimated(self):
        s=HuntSession();s.start()
        s.observe_exp(15,5000,50.)
        s.observe_exp(15,5300,53.)
        self.assertEqual(s.gained_exp,300)
        s.observe_exp(16,100,1.)
        self.assertTrue(s.exp_estimated)
        self.assertEqual(s.gained_exp,5100)
    def test_potions_and_icon_switch(self):
        s=HuntSession();s.start()
        s.observe_slot('Ctrl','red',99)
        s.observe_slot('Ctrl','red',99)
        s.observe_slot('Ctrl','red',95)
        self.assertEqual(s.slots['Ctrl'].spent,4)
        s.observe_slot('Ctrl','red',130)
        self.assertEqual(s.slots['Ctrl'].refills,35)
        s.observe_slot('Ctrl','blue',20)
        s.observe_slot('Ctrl','blue',20)
        self.assertEqual(s.retired_usage['red'],4)
        self.assertEqual(s.slots['Ctrl'].spent,0)
    def test_stats_only_while_running(self):
        s=HuntSession();s.observe_exp(15,5000,50)
        self.assertIsNone(s.last_exp)
        s.start();s.observe_exp(15,5000,50);s.finish()
        s.observe_exp(15,6000,60)
        self.assertEqual(s.gained_exp,0)
    def test_parse_hud(self):
        self.assertEqual(parse_exp_text('LV. 15 EXP:5,598[79.40%]'),(15,5598,79.4))
    def test_keyboard_reference(self):
        ref=cv2.imread(str(Path(__file__).resolve().parents[1]/'resources/hunt/keyboard-reference.png'))
        self.assertIsNotNone(ref)
        detected=locate_keyboard(ref)
        self.assertIsNotNone(detected)
        self.assertEqual(set(potion_crops(ref,detected)),{"Ctrl","Del","End","PgDn"})
    def test_amount_requires_only_digits(self):
        self.assertEqual(recognize_amount('99'),99)
        self.assertIsNone(recognize_amount('Ctrl 99 5'))
