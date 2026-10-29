"""Win32 window stacking for the Maple chat overlay.

Game-only mode is *not* a permanent system-wide always-on-top window.
It temporarily promotes UI into the topmost group when Maple or KAIN controls
have focus (works with most borderless-fullscreen game windows), and demotes
the UI when another app takes focus.  It does
not manipulate the Maple process or change the game window styles.
"""
from __future__ import annotations
import ctypes
import os
import sys

Z_ORDER_MODES = ('game', 'always', 'normal')
WDA_NONE = 0x00000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
HWND_TOP = 0
HWND_BOTTOM = 1
HWND_NOTOPMOST = -2
HWND_TOPMOST = -1
WS_EX_TOPMOST = 0x00000008
GW_HWNDPREV = 3


def capture_allowed(hwnd: int) -> bool:
    if sys.platform != 'win32' or not hwnd:
        return False
    try:
        from ctypes import wintypes
        api = ctypes.windll.user32.SetWindowDisplayAffinity
        api.argtypes = (wintypes.HWND, wintypes.DWORD)
        api.restype = wintypes.BOOL
        return bool(api(hwnd, WDA_NONE))
    except (AttributeError, OSError, ValueError):
        return False


def foreground_context(game_hwnd: int, game_pid: int, app_pid: int = 0) -> str:
    """One of 'game', 'controls', 'other'. Never mistake the game for our app.

    A KAIN setting dialog is in the same process as the controls; it must
    remain usable even when focus leaves the Maple executable.
    """
    if sys.platform != 'win32':
        return 'other'
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.argtypes = ()
        user32.GetForegroundWindow.restype = wintypes.HWND
        fg = user32.GetForegroundWindow()
        if not fg:
            return 'other'
        if game_hwnd and int(fg) == int(game_hwnd):
            return 'game'
        user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        if game_pid and int(pid.value) == int(game_pid):
            return 'game'
        if app_pid and int(pid.value) == int(app_pid):
            return 'controls'
    except (AttributeError, OSError, ValueError):
        return 'other'
    return 'other'


def foreground_is_game(game_hwnd: int, game_pid: int) -> bool:
    return foreground_context(game_hwnd, game_pid) == 'game'


def is_topmost(hwnd: int) -> bool:
    if sys.platform != 'win32' or not hwnd:
        return False
    try:
        from ctypes import wintypes
        api=ctypes.windll.user32.GetWindowLongW
        api.argtypes = (wintypes.HWND, ctypes.c_int)
        api.restype = ctypes.c_long
        return bool(api(hwnd, -20) & WS_EX_TOPMOST)
    except (AttributeError, OSError, ValueError):
        return False


def stack_target(mode: str, *, game_or_controls_active: bool = False,
                 game_topmost: bool = False) -> int | None:
    """Pure policy for the normal Windows Z-order (testable cross-platform)."""
    if mode not in Z_ORDER_MODES:
        raise ValueError(f'Invalid z-order mode: {mode}')
    if mode == 'always':
        return HWND_TOPMOST
    if mode == 'normal':
        return HWND_NOTOPMOST
    if game_or_controls_active:
        # Always raise above Maple, including games that are themselves
        # topmost and borderless fullscreen. The controller demotes our
        # windows when an unrelated application takes focus.
        return HWND_TOPMOST
    return None  # Do not steal the foreground from other apps.


def set_native_stack(hwnd: int, mode: str, *, game_foreground: bool = False,
                     game_topmost: bool = False) -> bool:
    """Place OUR window without stealing keyboard focus."""
    target=stack_target(mode,game_or_controls_active=game_foreground,
                        game_topmost=game_topmost)
    if target is None or sys.platform != 'win32' or not hwnd:
        return False
    try:
        from ctypes import wintypes
        win=ctypes.windll.user32.SetWindowPos
        win.argtypes=(wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                      ctypes.c_int,ctypes.c_int,wintypes.UINT)
        win.restype=wintypes.BOOL
        return bool(win(hwnd,target,0,0,0,0,
                         SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_NOOWNERZORDER))
    except (AttributeError,OSError,ValueError):
        return False


def restore_below_foreground(hwnd: int, game_hwnd: int = 0) -> bool:
    """Yield to unrelated apps without ever changing the game's own window.

    For a normal non-topmost Maple window, insert this KAIN window just
    above Maple. This keeps it below unrelated app windows that are above
    the game. If Maple itself is topmost, only remove our topmost flag:
    Windows cannot guarantee an order between topmost Maple and unrelated
    non-topmost apps without changing the game, which we intentionally avoid.
    """
    if sys.platform != 'win32' or not hwnd:
        return False
    try:
        from ctypes import wintypes
        user=ctypes.windll.user32
        setpos=user.SetWindowPos
        setpos.argtypes=(wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                         ctypes.c_int,ctypes.c_int,wintypes.UINT)
        setpos.restype=wintypes.BOOL
        flags=SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_NOOWNERZORDER
        # Demote only if currently topmost. Demoting every polling tick
        # unnecessarily brings a normal window in front of other apps.
        if is_topmost(hwnd):
            setpos(hwnd,HWND_NOTOPMOST,0,0,0,0,flags)
        if game_hwnd and not is_topmost(game_hwnd):
            getwindow=user.GetWindow
            getwindow.argtypes=(wintypes.HWND,wintypes.UINT)
            getwindow.restype=wintypes.HWND
            above=getwindow(game_hwnd,GW_HWNDPREV)
            if above and int(above) != int(hwnd):
                # The predecessor may be in the topmost group. Do not
                # accidentally turn our ordinary overlay topmost by using
                # such an HWND as the insertion point.
                target=HWND_NOTOPMOST if is_topmost(int(above)) else int(above)
                return bool(setpos(hwnd,target,0,0,0,0,flags))
        return True
    except (AttributeError,OSError,ValueError):
        return False
