"""v0.4.3 - controls always above game unless modes disabled."""
from pathlib import Path
import unittest
from kain_maple_translator.window_behavior import (
    HWND_TOPMOST, HWND_NOTOPMOST, stack_target, Z_ORDER_MODES,
)

ROOT = Path(__file__).resolve().parents[1]

class Regression043(unittest.TestCase):
    def test_game_mode_promotes_even_non_topmost_fullscreen_game(self):
        self.assertEqual(stack_target('game', game_or_controls_active=True,
                                      game_topmost=False), HWND_TOPMOST)
        self.assertEqual(stack_target('game', game_or_controls_active=True,
                                      game_topmost=True), HWND_TOPMOST)
        self.assertIsNone(stack_target('game',game_or_controls_active=False))

    def test_always_remains_topmost_even_when_game_not_active(self):
        self.assertEqual(stack_target('always', game_or_controls_active=False),
                         HWND_TOPMOST)
        self.assertEqual(stack_target('normal', game_or_controls_active=True),
                         HWND_NOTOPMOST)

    def test_controls_and_chat_always_promoted_together(self):
        code=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        sync=code.split('    def sync_stack(self):',1)[1].split('    def apply_chat_appearance(self):',1)[0]
        self.assertIn('panels=(self.chat,self.left,self.right)',sync)
        for mode in ("mode == 'always'", "mode == 'normal'"):
            self.assertIn(mode,sync)
        self.assertIn("set_native_stack(int(widget.winId()),'always')",sync)
        self.assertIn("set_native_stack(int(widget.winId()),'normal')",sync)
        self.assertIn("set_native_stack(int(widget.winId()),'game'",sync)
        self.assertIn('restore_below_foreground(int(widget.winId()),self.game_hwnd)',sync)
        self.assertNotIn('for widget in windows[1:]',sync)

    def test_settings_toggle_applies_immediately(self):
        code=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        method=code.split('    def save_settings_dialog(self, dlg):',1)[1].split('    def test_translation(self):',1)[0]
        self.assertIn('self.chat.set_top_mode(next_mode)',method)
        self.assertIn('self.sync_stack()',method)
        self.assertIn("self.cfg['top_mode']=next_mode",method)

    def test_captures_remain_available_in_topmost_modes(self):
        code=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('enable_obs_window_capture(self.chat)',code)

if __name__=='__main__': unittest.main()
