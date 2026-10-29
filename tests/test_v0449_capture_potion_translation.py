"""v0.4.49 regression: expedited EXP, decoupled quickslots, and chat scroll."""
import unittest
from pathlib import Path
import cv2
import numpy as np
from kain_maple_translator.hunt_capture import (ExpChangeGate,icon_snapshot,potion_crops,
                                                 icon_identity,slot_occupied,locate_keyboard)
from kain_maple_translator.hunt_aux import keyboard_from_relative
from kain_maple_translator.hunt_stats import HuntSession
from kain_maple_translator.core import ChatFrameTracker
from kain_maple_translator.sliding_dedupe import SlidingChatDeduper

ROOT=Path(__file__).resolve().parents[1]


def row(text,y,visual=None):
    visual=text if visual is None else visual
    return {'nickname':'User','body':text,'rect':(4,y,190,16),'kind':'normal','visual_key':visual}


class ExpTests(unittest.TestCase):
    def setUp(self):
        self.frame=np.full((600,800,3),25,np.uint8)
    def test_exp_changed_pixel_triggers_next_read(self):
        g=ExpChangeGate(.2,1.1,.35)
        self.assertTrue(g.should_read(self.frame,0))
        g.result(True,0)
        self.assertFalse(g.should_read(self.frame,.25))
        self.frame[560:575,420:435]=255
        self.assertTrue(g.should_read(self.frame,.35))
    def test_exp_heartbeat_when_still(self):
        g=ExpChangeGate(.2,1.1,.35)
        self.assertTrue(g.should_read(self.frame,0));g.result(True,0)
        self.assertFalse(g.should_read(self.frame,.5))
        self.assertTrue(g.should_read(self.frame,1.2))
    def test_failed_ocr_waits_before_retry_even_if_static(self):
        g=ExpChangeGate(.2,1.1,.35)
        self.assertTrue(g.should_read(self.frame,0));g.result(False,0)
        self.assertFalse(g.should_read(self.frame,.23))
        self.assertTrue(g.should_read(self.frame,.36))
    def test_reinitialization_on_new_game_size(self):
        g=ExpChangeGate()
        self.assertTrue(g.should_read(self.frame,0));g.result(True,0)
        self.assertFalse(g.should_read(self.frame,.3))
        g.reset()
        self.assertTrue(g.should_read(self.frame,.4))
    def test_bad_ocr_does_not_destroy_existing_exp_baseline(self):
        s=HuntSession();s.start()
        s.observe_exp(15,4316,61.22)
        s.observe_exp(15,None,None)
        s.observe_exp(15,4582,64.99)
        self.assertEqual(s.gained_exp,266)


class PotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame=cv2.imread(str(ROOT/'tests/fixtures/hunt-keyboard-real.png'))
        assert cls.frame is not None
    def test_keyboard_roi_calibration_rejects_bad_box(self):
        self.assertIsNone(keyboard_from_relative(self.frame,[.2,.2,.02,.03]))
        self.assertIsNone(keyboard_from_relative(self.frame,[-.1,0,.6,.6]))
        self.assertIsNone(keyboard_from_relative(self.frame,[.7,.7,.5,.5]))
    def test_manual_calibration_accepts_full_panel(self):
        got=keyboard_from_relative(self.frame,[0,0,1,1])
        # Panel is roughly 171:126 and must pass the aspect ratio check.
        self.assertEqual(got,(0,0,171,126))
    def test_actual_icon_snapshot_and_keys(self):
        box=locate_keyboard(self.frame)
        self.assertIsNotNone(box)
        crops=potion_crops(self.frame,box,all_slots=True)
        for name in ('Ctrl','End','PgDn'):
            self.assertTrue(slot_occupied(crops[name]))
            small=icon_snapshot(crops[name])
            self.assertGreater(small.size,80)
            self.assertLess(small.shape[0],crops[name].shape[0])
            self.assertTrue(icon_identity(crops[name]))
    def test_consumption_and_refill_are_separate(self):
        s=HuntSession();s.start()
        s.observe_slot('Ctrl','blue',100)
        s.observe_slot('Ctrl','blue',100)
        s.observe_slot('Ctrl','blue',97)
        s.observe_slot('Ctrl','blue',150)
        self.assertEqual(s.slots['Ctrl'].spent,3)
        self.assertEqual(s.slots['Ctrl'].refills,53)
    def test_aux_exp_job_not_blocked_by_meso_ocr_in_source(self):
        widget=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        auxiliary=(ROOT/'kain_maple_translator/hunt_aux.py').read_text('utf-8')
        self.assertIn('HuntAuxAnalyzer(',widget)
        self.assertIn('self._aux.publish(image,active)',widget)
        self.assertNotIn('read_meso(recognizer,image)',widget)
        self.assertNotIn('read_meso(recognizer,frame)',auxiliary)
    def test_exp_tracker_has_requested_new_name(self):
        widget=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        self.assertIn("setWindowTitle('글클메 경험치 측정기')",widget)
        self.assertIn("QLabel('EXP METER  ·  경험치 측정기')",widget)  # R15 classic title strip
        self.assertIn("QPushButton('영역 지정')",widget)
        self.assertIn("QPushButton('재인식')",widget)


class ChatTests(unittest.TestCase):
    def test_one_scrolled_message_not_retranslated(self):
        t=ChatFrameTracker();d=SlidingChatDeduper()
        a=[row('A',40),row('B',60),row('C',80)]
        self.assertEqual(len(d.filter(t.new(a),a,1)),3)
        b=[row('B',40),row('C',60),row('D',80)]
        self.assertEqual([r['body'] for r in d.filter(t.new(b),b,1.3)],['D'])
    def test_multi_message_burst_just_new_suffix(self):
        t=ChatFrameTracker();d=SlidingChatDeduper()
        a=[row('A',20),row('B',40),row('C',60),row('D',80)]
        d.filter(t.new(a),a,1)
        b=[row('C',20),row('D',40),row('E',60),row('F',80)]
        self.assertEqual([r['body'] for r in d.filter(t.new(b),b,1.2)],['E','F'])
    def test_identical_text_new_occurrence_preserved(self):
        t=ChatFrameTracker();d=SlidingChatDeduper()
        a=[row('A',20),row('haha',40)]
        d.filter(t.new(a),a,1)
        b=[row('haha',20),row('haha',40)]
        out=d.filter(t.new(b),b,1.15)
        self.assertEqual([r['body'] for r in out],['haha'])
    def test_empty_ocr_frame_does_not_erase_visual_history(self):
        d=SlidingChatDeduper()
        a=row('A',100)
        self.assertEqual(d.filter([a],[a],1),[a])
        self.assertEqual(d.filter([],[],1.4),[])
        self.assertEqual(d.filter([row('A',100)],[row('A',100)],2.0),[])

if __name__=='__main__':unittest.main()

class DigitGateTests(unittest.TestCase):
    def test_cached_count_only_for_same_pixels_and_icon(self):
        from kain_maple_translator.hunt_aux import SlotCountGate
        g=SlotCountGate(refresh_after=3.0)
        slot=np.full((42,42,3),150,np.uint8)
        self.assertIsNone(g.reuse('Ctrl','a',slot,0.0))
        g.record('Ctrl','a',slot,92,0.0)
        self.assertEqual(g.reuse('Ctrl','a',slot,1.0),92)
        changed=slot.copy()
        changed[-5:,4:14]=255
        self.assertIsNone(g.reuse('Ctrl','a',changed,1.0))
        self.assertIsNone(g.reuse('Ctrl','b',slot,1.0))
        self.assertIsNone(g.reuse('Ctrl','a',slot,3.1))
    def test_unknown_count_is_retried(self):
        from kain_maple_translator.hunt_aux import SlotCountGate
        g=SlotCountGate();slot=np.zeros((42,42,3),np.uint8)
        g.record('Ctrl','blue',slot,None,0)
        self.assertIsNone(g.reuse('Ctrl','blue',slot,.1))
