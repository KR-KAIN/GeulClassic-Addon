"""Tracker default Z-order must follow Maple and yield to other programs."""
import unittest
from unittest.mock import patch
from pathlib import Path
from kain_maple_translator.hunt_zorder import GameRelativeOverlay, should_float_above_game

class FakeWin32:
    def __init__(self):
        self.foreground=100
        self.valid={100,200}
        self.minimized=set()
    def IsWindow(self,hwnd):return int(hwnd) in self.valid
    def IsIconic(self,hwnd):return int(hwnd) in self.minimized
    def GetForegroundWindow(self):return self.foreground

class Widget:
    def winId(self):return 200

class Tests(unittest.TestCase):
    def test_foreground_maple_or_widget_only(self):
        self.assertTrue(should_float_above_game(100,100,200))
        self.assertTrue(should_float_above_game(200,100,200))
        self.assertFalse(should_float_above_game(300,100,200))
        self.assertFalse(should_float_above_game(100,0,200))

    def test_normal_maple_uses_relative_position_not_topmost(self):
        fake=FakeWin32();layer=GameRelativeOverlay();tops=[];normal=[]
        with patch.object(GameRelativeOverlay,'_user32',return_value=fake),\
             patch('kain_maple_translator.hunt_zorder.is_topmost',return_value=False),\
             patch('kain_maple_translator.hunt_zorder.restore_below_foreground',
                   side_effect=lambda hwnd,game:normal.append((hwnd,game)) or True),\
             patch.object(GameRelativeOverlay,'_set_top',
                   side_effect=lambda hwnd,enabled,u=None:tops.append(enabled) or True):
            layer.sync(Widget(),100)
            self.assertEqual(normal,[(200,100)])
            self.assertEqual(tops,[])
            layer.sync(Widget(),100)
            self.assertEqual(len(normal),1)
            fake.foreground=300
            layer.sync(Widget(),100)
            self.assertEqual(tops,[])
            self.assertEqual(normal[-1],(200,100))
            fake.foreground=100
            layer.sync(Widget(),100)
            self.assertEqual(len(normal),3)
            layer.release(Widget())
            self.assertEqual(tops,[])

    def test_actual_topmost_game_is_temporary_only(self):
        fake=FakeWin32();layer=GameRelativeOverlay();tops=[]
        with patch.object(GameRelativeOverlay,'_user32',return_value=fake),\
             patch('kain_maple_translator.hunt_zorder.is_topmost',return_value=True),\
             patch('kain_maple_translator.hunt_zorder.restore_below_foreground',return_value=True),\
             patch.object(GameRelativeOverlay,'_set_top',
                   side_effect=lambda hwnd,enabled,u=None:tops.append(enabled) or True):
            layer.sync(Widget(),100)
            self.assertEqual(tops,[True])
            fake.foreground=300
            layer.sync(Widget(),100)
            self.assertEqual(tops,[True,False])
            fake.foreground=100
            layer.sync(Widget(),100)
            self.assertEqual(tops,[True,False,True])
            layer.release(Widget())
            self.assertEqual(tops,[True,False,True,False])

    def test_minimized_game_demotes_old_topmost(self):
        fake=FakeWin32();layer=GameRelativeOverlay();tops=[]
        with patch.object(GameRelativeOverlay,'_user32',return_value=fake),\
             patch('kain_maple_translator.hunt_zorder.is_topmost',return_value=True),\
             patch('kain_maple_translator.hunt_zorder.restore_below_foreground',return_value=True),\
             patch.object(GameRelativeOverlay,'_set_top',
                   side_effect=lambda hwnd,enabled,u=None:tops.append(enabled) or True):
            layer.sync(Widget(),100)
            fake.minimized.add(100)
            layer.sync(Widget(),100)
            self.assertEqual(tops,[True,False])

    def test_tracker_default_is_game_only_and_migrates_old_setting(self):
        s=(Path(__file__).resolve().parents[1]/'kain_maple_translator'/'hunt_widget.py').read_text('utf-8')
        self.assertIn('self.zorder_tick.timeout.connect(self._sync_game_zorder)',s)
        self.assertIn('self._relative_zorder.sync(self,self._known_game_hwnd)',s)
        self.assertIn('hunt_window_order_v050_migrated',s)
        self.assertIn('if self._pinned: flags |= Qt.WindowType.WindowStaysOnTopHint',s)
        self.assertIn('self._relative_zorder.release(self)',s)

if __name__=='__main__':unittest.main()
