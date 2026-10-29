"""Non-global Maple-relative stacking for the hunting tracker.

A normal Maple game window never requires HWND_TOPMOST on the tracker. The
tracker is inserted directly above Maple in the *normal* Z-order group. Other
applications therefore cover it normally. Only an explicitly pinned tracker,
or a real game HWND that itself has WS_EX_TOPMOST, uses a temporary topmost
promotion; that exceptional promotion is undone on loss of game focus.
"""
from __future__ import annotations
import sys
from functools import lru_cache
from .window_behavior import is_topmost, restore_below_foreground


def should_float_above_game(foreground_hwnd: int, game_hwnd: int, overlay_hwnd: int) -> bool:
    return bool(game_hwnd and overlay_hwnd and
                foreground_hwnd in (game_hwnd, overlay_hwnd))


class GameRelativeOverlay:
    # Native calls never move/resize/activate the window or reorder its owner.
    _FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0200

    def __init__(self):
        self._applied=False  # temporary TOPMOST only for topmost Maple windows
        self._target_hwnd=0
        self._last_foreground=None
        self._last_game_topmost=None

    @staticmethod
    @lru_cache(maxsize=1)
    def _user32():
        if sys.platform != 'win32':return None
        import ctypes
        from ctypes import wintypes
        u=ctypes.WinDLL('user32',use_last_error=True)
        u.GetForegroundWindow.restype=wintypes.HWND
        u.IsWindow.argtypes=[wintypes.HWND]
        u.IsWindow.restype=wintypes.BOOL
        u.IsIconic.argtypes=[wintypes.HWND]
        u.IsIconic.restype=wintypes.BOOL
        u.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,
                                 ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                                 wintypes.UINT]
        u.SetWindowPos.restype=wintypes.BOOL
        return u

    def is_game_window(self,hwnd):
        u=self._user32()
        return bool(u and hwnd and u.IsWindow(hwnd) and not u.IsIconic(hwnd))

    def _set_top(self,overlay_hwnd: int, enabled: bool, u=None) -> bool:
        u=u or self._user32()
        if u is None:return False
        from ctypes import wintypes
        target=wintypes.HWND(-1 if enabled else -2)
        return bool(u.SetWindowPos(wintypes.HWND(overlay_hwnd),target,
                                   0,0,0,0,self._FLAGS))

    def sync(self,widget,game_hwnd:int):
        u=self._user32()
        if u is None:return
        widget_hwnd=int(widget.winId())
        valid_game=bool(game_hwnd and u.IsWindow(game_hwnd) and not u.IsIconic(game_hwnd))
        foreground=int(u.GetForegroundWindow() or 0)
        game_hwnd=int(game_hwnd) if valid_game else 0
        active=should_float_above_game(foreground,game_hwnd,widget_hwnd)
        game_topmost=bool(valid_game and is_topmost(game_hwnd))

        # True fullscreen/topmost Maple requires a temporary topmost overlay.
        # NEVER promote for ordinary windowed Maple: that was the source of
        # the tracker blocking unrelated desktop applications.
        need_topmost=active and game_topmost
        if need_topmost != self._applied:
            if self._set_top(widget_hwnd,need_topmost,u):
                self._applied=need_topmost

        changed=(self._target_hwnd!=game_hwnd or
                 self._last_foreground!=foreground or
                 self._last_game_topmost!=game_topmost)
        if valid_game and not need_topmost and changed:
            # Normal HWND ordering: above Maple, but below another app that
            # Windows has brought into the foreground. Never grab focus.
            restore_below_foreground(widget_hwnd,game_hwnd)
        self._target_hwnd=game_hwnd
        self._last_foreground=foreground
        self._last_game_topmost=game_topmost

    def release(self,widget):
        if self._applied:
            try:
                if self._set_top(int(widget.winId()),False):
                    self._applied=False
            except (RuntimeError,TypeError,ValueError):
                self._applied=False
        self._target_hwnd=0
        self._last_foreground=None
        self._last_game_topmost=None
