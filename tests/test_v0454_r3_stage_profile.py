"""Stage timing is factual and must not contaminate actual OCR/chat behavior."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from unittest.mock import patch
from kain_maple_translator.fast_vision import IncrementalChatOCR, InkRow
from kain_maple_translator.capture_stream import ChatCaptureStream, CapturedChat
from kain_maple_translator.stage_trace import StageTraceWriter


class FakeRecognizer:
    def __init__(self):
        self.calls=0
        self.ocr=self
    def recognize_txt(self, images):
        self.calls+=1
        return SimpleNamespace(txts=['Nick: hello there']*len(images),scores=[.99]*len(images))
    def detect(self,*args):
        return []

class FixedStepClock:
    """Deterministic clock for checking accounting, NOT a performance benchmark."""
    def __init__(self, initial=1000., step=.0001):
        self.value=float(initial)
        self.step=float(step)
    def __call__(self):
        self.value+=self.step
        return self.value


class StageProfileTests(unittest.TestCase):
    def test_stage_total_is_partitioned_and_input_sizes_recorded(self):
        frame=np.full((90,540,3),28,np.uint8)
        cv2.putText(frame,'Nick: hello there',(6,45),cv2.FONT_HERSHEY_SIMPLEX,.62,(245,245,245),1,cv2.LINE_AA)
        # Exercise a known *new row* rather than relying on OpenCV's
        # platform-dependent row segmentation of a synthetic font rendering.
        # On Windows, the original fixture can yield zero ink rows; a mocked
        # detector then completes in <0.005 ms and rounds stage_ocr_ms to 0.
        # That is a legitimate zero-REC frame, not an OCR timing failure.
        row=InkRow((6,18,275,48),frame[18:66,6:281].copy(),
                   frame[18:66,6:281].copy(),b'profiling-known-new-row')
        with (patch('kain_maple_translator.fast_vision.ink_rows',return_value=([row],False)),
              patch('kain_maple_translator.badge_split.BadgeSplitter.split',return_value=None),
              patch('kain_maple_translator.badge_split.BadgeSplitter.split_plain',return_value=None)):
            # The production clock may report a very short phase as 0.00ms
            # after two-decimal rounding. Use deterministic ticks to verify
            # partition arithmetic independent of the host timer resolution.
            recognizer=FakeRecognizer()
            engine=IncrementalChatOCR(recognizer,clock=FixedStepClock())
            engine.detect(frame,0,0)
        stats=engine.stats
        self.assertGreater(recognizer.calls,0,'Fixture must actually exercise OCR recognition')
        self.assertGreater(stats['recognition_inputs'],0)
        self.assertEqual((stats['input_width_px'],stats['input_height_px']), (540,90))
        self.assertEqual(stats['input_bytes'],frame.nbytes)
        self.assertGreater(stats['stage_pre_ms'],0)
        self.assertGreater(stats['stage_ocr_ms'],0)
        self.assertGreater(stats['rec_input_max_width_px'],0)
        self.assertEqual(stats['rec_input_max_height_px'],48)
        self.assertAlmostEqual(stats['stage_total_ms'],sum(stats[k] for k in ('stage_pre_ms','stage_ocr_ms','stage_post_ms')),delta=.04)
        self.assertGreaterEqual(stats['ocr_active_samples'],1)

    def test_zero_duration_phases_are_valid_when_clock_resolution_is_coarse(self):
        """A clock with coarse ticks must not fabricate elapsed time to pass QA."""
        frame=np.full((90,540,3),28,np.uint8)
        cv2.putText(frame,'Nick: hello there',(6,45),cv2.FONT_HERSHEY_SIMPLEX,
                    .62,(245,245,245),1,cv2.LINE_AA)
        row=InkRow((6,18,275,48),frame[18:66,6:281].copy(),
                   frame[18:66,6:281].copy(),b'coarse-clock-rec-row')
        with (patch('kain_maple_translator.fast_vision.ink_rows',return_value=([row],False)),
              patch('kain_maple_translator.badge_split.BadgeSplitter.split',return_value=None),
              patch('kain_maple_translator.badge_split.BadgeSplitter.split_plain',return_value=None)):
            recognizer=FakeRecognizer()
            engine=IncrementalChatOCR(recognizer,clock=lambda:1000.)
            engine.detect(frame,0,0)
        stats=engine.stats
        self.assertGreater(recognizer.calls,0)
        self.assertEqual(stats['recognition_inputs'],1)
        self.assertEqual(stats['stage_pre_ms'],0.)
        self.assertEqual(stats['stage_ocr_ms'],0.)
        self.assertEqual(stats['stage_total_ms'],0.)
        self.assertEqual(stats['stage_post_ms'],0.)

    def test_capture_enqueue_timestamp_is_independent_of_capture_start(self):
        stream=ChatCaptureStream(lambda:{},lambda _:None,capacity=4)
        frame=CapturedChat(np.zeros((20,30,3),np.uint8),{'left':0,'top':0,'width':30,'height':20},time.monotonic()-10)
        self.assertTrue(stream.publish(frame))
        got=stream.get(timeout=.01)
        self.assertGreater(got.queued_at,got.captured_at+9)
        self.assertLess(time.monotonic()-got.queued_at,1)

    def test_trace_is_metadata_only_and_flushes_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.jsonl'
            writer=StageTraceWriter(path)
            writer.record({'cap_ms':8.2,'pre_ms':10.5,'queue_wait_ms':3.4,
                           'input_width_px':700,'input_height_px':230})
            writer.close()
            rows=[json.loads(line) for line in path.read_text('utf-8').splitlines()]
            self.assertEqual(rows[0]['queue_wait_ms'],3.4)
            self.assertEqual(len(rows),1)
