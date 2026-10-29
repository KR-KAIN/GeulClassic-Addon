"""No global text mute, WGC capture integrity, and screenshot-derived HUD tests."""
import unittest
from pathlib import Path
import cv2
import numpy as np
from kain_maple_translator.core import ChatFrameTracker
from kain_maple_translator.sliding_dedupe import SlidingChatDeduper
from kain_maple_translator.hunt_stats import HuntSession
from kain_maple_translator.hunt_capture import (locate_keyboard,potion_crops,slot_occupied,
                                                find_exp_label_roi,icon_identity,locate_keyboard_near_hud)

ROOT=Path(__file__).resolve().parents[1]


def row(body='S> GFA 60% 3m',y=80,visual='a',kind='normal'):
    return dict(nickname='Maple',body=body,rect=(20,y,230,17),
                kind=kind,visual_key=visual)

class SlidingTests(unittest.TestCase):
    def test_repeated_same_visible_row_not_emitted(self):
        dedup=SlidingChatDeduper()
        a=row(y=130)
        self.assertEqual(dedup.filter([a],[a],1.0),[a])
        a2=row(y=130,visual='different-background')
        self.assertEqual(dedup.filter([a2],[a2],1.15),[])
    def test_old_row_scrolling_up_is_not_new_chat(self):
        dedup=SlidingChatDeduper()
        a=row(y=140);a2=row(y=117)
        self.assertEqual(dedup.filter([a],[a],1),[a])
        self.assertEqual(dedup.filter([a2],[a2],1.2),[])
    def test_true_duplicate_new_bottom_is_preserved(self):
        dedup=SlidingChatDeduper()
        a=row(y=105); b=row(y=150,visual='other-new-message')
        self.assertEqual(dedup.filter([a],[a],1.0),[a])
        self.assertEqual(dedup.filter([b],[a,b],1.1),[b])
        # A new repeated message may arrive after old text has scrolled away.
        c=row(y=165)
        self.assertEqual(dedup.filter([c],[c],1.3),[c])
    def test_different_names_same_body_are_not_duplicates(self):
        dedup=SlidingChatDeduper()
        a=row();b={**a,'nickname':'Other'}
        self.assertEqual(dedup.filter([a,b],[a,b],1.0),[a,b])
    def test_channel_changes_only_same_screen_location_suppressed(self):
        # Existing ChannelGuard independently protects classification bounces.
        from kain_maple_translator.channel_guard import ChannelGuard
        g=ChannelGuard(); a=row();b=row(kind='megaphone',y=83)
        self.assertTrue(g.accept(a,1.0))
        self.assertFalse(g.accept(b,1.1))
        self.assertTrue(g.accept(row(kind='megaphone',y=140),1.2))
    def test_animated_background_does_not_repost_identical_visible_repeats(self):
        t=ChatFrameTracker()
        visible=[row(y=100,visual='a'), row(y=120,visual='b')]
        self.assertEqual(len(t.new(visible)),2)
        animated=[row(y=100,visual='x'), row(y=120,visual='y')]
        self.assertEqual(t.new(animated),[])
        self.assertEqual(len(t.new(animated+[row(y=142,visual='z')])),1)
    def test_next_real_trade_with_same_text_after_many_seconds_survives(self):
        d=SlidingChatDeduper()
        a=row(y=140)
        self.assertEqual(d.filter([a],[a],1),[a])
        d.filter([],[],2)
        self.assertEqual(d.filter([a],[a],5),[a])

class HuntTests(unittest.TestCase):
    def test_keyboard_from_actual_game_video_stays_identifiable(self):
        frame=cv2.imread(str(ROOT/'tests/fixtures/hunt-keyboard-real.png'))
        self.assertIsNotNone(frame)
        rect=locate_keyboard(frame)
        self.assertIsNotNone(rect)
        crops=potion_crops(frame,rect,all_slots=True)
        for key in ('Ctrl','End','PgDn'):
            self.assertIn(key,crops)
            self.assertTrue(slot_occupied(crops[key]),key)
            self.assertTrue(icon_identity(crops[key]))
    def test_small_game_keyboard_detected_without_fullscreen(self):
        orig=cv2.imread(str(ROOT/'tests/fixtures/hunt-keyboard-real.png'))
        small=cv2.resize(orig,None,fx=.7,fy=.7)
        self.assertIsNotNone(locate_keyboard(small))
    def test_video_keyboard_does_not_look_like_exp(self):
        frame=cv2.imread(str(ROOT/'tests/fixtures/hunt-keyboard-real.png'))
        self.assertIsNone(find_exp_label_roi(frame))
    def test_single_ocr_drop_does_not_invent_exp_gains(self):
        s=HuntSession();s.start()
        s.observe_exp(15,5500,78.0)
        s.observe_exp(15,5400,None) # 1 OCR error/dropped digits
        s.observe_exp(15,5510,78.2)
        self.assertEqual(s.gained_exp,10)
    def test_big_exp_jump_percent_inconsistent_is_rejected(self):
        s=HuntSession();s.start()
        s.observe_exp(15,5500,78.0)
        s.observe_exp(15,55000,78.0)
        self.assertEqual(s.gained_exp,0)
        self.assertEqual(s.last_exp,5500)
        s.observe_exp(15,5520,78.3)
        self.assertEqual(s.gained_exp,20)
    def test_valid_exp_increment_counts_after_missed_samples(self):
        s=HuntSession();s.start()
        s.observe_exp(15,5500,78.0)
        s.observe_exp(15,5720,81.1)
        self.assertEqual(s.gained_exp,220)
    def test_two_consistent_lower_exp_observations_reanchor(self):
        s=HuntSession();s.start()
        s.observe_exp(15,5500,None)
        s.observe_exp(15,4900,None)
        self.assertEqual(s.last_exp,5500)
        s.observe_exp(15,4901,None)
        self.assertEqual(s.last_exp,4901)
        s.observe_exp(15,4950,None)
        self.assertEqual(s.gained_exp,49)
    def test_no_wgc_fallback_merely_because_exp_ocr_fails(self):
        src=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        self.assertNotIn('misses>=6',src)
        self.assertNotIn('WGC EXP 연속 미인식',src)
        self.assertIn('next_wgc_retry',src)
        self.assertIn('minimum_update_interval=100',src)
    def test_meso_display_updates_without_exp_packet(self):
        src=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        self.assertNotIn("if 'meso' in measurement:",src)
        self.assertIn("if 'found_keyboard' in measurement:",src)

if __name__=='__main__':unittest.main()
