"""R13: bounded live OCR lag and duplicate lines from real 1080p footage
(2026-10-27 12-59-43.mp4: 27 s median capture->OCR delay, 'buy bronze ore@@@'
shown 5 times as PoloYoloBen / 2oloYoloBen / oloYoloBen)."""
import unittest
from unittest.mock import patch
import numpy as np
from kain_maple_translator.capture_stream import CapturedChat, ChatCaptureStream
from kain_maple_translator.visual_message_ledger import same, strip_symbol_spam
from kain_maple_translator.worker import LIVE_MAX_LAG_S


def frame(code, seen):
    return CapturedChat(np.full((8, 32, 3), code, np.uint8),
                        {'left': 0, 'top': 0, 'width': 32, 'height': 8}, seen, changed=True)


class LiveLagTests(unittest.TestCase):
    def publish_all(self, stream, items, now):
        with patch('kain_maple_translator.capture_stream.time.monotonic', return_value=now):
            for code, seen in items:
                stream.publish(frame(code, seen))

    def test_backlog_skips_to_oldest_fresh_snapshot(self):
        stream = ChatCaptureStream(lambda: {}, lambda m: None, max_lag_s=2.5)
        self.publish_all(stream, [(1, 90.0), (2, 95.0), (3, 98.0), (4, 99.0)], 100.0)
        with patch('kain_maple_translator.capture_stream.time.monotonic', return_value=100.0):
            got = stream.get(timeout=0)
        # 3 is the oldest snapshot within 2.5 s: overlap with the next one kept.
        self.assertEqual(int(got.image[0, 0, 0]), 3)
        self.assertEqual(stream.lag_drops, 2)
        self.assertEqual(stream.frames.qsize(), 1)

    def test_sole_old_frame_is_still_read(self):
        stream = ChatCaptureStream(lambda: {}, lambda m: None, max_lag_s=2.5)
        self.publish_all(stream, [(7, 10.0)], 100.0)
        with patch('kain_maple_translator.capture_stream.time.monotonic', return_value=100.0):
            self.assertEqual(int(stream.get(timeout=0).image[0, 0, 0]), 7)
        self.assertEqual(stream.lag_drops, 0)

    def test_fresh_frames_keep_order(self):
        stream = ChatCaptureStream(lambda: {}, lambda m: None, max_lag_s=2.5)
        self.publish_all(stream, [(1, 99.0), (2, 99.5)], 100.0)
        with patch('kain_maple_translator.capture_stream.time.monotonic', return_value=100.0):
            self.assertEqual(int(stream.get(timeout=0).image[0, 0, 0]), 1)
            self.assertEqual(int(stream.get(timeout=0).image[0, 0, 0]), 2)

    def test_replay_without_limit_is_unchanged(self):
        stream = ChatCaptureStream(lambda: {}, lambda m: None)
        self.publish_all(stream, [(1, 1.0), (2, 2.0)], 100.0)
        self.assertEqual(int(stream.get(timeout=0).image[0, 0, 0]), 1)

    def test_live_limit_is_short(self):
        self.assertLessEqual(LIVE_MAX_LAG_S, 3.0)


class DuplicateLineTests(unittest.TestCase):
    def row(self, nick, body):
        return {'nickname': nick, 'body': body}

    def test_spam_suffix_keeps_word(self):
        self.assertEqual(strip_symbol_spam('buy bronze ore@@@@@@ @ @ @'), 'buy bronze ore @ @ @')
        self.assertEqual(strip_symbol_spam('S> 60% ATK @@@6@@'), 'S> 60% ATK')

    def test_spam_count_variants_are_same(self):
        self.assertTrue(same(self.row('PoloYoloBen', 'buy bronze ore@@@@@@'),
                             self.row('PoloYoloBen', 'buy bronze ore@@@@')))

    def test_first_glyph_of_nickname_misread(self):
        a = self.row('PoloYoloBen', 'buy bronze ore@@@@@@')
        self.assertTrue(same(a, self.row('2oloYoloBen', 'buy bronze ore@@@')))
        self.assertTrue(same(a, self.row('oloYoloBen', 'buy bronze ore@@@@@')))

    def test_different_messages_stay_different(self):
        self.assertFalse(same(self.row('PoloYoloBen', 'buy bronze ore'),
                              self.row('PoloYoloBen', 'buy silver ore')))
        self.assertFalse(same(self.row('Kain1', 'hello there all'),
                              self.row('Kain2', 'hello there all')))
        self.assertFalse(same(self.row('Ab', 'hello there'), self.row('Cb', 'hello there')))
        self.assertFalse(same(self.row('PoloYoloBen', 'S> ore 10k'),
                              self.row('2oloYoloBen', 'S> ore 20k')))


if __name__ == '__main__':
    unittest.main()
