"""R5 opt-in bitmap-crop capture never changes OCR data or saves when OFF."""
from dataclasses import dataclass
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from kain_maple_translator.glyph_features import GlyphDebugRecorder, separate_glyphs


@dataclass
class StubRow:
    original: np.ndarray
    neutral: np.ndarray


def example():
    im=np.full((20,40,3),255,np.uint8)
    im[6:15,6:11]=0
    im[6:15,17:23]=0
    return StubRow(im.copy(),im.copy())



class GlyphDebugUnittest(unittest.TestCase):
    """Run the R5 debug regressions in Windows unittest builds."""

    def setUp(self):
        sandbox = tempfile.TemporaryDirectory(prefix="gca-r5-test-")
        self.addCleanup(sandbox.cleanup)
        self.tmp_path = Path(sandbox.name)

    def test_off_does_not_create_or_write_files(self):
        recorder=GlyphDebugRecorder(enabled=False,folder=self.tmp_path/'private')
        recorder.capture(example(),'normal')
        recorder.observe(example().neutral,'AB')
        assert recorder.taken==0
        assert not (self.tmp_path/'private').exists()


    def test_raw_png_and_rectangle_preview_without_compression(self):
        recorder=GlyphDebugRecorder(enabled=True,folder=self.tmp_path/'private')
        row=example()
        recorder.capture(row,'normal')
        raw=self.tmp_path/'private/line-01-normal-original.png'
        preview=self.tmp_path/'private/line-01-normal-columns.png'
        assert raw.is_file() and preview.is_file()
        assert np.array_equal(cv2.imread(str(raw)),row.original)
        assert not np.array_equal(cv2.imread(str(preview)),row.original)
        assert len(separate_glyphs(row.neutral))==2


    def test_capture_limit_and_category_quotas(self):
        recorder=GlyphDebugRecorder(enabled=True,folder=self.tmp_path/'private')
        row=example()
        for category in ('normal','yellow','gray','pink','other'):
            for _ in range(30):recorder.capture(row,category)
        assert recorder.taken==40
        assert len(list((self.tmp_path/'private').glob('*.png')))==80
        assert all(v<=10 for v in recorder.categories.values())


    def test_glyph_split_stats(self):
        recorder=GlyphDebugRecorder(enabled=True,folder=self.tmp_path)
        row=example()
        recorder.observe(row.neutral,'AB')
        recorder.observe(row.neutral,'A')
        assert recorder.stats()['glyph_debug_split_match_ratio']==.5
