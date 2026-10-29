"""R20: the control panel folds with _, the KO > EN panel closes with its X,
and the green 번역 button opens/closes the KO > EN panel."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kain_maple_translator import classic_ui as CU

APP = QApplication.instance() or QApplication([])


def centre(rect):
    x, y, w, h = rect
    return QPoint(x + w // 2, y + h // 2)


class ControlPanel(unittest.TestCase):
    def setUp(self):
        from kain_maple_translator.main import CompactSettings
        self.panel = CompactSettings()
        self.panel.fit_bottom_hud(390, 126)
        self.panel.show()
        APP.processEvents()

    def tearDown(self):
        self.panel.close()

    def test_green_translate_button_opens_the_composer(self):
        self.assertEqual(self.panel.tester.text(), '번역')
        self.assertEqual(self.panel.tester.property('classic'), 'lime')
        hits = []
        self.panel.composer_toggle.connect(lambda: hits.append(1))
        self.panel.tester.click()
        self.assertEqual(hits, [1])

    def test_minimize_button_folds_to_title_and_status(self):
        full = self.panel.height()
        folded = []
        self.panel.minimize_toggled.connect(folded.append)
        QTest.mouseClick(self.panel, Qt.MouseButton.LeftButton, pos=centre(
            CU.panel_min_rect(self.panel.width(), self.panel.height())))
        self.assertEqual(folded, [True])
        self.panel.fit_bottom_hud(390, 126)
        APP.processEvents()
        self.assertLess(self.panel.height(), full * 0.6)
        self.assertTrue(self.panel.status.isVisible())
        for widget in self.panel._body_widgets():
            self.assertFalse(widget.isVisible())
        # the same button (now a window box) opens it again
        QTest.mouseClick(self.panel, Qt.MouseButton.LeftButton, pos=centre(
            CU.panel_min_rect(self.panel.width(), self.panel.height())))
        self.assertEqual(folded, [True, False])
        self.panel.fit_bottom_hud(390, 126)
        APP.processEvents()
        self.assertEqual(self.panel.height(), full)
        self.assertTrue(self.panel.toggle_btn.isVisible())

    def test_x_still_quits(self):
        hits = []
        self.panel.quit.connect(lambda: hits.append(1))
        QTest.mouseClick(self.panel, Qt.MouseButton.LeftButton, pos=centre(
            CU.panel_close_rect(self.panel.width(), self.panel.height())))
        self.assertEqual(hits, [1])


class Composer(unittest.TestCase):
    def test_x_closes(self):
        from kain_maple_translator.main import CompactComposer
        panel = CompactComposer()
        panel.fit_bottom_hud(330, 126)
        panel.show()
        APP.processEvents()
        hits = []
        panel.closed.connect(lambda: hits.append(1))
        QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=centre(
            CU.panel_close_rect(panel.width(), panel.height())))
        self.assertEqual(hits, [1])
        panel.close()


class Sprites(unittest.TestCase):
    def test_minimize_buttons_look_like_the_game_x(self):
        x = CU.piece('button/close_normal')
        for restore in (False, True):
            img = CU.min_sprite('normal', restore)
            self.assertEqual(img.shape, x.shape)
            self.assertTrue((img[0] == x[0]).all())        # same black rim
            self.assertFalse((img == x).all())


class Settings(unittest.TestCase):
    def test_new_keys_persist_and_test_moved_to_settings(self):
        from kain_maple_translator.core import load_config, save_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            cfg = load_config(path)
            self.assertTrue(cfg['composer_visible'])
            self.assertFalse(cfg['left_panel_minimized'])
            cfg['composer_visible'] = False
            cfg['left_panel_minimized'] = True
            save_config(cfg, path)
            again = load_config(path)
            self.assertFalse(again['composer_visible'])
            self.assertTrue(again['left_panel_minimized'])
        src = (Path(__file__).resolve().parents[1] / 'kain_maple_translator' / 'main.py').read_text('utf-8')
        self.assertIn("QPushButton('오프라인 번역 시험')", src)
        self.assertIn('dlg.test_translation_requested.connect(self.test_translation)', src)


if __name__ == '__main__':
    unittest.main()
