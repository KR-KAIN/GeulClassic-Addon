"""R7: loss-aware output noise guard and timestamp-based stale-frame limit."""
import time
import unittest
from unittest.mock import patch

import numpy as np

from kain_maple_translator.capture_stream import CapturedChat, ChatCaptureStream
from kain_maple_translator.row_admission import dedupe_exact_overlaps, is_at_only_noise
from kain_maple_translator.visual_message_ledger import FrameMessageLedger


class R7NoiseTests(unittest.TestCase):
    def test_bare_at_only_is_noise_but_message_with_at_is_not(self):
        for text in ('@', '@@@@', ' ＠＠  ', '@ \t @'):
            self.assertTrue(is_at_only_noise(text), text)
        for text in ('Nick@home', 'hello @player', '[@scroll]', 'selling @ 5m', 'a', ''):
            self.assertFalse(is_at_only_noise(text), text)

    def msg(self, text, y, x=20):
        return {'nickname':'Seller','body':text,'kind':'megaphone', 'rect':(x,y,170,18)}

    def test_overlapping_same_text_is_one_detection(self):
        a=self.msg('S> claw 5m',40)
        repeated=self.msg('S> claw 5m',41)
        self.assertEqual(len(dedupe_exact_overlaps([a,repeated])),1)

    def test_legitimate_repeated_message_at_other_y_remains(self):
        a=self.msg('S> claw 5m',40)
        b=self.msg('S> claw 5m',68)
        self.assertEqual(dedupe_exact_overlaps([a,b]),[a,b])
        ledger=FrameMessageLedger()
        self.assertEqual(len(ledger.filter([a,b],[a,b],2.0)),2)

    def test_changing_price_and_channel_is_not_suppressed(self):
        a=self.msg('S> claw 5m',40)
        b=self.msg('S> claw 6m',40)
        c={**a, 'kind':'normal'}
        self.assertEqual(len(dedupe_exact_overlaps([a,b,c])),3)


class R7FrameExpiryTests(unittest.TestCase):
    def frame(self, code, seen):
        return CapturedChat(np.full((8,32,3),code,np.uint8),
                            {'left':0,'top':0,'width':32,'height':8},
                            seen,changed=True)

    def test_overdue_frame_is_skipped_in_realtime_mode(self):
        stream=ChatCaptureStream(lambda:{},lambda msg:None,max_age_s=.4)
        with patch('kain_maple_translator.capture_stream.time.monotonic',return_value=100.0):
            stream.publish(self.frame(1,99.0))
        with patch('kain_maple_translator.capture_stream.time.monotonic',return_value=100.6):
            self.assertIsNotNone(stream.get(timeout=0))
        self.assertEqual(stream.expired_drops,0)


    def test_last_available_frame_is_not_lost_to_age_filter(self):
        # If WGC stops publishing temporarily, an older sole snapshot must
        # still be available to OCR instead of making translation go silent.
        stream=ChatCaptureStream(lambda:{},lambda msg:None,max_age_s=.4)
        with patch('kain_maple_translator.capture_stream.time.monotonic',return_value=100.0):
            stream.publish(self.frame(1,99.0))
        with patch('kain_maple_translator.capture_stream.time.monotonic',return_value=100.6):
            got=stream.get(timeout=0)
        self.assertIsNotNone(got)
        self.assertEqual(int(got.image[0,0,0]),1)
        self.assertEqual(stream.expired_drops,0)

    def test_recent_queue_stamp_must_not_hide_old_capture(self):
        stream=ChatCaptureStream(lambda:{},lambda msg:None,max_age_s=.4)
        with patch('kain_maple_translator.capture_stream.time.monotonic',return_value=100.5):
            stream.publish(self.frame(9,99.0))
            self.assertIsNotNone(stream.get(timeout=0))
        self.assertEqual(stream.expired_drops,0)

    def test_stale_then_fresh_selects_fresh(self):
        stream=ChatCaptureStream(lambda:{},lambda msg:None,max_age_s=.4)
        with patch('kain_maple_translator.capture_stream.time.monotonic',side_effect=[100.0,100.4]):
            stream.publish(self.frame(1,99.0))
            stream.publish(self.frame(2,100.4))
        with patch('kain_maple_translator.capture_stream.time.monotonic',return_value=100.6):
            frame=stream.get(timeout=0)
        self.assertEqual(int(frame.image[0,0,0]),2)
        self.assertEqual(stream.expired_drops,1)

    def test_unmodified_historical_replay_when_limit_not_enabled(self):
        stream=ChatCaptureStream(lambda:{},lambda msg:None)
        stream.publish(self.frame(3,1.0))
        self.assertEqual(int(stream.get(timeout=0).image[0,0,0]),3)
        self.assertEqual(stream.expired_drops,0)

    def test_live_worker_preserves_changes_and_emits_drop_counters(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parents[1]/'kain_maple_translator/worker.py').read_text('utf-8')
        self.assertIn('ChatCaptureStream(self._settings, self.problem.emit, capacity=48, max_lag_s=LIVE_MAX_LAG_S)',source)
        self.assertNotIn('max_age_s=0.4',source)
        self.assertIn("'capture_expired_drops':stream.expired_drops",source)


if __name__=='__main__':
    unittest.main()
