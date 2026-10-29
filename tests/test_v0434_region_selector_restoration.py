"""Non-dimming selector input/restoration contracts for the 0.4.33 regression."""
import unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
SRC=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
SEL=SRC.split('class RegionSelector(QWidget):',1)[1].split('class Glass(QWidget):',1)[0]
CTRL=SRC.split('    def choose_region(self):',1)[1].split('    def selected(self,region):',1)[0]

class SelectionRestoration(unittest.TestCase):
    def test_selector_has_nonzero_hit_test_alpha_no_visible_dimmer(self):
        self.assertIn('QColor(0, 0, 0, 2)',SEL)
        self.assertNotIn('QColor(2,8,16,135)',SEL)
        self.assertNotIn('QColor(0,0,0,0)',SEL)
        self.assertIn('WA_TransparentForMouseEvents, False', SEL)

    def test_selector_can_cancel_by_escape_and_right_click(self):
        self.assertIn('Qt.Key.Key_Escape',SEL)
        self.assertIn('Qt.MouseButton.RightButton',SEL)
        self.assertIn('self.finish(None)',SEL)

    def test_selector_window_manager_close_restores_app_once(self):
        self.assertIn('def closeEvent(self, event):',SEL)
        self.assertIn('if not self._completed:',SEL)
        self.assertIn('self.selected.emit(None)',SEL)
        self.assertIn('self._completed = True',SEL)

    def test_panels_are_hidden_after_selector_is_visible(self):
        self.assertLess(CTRL.index('picker.show()'),CTRL.index('self.left.hide()'))
        self.assertLess(CTRL.index('if not picker.isVisible():'),CTRL.index('self.left.hide()'))

    def test_timeout_and_visibility_fail_safe(self):
        self.assertIn('QTimer.singleShot(60000',CTRL)
        self.assertIn('self._check_selector_visible(picker)',CTRL)
        self.assertIn('self.selected(None)',CTRL)

    def test_selected_handler_restores_two_controls_and_chat_layout(self):
        segment=SRC.split('    def selected(self,region):',1)[1].split('    def toggle_worker(self):',1)[0]
        self.assertIn('self.left.show()',segment)
        self.assertIn('self.right.show()',segment)
        self.assertIn('self.relayout()',segment)
        self.assertIn('self.worker.update_settings(self.cfg)',segment)

if __name__=='__main__': unittest.main()
