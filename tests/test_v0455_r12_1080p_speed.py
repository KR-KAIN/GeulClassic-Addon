"""R12: 1080p scrollbar, edge-flicker reuse, text-change capture, merge safety.

Uses the user's own 1080p screenshot fixture plus synthetic glyphs only.
"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from kain_maple_translator.frame_context import inspect_scrollbar
from kain_maple_translator.fast_vision import (
    IncrementalChatOCR, InkRow, ink_signature, near_identical_ink)
from kain_maple_translator.capture_stream import ChangeDetector
from kain_maple_translator.ocr_recall import merge_recovery_lines
from kain_maple_translator.translation_queue import TranslationQueue
from kain_maple_translator.vision import Line

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def chat_1080p():
    """Automatic 1080p chat ROI (404,891,784x97) from the user's screenshot."""
    shot = cv2.imread(str(FIXTURES / 'hunt-1080p-user-screenshot.png'))
    return shot[891:988, 404:1188].copy()


def glyph_row(text, width=260, height=22, scale=.5, extra=None):
    neutral = np.full((height, width, 3), 255, np.uint8)
    cv2.putText(neutral, text, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 1, cv2.LINE_8)
    if extra is not None:
        extra(neutral)
    return neutral


class ScrollbarAt1080p(unittest.TestCase):
    def test_thumb_resting_on_down_button_is_bottom(self):
        # R11 reported 'browsing history' for every 1080p frame and skipped
        # all chat: the automatic ROI ends ~8px below the scrollbar.
        context = inspect_scrollbar(chat_1080p())
        self.assertIsNotNone(context.gutter)
        self.assertIs(context.at_bottom, True)

    def test_thumb_moved_up_is_still_browsing(self):
        image = chat_1080p()
        x0, _, w, _ = inspect_scrollbar(image).gutter
        strip = image[:, x0:x0+w].copy()
        rail = strip[30:31].copy()
        thumb = strip[41:72].copy()
        strip[41:72] = rail
        strip[41-6:72-6] = thumb
        image[:, x0:x0+w] = strip
        self.assertIs(inspect_scrollbar(image).at_bottom, False)

    def test_768p_fixture_unchanged(self):
        image = cv2.imread(str(FIXTURES / 'user-four-colour-rows.png'))
        self.assertIs(inspect_scrollbar(image).at_bottom, True)


class EdgeFlickerIdentity(unittest.TestCase):
    def flicker(self, neutral, points):
        out = neutral.copy()
        for y, x in points:
            out[y, x] = 255 - out[y, x]
        return out

    def edge_points(self, neutral, count):
        mask = neutral[:, :, 0] < 128
        edge = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~mask
        ys, xs = np.nonzero(edge)
        step = max(1, len(ys)//count)
        return list(zip(ys[::step][:count], xs[::step][:count]))

    def test_identical_and_scattered_edge_flicker_match(self):
        base = glyph_row('Alice : S> 150k ea')
        self.assertTrue(near_identical_ink(ink_signature(base), ink_signature(base.copy())))
        noisy = self.flicker(base, self.edge_points(base, 4))
        self.assertTrue(near_identical_ink(ink_signature(base), ink_signature(noisy)))

    def test_digit_change_never_matches(self):
        for a, b in (('S> 150k', 'S> 160k'), ('S> 150k', 'S> 15Ok'), ('B> 10m', 'B> 1Om'),
                     ('S> 3k', 'S> 8k'), ('lv 35', 'lv 36')):
            self.assertFalse(near_identical_ink(ink_signature(glyph_row(a)), ink_signature(glyph_row(b))), (a, b))

    @staticmethod
    def gap_column(neutral):
        """An empty column strictly inside the text (a word gap)."""
        mask = neutral[:, :, 0] < 128
        cols = np.flatnonzero(mask.any(axis=0))
        inside = [x for x in range(cols[0]+1, cols[-1]) if not mask[:, x-1:x+2].any()]
        return inside[len(inside)//2]

    def test_added_period_or_dot_never_matches(self):
        base = glyph_row('Alice : jpq ok')
        x = self.gap_column(base)
        def dot(img, size):
            img[13:13+size, x:x+size] = 0
        for size in (1, 2):
            dotted = glyph_row('Alice : jpq ok', extra=lambda img: dot(img, size))
            self.assertFalse(near_identical_ink(ink_signature(base), ink_signature(dotted)), size)

    def test_stroke_blob_larger_than_two_pixels_rejected(self):
        base = glyph_row('Alice : hello')
        mask = base[:, :, 0] < 128
        ys, xs = np.nonzero(mask)
        top, bottom = int(ys.min()), int(ys.max())
        for y, x in zip(ys, xs):
            if y+3 <= bottom and not mask[y+1:y+4, x-1:x+2].any():
                break
        def stroke(img):
            img[y+1:y+4, x] = 0  # 3px extension hanging from existing ink
        self.assertFalse(near_identical_ink(ink_signature(base), ink_signature(glyph_row('Alice : hello', extra=stroke))))

    def test_outer_column_flicker_still_matches(self):
        base = glyph_row('Alice : need help')
        mask = base[:, :, 0] < 128
        ys, xs = np.nonzero(mask)
        left = int(xs.min())
        y = int(ys[xs == left][0])
        grown = base.copy(); grown[y, left-1] = 0  # one pixel left of the box
        self.assertTrue(near_identical_ink(ink_signature(base), ink_signature(grown)))


class FlickerReuseInPipeline(unittest.TestCase):
    def make(self):
        self.now = 0.; self.calls = 0
        def recognize(images):
            self.calls += 1
            return SimpleNamespace(txts=['Alice: need help']*len(images), scores=[.97]*len(images), word_results=[])
        reader = SimpleNamespace(ocr=SimpleNamespace(recognize_txt=recognize), detect=lambda *a: [])
        engine = IncrementalChatOCR(reader, clock=lambda: self.now)
        engine.badges = SimpleNamespace(split=lambda *a: None, split_plain=lambda *a: None)
        return engine

    def row(self, neutral, key):
        return InkRow((0, 0, neutral.shape[1], neutral.shape[0]), neutral.copy(), neutral, key)

    def test_flickered_copy_reuses_read_and_changed_text_does_not(self):
        engine = self.make()
        base = glyph_row('Alice : need help')
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry', return_value=([self.row(base, b'a')], False, 0)):
            first = engine.detect(base, 0, 0)
        calls = self.calls
        noisy = EdgeFlickerIdentity().flicker(base, EdgeFlickerIdentity().edge_points(base, 3))
        self.now = .5
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry', return_value=([self.row(noisy, b'b')], False, 0)):
            second = engine.detect(noisy, 0, 0)
        self.assertEqual(self.calls, calls)
        self.assertEqual(engine.stats['near_cache_hits'], 1)
        self.assertEqual(second[0].text, first[0].text)
        self.assertEqual(second[0].ink_key, first[0].ink_key)  # same physical ink identity
        changed = glyph_row('Alice : need helq')
        self.now = 1.
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry', return_value=([self.row(changed, b'c')], False, 0)):
            engine.detect(changed, 0, 0)
        self.assertGreater(self.calls, calls)


class BrightFrameDetectorPolicy(unittest.TestCase):
    def make(self, text='Alice: B> scroll 100k', detected=()):
        self.now = 0.; self.detectors = 0
        def recognize(images):
            return SimpleNamespace(txts=[text]*len(images), scores=[.96]*len(images), word_results=[])
        def detect(*args):
            self.detectors += 1
            return list(detected)
        reader = SimpleNamespace(ocr=SimpleNamespace(recognize_txt=recognize), detect=detect)
        engine = IncrementalChatOCR(reader, clock=lambda: self.now)
        engine.badges = SimpleNamespace(split=lambda *a: None, split_plain=lambda *a: None)
        neutral = glyph_row('Alice : B> scroll 100k', width=300)
        row = InkRow((0, 0, 300, 22), neutral.copy(), neutral, b'bright', True)
        return engine, row

    def test_confident_bright_digits_do_not_force_detector(self):
        engine, row = self.make()
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry', return_value=([row], True, 1)):
            for step in range(5):
                self.now = step * .2
                engine.detect(row.original, 0, 0)
        self.assertLessEqual(self.detectors, 1)

    def test_unresolved_bright_frame_probes_at_most_once_per_interval(self):
        engine, row = self.make(text='Alice: S> 100k : pm')
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry', return_value=([row], True, 1)):
            for step in range(5):
                self.now = step * .2
                engine.detect(row.original, 0, 0)
            self.assertEqual(self.detectors, 1)
            self.now = 1.2
            engine.detect(row.original, 0, 0)
        self.assertEqual(self.detectors, 2)

    def test_probe_cannot_overwrite_confident_bright_row(self):
        wrong = Line('Alice: B> scroll 10k', .97, (0, 0, 300, 22))
        engine, row = self.make(detected=[wrong])
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry', return_value=([row], True, 1)):
            out = engine.detect(row.original, 0, 0)
        self.assertEqual([l.text for l in out], ['Alice: B> scroll 100k'])

    def test_edge_trim_rescue_keeps_detector_verification(self):
        engine, row = self.make()
        plain = InkRow(row.rect, row.original, row.neutral, b'plain')
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry', return_value=([plain], True, 1)):
            engine.detect(row.original, 0, 0)
        self.assertEqual(self.detectors, 1)


class DetectorMergeSafety(unittest.TestCase):
    def line(self, text, score=.95, y=0):
        return Line(text, score, (0, y, 400, 22))

    def test_detector_cannot_rename_confident_sender(self):
        good = self.line('HolyArrow : SELL GEPHART DAGGER LV40', .87)
        bad = self.line('HolVAFERS : SELLGEPHARTDAGGERLV4O', .9)
        self.assertEqual(merge_recovery_lines([good], [bad]), [good])

    def test_detector_still_repairs_digits_for_same_sender(self):
        primary = self.line('Alice: S> 10MESO', .97)
        detector = self.line('Alice: S> 100MESO', .9)
        self.assertEqual(merge_recovery_lines([primary], [detector]), [detector])

    def test_detector_still_repairs_weak_row(self):
        weak = self.line('Alce: S> 1OOk', .7)
        detector = self.line('Alice: S> 100k', .9)
        self.assertEqual(merge_recovery_lines([weak], [detector]), [detector])


class ChangeDetectorTests(unittest.TestCase):
    def frame(self, lines, shift):
        """Outlined white chat over a scrolling brick map (like R9's sample)."""
        h, w = 80, 420
        yy, xx = np.mgrid[0:h, 0:w]
        mortar = (((xx+shift)//43 + yy//13) % 4) == 0
        bg = np.where(mortar[:, :, None], np.array([32, 48, 70], np.uint8),
                      np.array([40, 63, 99], np.uint8)).astype(np.uint8)
        ripple = ((np.sin((xx+shift)/7.)+1)*6).astype(np.uint8)
        bg = cv2.add(bg, np.repeat(ripple[:, :, None], 3, axis=2))
        for i, text in enumerate(lines):
            cv2.putText(bg, text, (6, 14+i*18), cv2.FONT_HERSHEY_SIMPLEX, .36, (10, 10, 10), 2, cv2.LINE_8)
            cv2.putText(bg, text, (6, 14+i*18), cv2.FONT_HERSHEY_SIMPLEX, .36, (236, 236, 238), 1, cv2.LINE_8)
        return bg

    def test_moving_scenery_with_same_text_is_not_a_change(self):
        lines = ['Alice : S> 150k ea', 'Bob : jpq', 'Carol : need 2 more', 'Dave : hi there']
        detector = ChangeDetector()
        self.assertTrue(detector.observe(self.frame(lines, 0))[0])
        self.assertGreaterEqual(len(detector.previous_ink[0]), 3)
        changes = [detector.observe(self.frame(lines, s))[0] for s in range(3, 40, 3)]
        self.assertLessEqual(sum(changes), 1)
        scrolled = lines[1:] + ['Eve : S> 160k ea']
        self.assertTrue(detector.observe(self.frame(scrolled, 42))[0])

    def test_scrollbar_no_longer_blocks_row_signatures(self):
        image = chat_1080p()
        changed, signature = ChangeDetector().observe(image)
        self.assertTrue(changed)
        self.assertGreaterEqual(len(signature), 2)


class TranslationBatching(unittest.TestCase):
    def test_burst_of_eight_is_one_model_batch(self):
        import threading
        batches = []
        gate = threading.Event()
        class Fake:
            def translate_many(self, texts, direction):
                gate.wait(2)
                batches.append(list(texts))
                return ['ko '+t for t in texts]
            def translate(self, text, direction):
                return 'ko '+text
        out = []
        queue = TranslationQueue(Fake(), out.append, lambda m: None)
        try:
            # First item occupies the worker; the next 8 arrive meanwhile.
            queue.submit('warmup', {})
            for i in range(8):
                queue.submit(f'message {i}', {})
            gate.set()
            for _ in range(200):
                if len(out) == 9:
                    break
                threading.Event().wait(.01)
        finally:
            queue.close()
        self.assertEqual(len(out), 9)
        self.assertLessEqual(len(batches), 2)


if __name__ == '__main__':
    unittest.main()


class JitterDedupeAndAdmission(unittest.TestCase):
    def test_one_glyph_nickname_or_body_jitter_is_same_message(self):
        from kain_maple_translator.visual_message_ledger import same
        r = lambda n, b: {'nickname': n, 'body': b}
        # R14: a short reply ('ty') from a one-glyph-different name is merged
        # only with neighbour-row scroll evidence (R13 _slot_same), not here.
        self.assertTrue(same(r('RoxasXI', 'ty for the buff'), r('RoxasXl', 'ty for the buff')))
        self.assertFalse(same(r('RoxasXI', 'ty'), r('RoxasXl', 'ty')))
        self.assertTrue(same(r('ZombiéLupin', 'xbow arrows*'), r('ZombieLupin', 'xbow arrows*')))
        self.assertTrue(same(r('itdepends', 'jpq rush lv 35 xbow'), r('itdepends', 'lpq rush lv 35 xbow')))

    def test_real_differences_stay_separate(self):
        from kain_maple_translator.visual_message_ledger import same
        r = lambda n, b: {'nickname': n, 'body': b}
        self.assertFalse(same(r('Kain1', 'ty'), r('Kain2', 'ty')))        # different numbered alts
        self.assertFalse(same(r('Alice', 'S> 150k'), r('Alice', 'S> 160k')))  # price change
        self.assertFalse(same(r('Bob', 'yes'), r('Bob', 'no')))
        self.assertFalse(same(r('Bob', 'ok'), r('Bob', 'ok!!')))           # two glyphs

    def test_spam_line_confirmed_despite_symbol_count_jitter(self):
        from kain_maple_translator.row_admission import RowAdmission
        gate = RowAdmission()
        row = lambda body: dict(nickname='Abisune', body=body, kind='normal', confidence=.85,
                                source_white_body=False, rect=(0, 70, 600, 21))
        self.assertEqual(gate.filter([row('J>PQ ' + '@'*24)], 1.0), [])
        self.assertEqual(len(gate.filter([row('J>PQ ' + '@'*25)], 1.4)), 1)


class BrightRowGeometry(unittest.TestCase):
    def scene(self):
        h, w = 80, 640
        yy, xx = np.mgrid[0:h, 0:w]
        mortar = ((xx//43 + yy//13) % 4) == 0
        return np.where(mortar[:, :, None], np.array([32, 48, 70], np.uint8),
                        np.array([40, 63, 99], np.uint8)).astype(np.uint8)

    def test_far_white_sprite_does_not_widen_text_row(self):
        from kain_maple_translator.fast_vision import _bright_glyph_rows
        img = self.scene()
        cv2.putText(img, 'Alice : need 2 more', (8, 18), cv2.FONT_HERSHEY_SIMPLEX, .4, (240, 240, 240), 1, cv2.LINE_8)
        cv2.putText(img, 'Bob : jpq', (8, 40), cv2.FONT_HERSHEY_SIMPLEX, .4, (240, 240, 240), 1, cv2.LINE_8)
        cv2.rectangle(img, (520, 8), (560, 18), (235, 235, 235), -1)  # white sprite far right
        rows = _bright_glyph_rows(img)
        top = min(rows, key=lambda r: r.rect[1])
        self.assertLess(top.rect[0]+top.rect[2], 300)

    def test_dotted_strip_edge_below_text_does_not_widen_row(self):
        from kain_maple_translator.fast_vision import _bright_glyph_rows
        img = self.scene()
        cv2.putText(img, 'Alice : hi there', (8, 18), cv2.FONT_HERSHEY_SIMPLEX, .4, (240, 240, 240), 1, cv2.LINE_8)
        cv2.putText(img, 'Bob : jpq', (8, 40), cv2.FONT_HERSHEY_SIMPLEX, .4, (240, 240, 240), 1, cv2.LINE_8)
        img[21, 4:620:3] = (230, 230, 230)  # 1px dotted band edge right under row 1
        rows = _bright_glyph_rows(img)
        top = min(rows, key=lambda r: r.rect[1])
        self.assertLess(top.rect[0]+top.rect[2], 300)


class SymbolSpamComparison(unittest.TestCase):
    def test_trade_line_with_jittery_at_spam_is_one_message(self):
        from kain_maple_translator.visual_message_ledger import same
        r = lambda b: {'nickname': 'iceash', 'body': b}
        self.assertTrue(same(r('S > 60% ATK SCROLL BOW 100K ' + '@'*18 + ' @@④@@@@@@@@@'),
                             r('S > 60% ATK SCROLL BOW 100K ' + '@'*15 + '②@@ @@@@@@@@@@Q②')))

    def test_price_change_under_spam_is_still_new(self):
        from kain_maple_translator.visual_message_ledger import same
        r = lambda b: {'nickname': 'iceash', 'body': b}
        self.assertFalse(same(r('S> 60% ATK SCROLL BOW 100K @@@@@@@@'), r('S> 60% ATK SCROLL BOW 200K @@@@@@@@')))
