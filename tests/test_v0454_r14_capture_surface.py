"""R14 capture regression using original 17:40 recording pixels only."""
from pathlib import Path
import itertools
import sys
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import unittest

from kain_maple_translator.capture_stream import ChatCaptureStream
from kain_maple_translator.fast_vision import ink_rows


FIXTURES = Path(__file__).parent / 'fixtures' / 'r14'


class CaptureSurfaceTests(unittest.TestCase):
    def test_identical_video_pixels_keep_uncertain_segmentation(self):
        image = cv2.imread(str(FIXTURES / 'capture-15.png'))
        rows, uncertain = ink_rows(image)
        assert len(rows) == 1 and uncertain
        cfg = {'capture_backend': 'mss', 'enabled': {'chat': True},
               'regions': {'chat': {'left': 330, 'top': 833, 'width': 621, 'height': 80}}}
        errors, consumed = [], []
        stream = ChatCaptureStream(lambda: cfg, errors.append)
        class Mss:
            calls = 0
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def grab(self, region):
                self.calls += 1
                if self.calls == 2:
                    consumed.append(stream.get(timeout=0))
                    stream.stop_event.set()
                return image.copy()
        ticks = itertools.count(100., .1)
        with (patch.dict(sys.modules, {'mss': SimpleNamespace(mss=Mss)}),
              patch('kain_maple_translator.capture_stream.time.monotonic', side_effect=lambda: next(ticks))):
            stream._run()
        assert errors == []
        first, second = consumed[0], stream.get(timeout=0)
        assert first is not None and second is not None
        # A repeated screenshot does not prove uncertain segmentation correct.
        # Both snapshots must remain ineligible for row-coverage compaction.
        assert first.row_signature == second.row_signature == ()
        assert stream.signature_uncertain_frames == 2

    def _check_wgc_interval(self, interval, milliseconds):
        image = cv2.imread(str(FIXTURES / 'capture-15.png'))
        region = {'left': 330, 'top': 833, 'width': 621, 'height': 80}
        cfg = {'capture_backend': 'wgc', 'enabled': {'chat': True},
               'capture_interval': interval, 'regions': {'chat': region}}
        errors, started = [], []
        stream = ChatCaptureStream(lambda: cfg, errors.append)
        class Source:
            def __init__(self, hwnd, client_rect, region):
                self.arrivals = 1; self.queue_overflows = 0; self.finished = False
                self.started_at = 100.; self.error = None
            def start(self): started.append(self.minimum_update_interval)
            def get(self, timeout):
                stream.stop_event.set()
                return image.copy(), region.copy(), 100.
            def close(self): pass
        class Mss:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def grab(self, region): raise AssertionError('WGC must not grab via MSS')
        game = SimpleNamespace(hwnd=314, rect=(0, 0, 1920, 1080))
        with (patch.dict(sys.modules, {'mss': SimpleNamespace(mss=Mss)}),
              patch('kain_maple_translator.game_window.find_maple_window', return_value=game),
              patch('kain_maple_translator.wgc_capture.WgcWindowSource', Source)):
            stream._run()
        assert errors == []
        assert started == [milliseconds]
        assert stream.capture_interval_ms == milliseconds
        assert stream.get(timeout=0).image.shape == image.shape

    def test_wgc_pacing_default_80ms(self):
        self._check_wgc_interval(.08, 80)

    def test_wgc_pacing_minimum_50ms(self):
        self._check_wgc_interval(.05, 50)

    def test_wgc_pacing_maximum_250ms(self):
        self._check_wgc_interval(.25, 250)


if __name__ == "__main__":
    unittest.main()
