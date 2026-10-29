"""Actual source pixels from the user's 2026-10-27 16-30-42 recording.

No generated chat samples: verify the new source-first recognition path on
the four visible party posts and the two separate SilkArrow messages.
"""
import unittest
from pathlib import Path

import cv2

from kain_maple_translator.core import merge_chat_ocr
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.frame_context import inspect_scrollbar, without_scrollbar
from kain_maple_translator.vision import TextRecognizer


class RealVideoWhiteSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = TextRecognizer()

    def read(self, second):
        path = Path(__file__).parent / 'fixtures/r13' / f'white-chat-{second}.png'
        frame = cv2.imread(str(path))
        self.assertIsNotNone(frame)
        frame = without_scrollbar(frame, inspect_scrollbar(frame))
        engine = IncrementalChatOCR(self.recognizer)
        rows = merge_chat_ocr(engine.detect(frame, 0, 0))
        self.assertGreater(engine.stats.get('source_first_rows', 0), 0)
        return rows

    def test_video_24_four_physical_party_posts_remain_four(self):
        rows = self.read(24)
        party = [r for r in rows if r['body'].startswith('J>PQ RUSH')]
        self.assertEqual(len(party), 4)
        self.assertEqual(len({r['rect'][1] for r in party}), 4)

    def test_video_56_distinct_dialogue_sender_and_text(self):
        rows = self.read(56)
        observed = {(r['nickname'], r['body']) for r in rows}
        self.assertIn(('SilkArrow', 'naw ch3n'), observed)
        self.assertIn(('SilkArrow', 'u scammed me'), observed)

