"""R20: windowed game resolutions 1280x720 .. 2560x1440.

The game scales its HUD by client height (never below 1.0) with UI size
'기본 비율', and by whole numbers with '최적 비율'. Chat detection, the chat
estimate, the side panels and a chat crop chosen at another resolution must
all follow that, not the window's width/height ratio.
"""
import sys
import time
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from kain_maple_translator.auto_chat_detect import detect_chat_region, estimate
from kain_maple_translator.capture_stream import ChatCaptureStream
from kain_maple_translator.game_window import region_to_relative
from kain_maple_translator.layout import (estimate_chat_area, game_ui_scale,
                                          hud_panel_geometry, hud_relative_region)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'resolutions'

BLUE = (111, 83, 54)        # the chat-target button, BGR


def hud_frame(w, h, s, sprite=False):
    """Synthetic client: the blue chat-target button and the white input field
    at UI scale s, where the real game draws them."""
    img = np.full((h, w, 3), (155, 155, 155), np.uint8)
    cx = w / 2
    left, right = round(cx - 396 * s), round(cx - 316 * s)
    top, bottom = round(h - 62 * s), round(h - 44 * s)
    cv2.rectangle(img, (right + 3, top), (right + round(460 * s), bottom - 2), (245, 245, 245), -1)
    cv2.rectangle(img, (left, top), (right - 1, bottom - 1), BLUE, -1)
    # the white letters of '전체'
    cv2.rectangle(img, (round(left + 30 * s), round(top + 4 * s)),
                  (round(left + 50 * s), round(bottom - 5 * s)), (240, 240, 240), -1)
    if sprite:
        # a character in blue clothes standing against the button's left end
        cv2.rectangle(img, (left - round(24 * s), top - round(5 * s)), (left + 1, bottom - round(8 * s)), BLUE, -1)
    return img, left, top


class GameScale(unittest.TestCase):
    def test_scale_by_height_never_below_one(self):
        for (w, h), s in {(1280, 720): 1.0, (1366, 768): 1.0, (1920, 1080): 1080 / 768,
                          (1920, 1200): 1.5625, (2560, 1440): 1.875}.items():
            with self.subTest(size=(w, h)):
                self.assertAlmostEqual(game_ui_scale(w, h), s, places=4)

    def test_estimate_matches_measured_chat_text(self):
        # chat text left edge = blue button left; top just above the button
        for (w, h), (x, y) in {(1280, 720): (244, 586), (1366, 768): (287, 634),
                               (1920, 1200): (342, 991), (2560, 1440): (539, 1189)}.items():
            with self.subTest(size=(w, h)):
                ex, ey, ew, eh = estimate_chat_area((0, 0, w, h))
                self.assertLessEqual(abs(ex - x), 2)
                self.assertLessEqual(abs(ey - y), 2)
                self.assertEqual(ew, round(558 * game_ui_scale(w, h)))

    def test_stale_resolution_hint_is_ignored(self):
        # a '1920x1080' setting left over while the game now runs at 1280x720
        self.assertEqual(estimate_chat_area((0, 0, 1280, 720), '1920x1080'),
                         estimate_chat_area((0, 0, 1280, 720)))

    def test_fullscreen_stretch_hint_still_used(self):
        # 1280x720 game stretched over a 1920x1080 screen: UI 1.0 x 1.5
        x, y, w, h = estimate_chat_area((0, 0, 1920, 1080), '1280x720')
        self.assertEqual(w, 837)

    def test_side_panels_stop_at_the_game_hud(self):
        for w, h in [(1280, 720), (1366, 768), (1920, 1080), (1920, 1200), (2560, 1440)]:
            with self.subTest(size=(w, h)):
                chat = dict(zip(('left', 'top', 'width', 'height'), estimate_chat_area((0, 0, w, h))))
                left, right = hud_panel_geometry((0, 0, w, h), (0, 0, w, h), chat)
                self.assertLessEqual(left[0] + left[2], chat['left'])
                self.assertGreaterEqual(left[2], 155)
                self.assertGreaterEqual(right[2], 155)
                hud = 803 * game_ui_scale(w, h)
                self.assertAlmostEqual(right[0] - (left[0] + left[2]), hud, delta=1)

    def test_measured_scale_overrides_the_guess(self):
        l1, r1 = hud_panel_geometry((0, 0, 2560, 1440), (0, 0, 2560, 1440), None)
        l2, r2 = hud_panel_geometry((0, 0, 2560, 1440), (0, 0, 2560, 1440), None, ui_scale=2.0)
        self.assertLess(l2[2], l1[2])
        self.assertEqual(r2[0] - (l2[0] + l2[2]), 1606)


class CropAtAnotherResolution(unittest.TestCase):
    def test_manual_crop_from_1080p_follows_the_hud_to_720p(self):
        # the crop a user drew at 1920x1080 (fractions of that client)
        game0 = (0, 0, 1920, 1080)
        drawn = {'left': 403, 'top': 891, 'width': 767, 'height': 90}
        rel = vars(region_to_relative(game0, drawn))
        ref = {'width': 1920, 'height': 1080, 'scale': game_ui_scale(1920, 1080)}
        moved = hud_relative_region(rel, ref, (10, 354, 1280, 720))
        # the chat text starts at 244 in a 1280x720 client
        self.assertLessEqual(abs(moved['left'] - (10 + 244)), 2)
        self.assertEqual(moved['width'], round(767 / (1080 / 768)))
        self.assertEqual(moved['top'] + moved['height'], 354 + 720 - round((1080 - 981) * 768 / 1080))

    def test_same_size_round_trip(self):
        game = (100, 50, 1920, 1200)
        drawn = {'left': 400, 'top': 1040, 'width': 800, 'height': 100}
        rel = vars(region_to_relative(game, drawn))
        ref = {'width': 1920, 'height': 1200, 'scale': 1.5625}
        moved = hud_relative_region(rel, ref, game)
        for key in drawn:
            self.assertLessEqual(abs(moved[key] - drawn[key]), 1)

    def test_main_remembers_the_game_size_of_a_crop(self):
        src = (ROOT / 'kain_maple_translator' / 'main.py').read_text('utf-8')
        self.assertIn("self.cfg['chat_region_game']=", src)
        self.assertIn('hud_relative_region(relative,ref,win.rect)', src)
        self.assertIn("'auto_chat_game_size'", src)
        from kain_maple_translator.core import DEFAULTS
        self.assertIn('chat_region_game', DEFAULTS)


class SettingsKept(unittest.TestCase):
    def test_new_keys_survive_a_restart(self):
        import tempfile
        from kain_maple_translator.core import load_config, save_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            cfg = load_config(path)
            self.assertFalse(cfg['help_seen_r19'])
            cfg['help_seen_r19'] = True
            cfg['chat_region_game'] = {'width': 1920, 'height': 1080, 'scale': 1.4062}
            save_config(cfg, path)
            again = load_config(path)
            # R19 kept neither: the how-to poster opened on every start
            self.assertTrue(again['help_seen_r19'])
            self.assertEqual(again['chat_region_game']['width'], 1920)


class SyntheticDetection(unittest.TestCase):
    def test_every_resolution_and_ui_size(self):
        cases = [((1280, 720), 1.0), ((1366, 768), 1.0), ((1920, 1080), 1080 / 768),
                 ((1920, 1200), 1.5625), ((2560, 1440), 1.875),
                 ((2560, 1440), 2.0), ((1920, 1080), 1.0), ((1920, 1080), 2.0)]
        for (w, h), s in cases:
            for sprite in (False, True):
                with self.subTest(size=(w, h), scale=s, sprite=sprite):
                    img, left, top = hud_frame(w, h, s, sprite)
                    found = detect_chat_region(img, (0, 0, w, h))
                    self.assertIsNotNone(found)
                    self.assertAlmostEqual(found.scale, s, delta=.02)
                    self.assertLessEqual(abs(found.region['left'] - left), 2)
                    self.assertEqual(found.region['width'], round(558 * found.scale))
                    self.assertLessEqual(abs(found.region['top'] + found.region['height'] - (top - 3 * s)), 3)

    def test_blue_without_the_input_field_is_not_the_chat(self):
        img, left, top = hud_frame(1366, 768, 1.0)
        img[top:top + 20, 371:900] = (155, 155, 155)      # no white field
        self.assertIsNone(detect_chat_region(img, (0, 0, 1366, 768)))

    def test_estimate_reports_scale(self):
        self.assertAlmostEqual(estimate((0, 0, 1920, 1200)).scale, 1.5625)


class RealCaptures(unittest.TestCase):
    """Bottom HUD bands of real game clients (private fixtures)."""
    EXPECT = {'hud_1280x720_default.png': ((1280, 720), 1.0, 244),
              'hud_1366x768_default.png': ((1366, 768), 1.0, 287),
              'hud_1920x1200_default.png': ((1920, 1200), 1.5625, 342),
              'hud_2560x1440_default.png': ((2560, 1440), 1.875, 539),
              'hud_2560x1440_optimal.png': ((2560, 1440), 2.0, 488),
              'hud_1920x1080_default.png': ((1920, 1080), 1080 / 768, 404)}

    def test_detects_chat_and_scale(self):
        if not FIXTURES.exists():
            self.skipTest('No resolution fixtures')
        for name, ((w, h), s, left) in self.EXPECT.items():
            path = FIXTURES / name
            if not path.exists():
                continue
            with self.subTest(name=name):
                band = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
                img = np.zeros((h, w, 3), np.uint8)
                img[h - band.shape[0]:] = band
                found = detect_chat_region(img, (0, 0, w, h))
                self.assertIsNotNone(found)
                self.assertAlmostEqual(found.scale, s, delta=.01)
                self.assertLessEqual(abs(found.region['left'] - left), 3)

    def test_user_1080p_screenshot_matches_the_hand_drawn_area(self):
        path = ROOT / 'tests' / 'fixtures' / 'hunt-1080p-user-screenshot.png'
        if not path.exists():
            self.skipTest('No 1080p fixture')
        img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        found = detect_chat_region(img, (0, 0, w, h))
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found.scale, h / 768, delta=.02)
        # the user drew the chat area at 403,891 on this client
        self.assertLessEqual(abs(found.region['left'] - 403), 3)
        self.assertLessEqual(abs(found.region['top'] - 891), 3)


class ResizeRedetects(unittest.TestCase):
    """A new game resolution on the same window finds the chat again."""

    def test_wgc_size_change_runs_detection_again(self):
        sizes = {'rect': (0, 0, 1366, 768)}

        @dataclass
        class Game:
            hwnd: int = 77

            @property
            def rect(self):
                return sizes['rect']

        frames = {(1366, 768): hud_frame(1366, 768, 1.0)[0],
                  (1920, 1200): hud_frame(1920, 1200, 1.5625)[0]}

        class Source:
            def __init__(self, hwnd, client_rect, region):
                self.region = dict(region)
                self.arrivals = 0
                self.queue_overflows = 0
                self.started_at = time.monotonic()
                self.error = None

            def start(self):
                pass

            def set_geometry(self, rect, region):
                self.region = dict(region)

            def get(self, timeout=.05):
                time.sleep(.01)
                self.arrivals += 1
                gx, gy, gw, gh = sizes['rect']
                img = frames[(gw, gh)]
                r = self.region
                if (r['width'], r['height']) == (gw, gh):
                    return img.copy(), dict(r), time.monotonic()
                if r['left'] + r['width'] > gw or r['top'] + r['height'] > gh:
                    return None
                return (img[r['top']:r['top'] + r['height'], r['left']:r['left'] + r['width']].copy(),
                        dict(r), time.monotonic())

            @property
            def finished(self):
                return False

            def close(self):
                pass

        class NoMss:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        cfg = {'capture_backend': 'wgc', 'auto_chat_region': True, 'enabled': {'chat': True},
               'regions': {'chat': None}, 'capture_interval': .08}
        stream = ChatCaptureStream(lambda: cfg, lambda err: None)
        with (patch.dict(sys.modules, {'mss': types.SimpleNamespace(mss=NoMss)}),
              patch('kain_maple_translator.game_window.find_maple_window', return_value=Game()),
              patch('kain_maple_translator.wgc_capture.WgcWindowSource', Source),
              patch('kain_maple_translator.fast_vision.ink_rows', return_value=([], False))):
            stream.start()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and stream.auto_size != (1366, 768):
                time.sleep(.05)
            first = dict(stream.auto_region or {})
            sizes['rect'] = (0, 0, 1920, 1200)
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline and stream.auto_size != (1920, 1200):
                time.sleep(.05)
            second = dict(stream.auto_region or {})
            scale = stream.auto_scale
            stream.close()
        self.assertEqual(first.get('left'), 287)
        self.assertEqual(stream.auto_method, 'visual-chat-toolbar')
        self.assertAlmostEqual(scale, 1.5625, places=3)
        self.assertLessEqual(abs(second.get('left', 0) - 342), 2)


if __name__ == '__main__':
    unittest.main()
