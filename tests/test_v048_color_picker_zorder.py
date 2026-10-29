"""Regression: color selection must stay above the pinned settings overlay.

Uses the *actual method bodies* extracted from main.py with Windows/Qt fakes;
PySide6 is not required to test the z-order interactions on Linux.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'kain_maple_translator'/'main.py'


def extract(class_name, function_name, env):
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name==class_name)
    method=next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name==function_name)
    ns=dict(env)
    exec(compile(ast.Module(body=[method], type_ignores=[]),str(SOURCE),'exec'),ns)
    return ns[function_name]


class FakeColor:
    def __init__(self, value): self.value=value
    def isValid(self): return self.value.startswith('#') and len(self.value)==7
    def name(self): return self.value


class FakeInput:
    def __init__(self): self.value='#ff00aa'
    def text(self): return self.value
    def setText(self,val): self.value=val


class FakeColorDialog:
    ColorDialogOption=SimpleNamespace(DontUseNativeDialog='qt-nonnative')
    next_result=1
    fail_exec=False
    instance=None
    def __init__(self, initial, parent):
        self.initial=initial;self.parent=parent;self.actions=[]
        self._picked=FakeColor('#aabbcc')
        FakeColorDialog.instance=self
    def setWindowTitle(self,value): self.actions.append(('title',value))
    def setOption(self,*args): self.actions.append(('option',*args))
    def setWindowModality(self,v): self.actions.append(('modality',v))
    def setWindowFlag(self,*args): self.actions.append(('flag',*args))
    def show(self): self.actions.append(('show',))
    def raise_(self): self.actions.append(('raise',))
    def activateWindow(self): self.actions.append(('activate',))
    def exec(self):
        self.actions.append(('exec',))
        assert self.parent._color_picker_open
        if self.fail_exec: raise ValueError('mock picker failure')
        return self.next_result
    def selectedColor(self): return self._picked
    def close(self): self.actions.append(('close',))


class FakeSettings:
    def __init__(self):
        self.color_inputs={'nickname_color':FakeInput()}
        self._color_picker_open=False
        self._color_picker=None
        self.activations=[]
    def isVisible(self): return True
    def raise_(self): self.activations.append('raise')
    def activateWindow(self): self.activations.append('activate')


class ColorPicker048(unittest.TestCase):
    def setUp(self):
        self.runner=extract('SettingsDialog','choose_color',dict(
            QColor=FakeColor,QColorDialog=FakeColorDialog,
            QDialog=SimpleNamespace(DialogCode=SimpleNamespace(Accepted=1)),
            Qt=SimpleNamespace(WindowModality=SimpleNamespace(ApplicationModal='app-modal'),
                               WindowType=SimpleNamespace(WindowStaysOnTopHint='top'))))
        self.settings=FakeSettings()
        FakeColorDialog.next_result=1
        FakeColorDialog.fail_exec=False

    def test_native_dialog_is_not_used_and_picker_is_modal_and_topmost(self):
        self.runner(self.settings,'nickname_color')
        acts=FakeColorDialog.instance.actions
        self.assertIn(('option','qt-nonnative',True),acts)
        self.assertIn(('modality','app-modal'),acts)
        self.assertIn(('flag','top',True),acts)
        self.assertLess(acts.index(('show',)),acts.index(('raise',)))
        self.assertLess(acts.index(('raise',)),acts.index(('exec',)))
        self.assertTrue(FakeColorDialog.instance._kain_transient_dialog)
        self.assertEqual(self.settings.color_inputs['nickname_color'].text(),'#aabbcc')
        self.assertFalse(self.settings._color_picker_open)
        self.assertIsNone(self.settings._color_picker)
        self.assertEqual(self.settings.activations,['raise','activate'])

    def test_cancel_preserves_current_color(self):
        FakeColorDialog.next_result=0
        self.runner(self.settings,'nickname_color')
        self.assertEqual(self.settings.color_inputs['nickname_color'].text(),'#ff00aa')
        self.assertFalse(self.settings._color_picker_open)

    def test_exception_does_not_leave_stack_scheduler_frozen(self):
        FakeColorDialog.fail_exec=True
        with self.assertRaises(ValueError):self.runner(self.settings,'nickname_color')
        self.assertFalse(self.settings._color_picker_open)
        self.assertIsNone(self.settings._color_picker)
        self.assertIn(('close',),FakeColorDialog.instance.actions)

    def test_sync_stack_pauses_during_picker_and_ignores_transient_dialogs(self):
        from test_v043_stack_integration import FakeWindow, FakeDialog
        import os
        ops=[]
        context='game'
        normal=FakeDialog(40)
        modal=FakeDialog(41);modal._kain_transient_dialog=True
        FakeApp=SimpleNamespace(topLevelWidgets=lambda:[normal,modal])
        setstack=lambda hwnd,mode,**kw:ops.append((hwnd,mode))
        runner=extract('Controller','sync_stack',dict(
            QApplication=FakeApp,QDialog=FakeDialog,
            Z_ORDER_MODES=('always','game','normal'),
            foreground_context=lambda *args:context,
            is_topmost=lambda hwnd:True,
            set_native_stack=setstack,
            restore_below_foreground=lambda *a:ops.append(('restore',*a)),
            os=os))
        settings=SimpleNamespace(_color_picker_open=True)
        c=SimpleNamespace(closing=False,selector=None,cfg={'top_mode':'always',
                             'pin_settings_above_game':True},
                          game_hwnd=777,game_pid=888,chat=FakeWindow(1),
                          left=FakeWindow(2),right=FakeWindow(3),
                          _settings_dialog=settings,
                          _prior_stack_active=None,_last_stack_mode=None,
                          _last_foreground_context=None)
        runner(c)
        self.assertEqual(ops,[])
        settings._color_picker_open=False
        runner(c)
        self.assertIn((40,'always'),ops)
        self.assertNotIn((41,'always'),ops)

if __name__=='__main__':unittest.main()
