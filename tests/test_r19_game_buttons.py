"""R19: every addon button is the game's own button sprite (MCW data)."""
import os
import re
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6.QtWidgets import QApplication

from kain_maple_translator import classic_ui as CU
from kain_maple_translator import visual_theme as T

ROOT = Path(__file__).resolve().parents[1] / 'resources' / 'classic_ui'
STATES = ('normal', 'hover', 'pressed', 'disabled')


class Sprites(unittest.TestCase):
    def test_all_kinds_and_states_exist(self):
        for kind in ('lime', 'orange', 'pink', 'blue', 'cancel', 'close'):
            for state in STATES:
                img = CU.piece(f'button/{kind}_{state}')
                self.assertEqual(img.shape[2], 4, (kind, state))
                self.assertGreaterEqual(img.shape[0], 12)
        caps = CU._button_caps()
        for kind in ('lime', 'orange', 'pink', 'blue', 'cancel'):
            for state in STATES:
                self.assertIn(caps.get(f'{kind}_{state}'), (2, 3, 4))

    def test_blank_middle_has_no_letters(self):
        # the stored middle is one clean column repeated: all middle columns equal
        for kind in ('lime', 'orange', 'pink', 'blue', 'cancel'):
            name = f'{kind}_normal'
            img = CU.piece(f'button/{name}').astype(int)
            cap = CU._button_caps()[name]
            mid = img[:, cap:img.shape[1] - cap]
            self.assertEqual(np.abs(mid - mid[:, :1]).max(), 0, kind)

    def test_qss_images_exist(self):
        css = T.game_buttons()
        for path in re.findall(r'url\("([^"]+)"\)', css):
            self.assertTrue(Path(path).exists(), path)
        self.assertIn('qss_btn_blue_hover.png', css)
        self.assertIn('qss_btn_cancel_disabled.png', css)


class Drawing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_kind_and_state_draws(self):
        for kind in ('blue', 'confirm', 'lime', 'orange', 'pink', 'cancel', 'gray', 'close'):
            for state in STATES:
                c = CU.Canvas(60, 18)
                c.ui_button(0, 0, 60, 18, '닫기', state, kind)
                self.assertGreater(int(c.px[:, :, 3].max()), 0, (kind, state))

    def test_states_look_different(self):
        shots = []
        for state in STATES:
            c = CU.Canvas(60, 18)
            c.ui_button(0, 0, 60, 18, 'OK', state, 'lime')
            shots.append(c.px.copy())
        for i in range(len(shots)):
            for j in range(i + 1, len(shots)):
                self.assertFalse(np.array_equal(shots[i], shots[j]), (STATES[i], STATES[j]))

    def test_short_and_tall_buttons(self):
        for h in (12, 15, 18, 25):
            c = CU.Canvas(40, h)
            c.ui_button(0, 0, 40, h, '고정', 'normal', 'orange', px=11)
            self.assertEqual(c.px.shape[0], h)

    def test_close_pixmap_and_title_bar(self):
        pix = CU.close_pixmap()
        self.assertFalse(pix.isNull())
        self.assertGreater(pix.width(), 12)       # stretched like the game window
        bar = CU.ClassicTitleBar('PRICE LOG')
        bar.resize(400, bar.height())
        self.assertFalse(bar.grab().isNull())

    def test_windows_use_game_kinds(self):
        from kain_maple_translator.classic_windows import PriceLogWindow

        class Log:
            def summary(self, q):
                return []

            def clear(self):
                pass
        w = PriceLogWindow(Log())
        kinds = {b.text(): b.property('classic') for b in w.findChildren(CU.ClassicButton)}
        self.assertEqual(kinds['새로고침'], 'blue')
        self.assertEqual(kinds['기록 전부 지우기'], 'lime')
        self.assertEqual(kinds['닫기'], 'cancel')
        for b in w.findChildren(CU.ClassicButton):
            self.assertGreaterEqual(b.minimumWidth(), round(47 * CU.SCALE[0]))
        # opened from the panel it must not land behind the game window
        from PySide6.QtCore import Qt
        self.assertTrue(w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        w.close()


class PanelStrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_status_text_centred_between_strip_lines(self):
        from PySide6.QtGui import QImage
        from kain_maple_translator.main import CompactSettings
        for text in ('화면 대기 0.5초 (2장) · OCR 2171.0ms · 번역', '번역 표시됨 · MinnowD'):
            w = CompactSettings()
            w.fit_bottom_hud(390, 126)
            w.set_status(text)
            w.show()
            self.app.processEvents()
            img = w.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
            a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
            a = a[:, :img.width(), :3].astype(int)
            h = a.shape[0]
            # the strip's two dark steel-blue lines in a text-free column at the right
            # (not the black edge of the button above)
            col = a[:, w.width() - 12]
            lines = [y for y in range(h - 30, h) if col[y].sum() < 430 and col[y][0] - col[y][2] > 40]
            self.assertGreaterEqual(len(lines), 2, lines)
            top, bottom = lines[0], lines[-1]
            # white letter faces in the text area between them
            band = a[top + 1:bottom, 20:150]
            rows = [y for y in range(band.shape[0]) if (band[y].min(axis=1) > 228).sum() >= 2]
            self.assertTrue(rows, text)
            gap_top, gap_bottom = rows[0], band.shape[0] - 1 - rows[-1]
            self.assertGreaterEqual(gap_top, 1, (text, gap_top, gap_bottom))
            self.assertGreaterEqual(gap_bottom, 1, (text, gap_top, gap_bottom))
            self.assertLessEqual(abs(gap_top - gap_bottom), 2, (text, gap_top, gap_bottom))
            w.close()


class HowToUse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_poster_window(self):
        from kain_maple_translator.classic_windows import HelpWindow, help_image_path
        self.assertTrue(help_image_path().exists())
        w = HelpWindow()
        pix = w.poster.pixmap()
        self.assertFalse(pix.isNull())
        self.assertEqual(pix.width(), 850)
        self.assertGreater(pix.height(), 1500)          # the whole poster, scrollable
        w.close()

    def test_settings_has_help_button(self):
        from PySide6.QtWidgets import QPushButton
        from kain_maple_translator.main import SettingsDialog
        dlg = SettingsDialog({}, None)
        hits = []
        dlg.help_requested.connect(lambda: hits.append(1))
        button = [b for b in dlg.findChildren(QPushButton) if b.text() == '사용법 · 기능 안내 보기']
        self.assertEqual(len(button), 1)
        button[0].click()
        self.assertEqual(hits, [1])
        dlg.close()


class ChatRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_general_rows_are_separated(self):
        from kain_maple_translator.main import FloatingChat
        chat = FloatingChat()
        chat.apply_style({}, 98)
        chat.resize(430, 520)
        chat._update_skin()
        row = chat._make_row('Leo', '금방 올게요', {'kind': 'normal'})
        self.assertIn('border-bottom:1px solid rgba(0,0,0,30)', row.styleSheet())
        chat.resize(430, 150)
        chat._update_skin()
        row = chat._make_row('Leo', '금방 올게요', {'kind': 'normal'})
        self.assertIn('rgba(0,0,0,38)', row.styleSheet())
        chat.close()


if __name__ == '__main__':
    unittest.main()
