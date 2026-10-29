"""OBS source + normal Z-order regression tests, no Qt or Windows required."""
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from kain_maple_translator.obs_source import OBSChatSource, OBS_HTML
from kain_maple_translator.window_behavior import (
    Z_ORDER_MODES, capture_allowed, foreground_is_game, foreground_context,
    set_native_stack, stack_target, restore_below_foreground, is_topmost,
    WDA_NONE, HWND_TOP, HWND_TOPMOST, HWND_NOTOPMOST,
)
from kain_maple_translator.core import load_config, save_config

ROOT=Path(__file__).resolve().parents[1]

class ObsCaptureTests(unittest.TestCase):
    def test_local_obs_source_http_and_unicode(self):
        obs=OBSChatSource(port=0)
        try:
            url=obs.start()
            self.assertTrue(url.startswith('http://127.0.0.1:'))
            obs.set_state([('MapleKing','커닝 파퀘 모여요'),('A<script>','파티 모집')],
                          font_size=19,font_family='Malgun Gothic',opacity=74)
            with urlopen(url+'state',timeout=3) as stream:
                obj=json.loads(stream.read().decode('utf-8'))
                self.assertIn('no-store',stream.headers['Cache-Control'])
            self.assertEqual(obj['messages'][0],['MapleKing','커닝 파퀘 모여요'])
            self.assertEqual(obj['opacity'],74)
            self.assertEqual(obj['font_size'],19)
            with urlopen(url,timeout=3) as stream:
                page=stream.read().decode('utf-8')
                self.assertIn('background:transparent',page)
                self.assertIn('textContent=',page)
                self.assertNotIn('A<script>',page)
            self.assertEqual(obs.state()['revision'],1)
        finally:
            obs.close()

    def test_empty_initial_state_and_limits(self):
        obs=OBSChatSource(port=0)
        obs.set_state([('x','y')]*110,font_size=100,opacity=200)
        state=obs.state()
        self.assertEqual(len(state['messages']),95)
        self.assertEqual(state['font_size'],38)
        self.assertEqual(state['opacity'],100)
        with self.assertRaises(ValueError):
            OBSChatSource(host='0.0.0.0')

    def test_config_persists_three_stacking_modes(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            path=Path(d)/'config.json'
            cfg=load_config(path)
            self.assertEqual(cfg['top_mode'],'game')
            for value in Z_ORDER_MODES:
                cfg['top_mode']=value
                save_config(cfg,path)
                self.assertEqual(load_config(path)['top_mode'],value)

    def test_no_exclusion_and_no_topmost_for_game_mode(self):
        ui=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertNotIn('exclude_from_capture(',ui)
        self.assertIn('self.top_mode == \'always\'',ui)
        self.assertIn('foreground_context(self.game_hwnd,self.game_pid,os.getpid())',ui)
        self.assertIn("set_native_stack(int(widget.winId()),'game',",ui)
        self.assertIn("self.setWindowTitle('글클메 애드온 - 채팅')",ui)
        self.assertIn("self.left.obs_copy.connect(self.copy_obs_url)",ui)
        self.assertIn('self.obs.close()',ui)
        self.assertNotIn('self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)',ui)
        self.assertNotIn('0x11)',ui)
        self.assertEqual(WDA_NONE,0)
        self.assertNotEqual(HWND_TOP,HWND_TOPMOST)
        self.assertNotEqual(HWND_NOTOPMOST,HWND_TOPMOST)

    def test_game_only_stack_policy_keeps_controls_above_maple(self):
        # Game or any KAIN dialog has focus: the panel can be raised.
        self.assertEqual(stack_target('game',game_or_controls_active=True), HWND_TOPMOST)
        self.assertEqual(stack_target('game',game_or_controls_active=True,game_topmost=True),HWND_TOPMOST)
        # Another app has focus: no unsolicited foreground stealing.
        self.assertIsNone(stack_target('game',game_or_controls_active=False))
        self.assertEqual(stack_target('always'),HWND_TOPMOST)
        self.assertEqual(stack_target('normal'),HWND_NOTOPMOST)

    def test_panels_and_modal_dialogs_preserved_during_focus_changes(self):
        ui=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('context in (\'game\',\'controls\')',ui)
        self.assertIn('isinstance(w,QDialog) and w.isVisible()',ui)
        self.assertIn('self.layout_timer.setInterval(200)',ui)
        self.assertIn('self._last_stack_mode',ui)
        self.assertIn('stacking_v037_initialized',ui)
        self.assertIn('restore_below_foreground',ui)
        self.assertNotIn('SetForegroundWindow',ui)

    def test_win32_calls_safe_nonwindows(self):
        with patch('kain_maple_translator.window_behavior.sys.platform','linux'):
            self.assertFalse(capture_allowed(123))
            self.assertFalse(foreground_is_game(123,456))
            self.assertFalse(set_native_stack(123,'game',game_foreground=True))
            self.assertEqual(foreground_context(123,456,789),'other')
            self.assertFalse(is_topmost(123))
            self.assertFalse(restore_below_foreground(123, 456))
        with self.assertRaisesRegex(ValueError,'Invalid z-order'):
            set_native_stack(123,'invalid')

if __name__=='__main__':
    unittest.main()
