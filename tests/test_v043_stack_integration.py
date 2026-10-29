"""Integration-style tests run Controller.sync_stack with fake window handles.

No PySide6 required; compile only the actual method from main.py and supply
fakes for native window methods. Tests the real algorithm rather than strings.
"""
from __future__ import annotations
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import os

ROOT = Path(__file__).resolve().parents[1]


class FakeWindow:
    def __init__(self, handle):
        self.handle = handle
    def isVisible(self):
        return True
    def winId(self):
        return self.handle


class FakeDialog(FakeWindow):
    pass


class FakeQApplication:
    @staticmethod
    def topLevelWidgets():
        return [FakeDialog(44)]


def extract_sync(method_env):
    tree = ast.parse((ROOT / 'kain_maple_translator/main.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Controller')
    meth = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'sync_stack')
    # Make the method available as a standalone Python function; source is unchanged.
    code = compile(ast.Module(body=[meth], type_ignores=[]), '<actual Controller.sync_stack>', 'exec')
    namespace = dict(method_env)
    exec(code, namespace)
    return namespace['sync_stack']


class Behavior043(unittest.TestCase):
    def setUp(self):
        self.operations=[]
        self.context='game'
        self.topmost={11:True,22:True,33:True,44:True}
        def setstack(hwnd, mode, **kwargs):
            self.operations.append(('set',hwnd,mode))
            self.topmost[hwnd] = mode != 'normal'
            return True
        def restore(hwnd, game_hwnd):
            self.operations.append(('restore',hwnd,game_hwnd))
            self.topmost[hwnd] = False
            return True
        env=dict(QApplication=FakeQApplication,QDialog=FakeDialog,
                 Z_ORDER_MODES=('always','game','normal'),
                 foreground_context=lambda *args:self.context,
                 is_topmost=lambda hwnd:self.topmost.get(hwnd,False),
                 set_native_stack=setstack,restore_below_foreground=restore,
                 os=os)
        self.runner=extract_sync(env)
        self.controller=SimpleNamespace(closing=False,selector=None,
                                        cfg={'top_mode':'always',
                                             'pin_settings_above_game':False},
                                        game_hwnd=888,game_pid=999,
                                        chat=FakeWindow(11),left=FakeWindow(22),
                                        right=FakeWindow(33),
                                        _prior_stack_active=None,
                                        _last_stack_mode=None)

    def test_always_on_keeps_both_panels_topmost_even_on_other_app_focus(self):
        self.context='other'
        self.runner(self.controller)
        for hwnd in (11,22,33):
            self.assertIn(('set',hwnd,'always'),self.operations)
        self.assertFalse(any(x[0]=='restore' for x in self.operations))

    def test_game_only_promotes_all_over_borderless(self):
        self.controller.cfg['top_mode']='game'
        self.context='game'
        self.runner(self.controller)
        for hwnd in (11,22,33):
            self.assertIn(('set',hwnd,'game'),self.operations)

    def test_game_only_yields_when_chrome_active_and_recovers(self):
        self.controller.cfg['top_mode']='game'
        self.context='game'
        self.runner(self.controller)
        self.operations.clear()
        self.context='other'
        self.runner(self.controller)
        self.assertEqual({x[1] for x in self.operations if x[0]=='restore'}, {11,22,33})
        self.operations.clear()
        self.context='game'
        self.runner(self.controller)
        self.assertEqual({x[1] for x in self.operations if x[0]=='set'}, {11,22,33})

    def test_normal_mode_demotes_all_three(self):
        self.controller.cfg['top_mode']='normal'
        self.runner(self.controller)
        self.assertEqual({x[1] for x in self.operations if x[2]=='normal'}, {11,22,33,44})

    def test_settings_only_pins_if_opted_in(self):
        self.controller.cfg['top_mode']='always'
        self.controller.cfg['pin_settings_above_game']=True
        self.runner(self.controller)
        self.assertIn(('set',44,'always'),self.operations)
        self.controller.cfg['pin_settings_above_game']=False
        self.operations.clear()
        self.runner(self.controller)
        self.assertIn(('set',44,'normal'),self.operations)

if __name__ == '__main__': unittest.main()
