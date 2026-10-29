"""Regression crops taken only from the user's 17-40-36 video.

The blue/grey posts are real pixels, including the scenery and rail that
previously made entire visible lines disappear before recognition.
The 50/60-second source crops document remaining omissions as well; their
presence in this fixture set is not a claim of complete per-frame recall.
"""
from pathlib import Path
import json
import unittest

import cv2
import numpy as np

from kain_maple_translator.row_admission import classified_chat_rows
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.frame_context import inspect_scrollbar, without_scrollbar
from kain_maple_translator.vision import TextRecognizer,Line
from kain_maple_translator.ocr_recall import merge_recovery_lines


FIXTURES=Path(__file__).parent/'fixtures/r14'


def source(second):
    return cv2.imread(str(FIXTURES/f'video-174036-{second}s.png'))


class RecordedScrollbarTests(unittest.TestCase):
    def test_slate_banners_do_not_hide_the_recorded_rail(self):
        for second in (6,32,50,60):
            with self.subTest(second=second):
                frame=source(second)
                context=inspect_scrollbar(frame)
                self.assertIs(context.at_bottom,True)
                self.assertGreaterEqual(context.gutter[0],600)
                clean=without_scrollbar(frame,context)
                np.testing.assert_array_equal(clean[:,:595],frame[:,:595])

    def test_actual_chat_without_rail_does_not_invent_a_gutter(self):
        # An ablation of the same video crop, not a generated chat sample.
        for second in (6,32,50):
            with self.subTest(second=second):
                self.assertIsNone(inspect_scrollbar(source(second)[:,:595]).gutter)

    def test_contained_prefix_is_an_alternative_read_not_a_second_sender(self):
        recorded=json.loads((FIXTURES/'overlap-57.json').read_text(encoding='utf-8'))
        lines=[Line(**item) for item in recorded['raw']]
        repaired=merge_recovery_lines([],lines)
        self.assertFalse(any(r.text=='Comupy  :B' for r in repaired))
        self.assertTrue(any(r.text=='Corrupy c: B> 2H sword attack 60% Ch 33 FM 19 PMO'
                            for r in repaired))
        # The actual separate HolyRatty row and DarkMen wrapped tail remain.
        self.assertEqual(len(repaired),len(lines)-1)
        self.assertTrue(any(r.text.startswith('HolyRattyc') for r in repaired))
        self.assertTrue(any(r.text.startswith('@@@@@Q') for r in repaired))


class RecordedRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer=TextRecognizer()

    def read(self,second):
        frame=source(second)
        frame=without_scrollbar(frame,inspect_scrollbar(frame))
        lines=IncrementalChatOCR(self.recognizer).detect(frame,0,0)
        return classified_chat_rows(lines,frame,0,0)

    def test_two_independent_gray_rows_survive_the_slate_rail_collision(self):
        rows=self.read(32)
        self.assertTrue(any(r['nickname']=='ONEGOAL' and
                            'top/chest/bottoms pm me!' in r['body'] for r in rows))
        self.assertTrue(any(r['nickname']=='Yakise' and
                            r['body']=='S>Pet Speed 60% (1)' for r in rows))

