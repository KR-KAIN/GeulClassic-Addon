"""Game window tracking via Win32 PID/HWND and real client origin.

Does not read game memory or inject code into the process. PID and executable
image are queried solely for selecting the correct top-level game window.
"""
from __future__ import annotations
from dataclasses import dataclass
import ctypes
import os
import sys
from pathlib import Path

@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    pid: int
    executable: str
    title: str
    rect: tuple[int, int, int, int]  # client in physical screen pixels

@dataclass(frozen=True)
class RelativeRegion:
    x: float
    y: float
    w: float
    h: float


def region_to_relative(game: tuple[int,int,int,int], region: dict) -> RelativeRegion:
    gx, gy, gw, gh = game
    if gw <= 0 or gh <= 0:
        raise ValueError('Invalid game rectangle')
    return RelativeRegion((region['left'] - gx)/gw, (region['top']-gy)/gh,
                          region['width']/gw, region['height']/gh)

def relative_to_region(game: tuple[int,int,int,int], relative: RelativeRegion | dict) -> dict:
    gx,gy,gw,gh=game
    if isinstance(relative,dict):
        r=RelativeRegion(**relative)
    else:
        r=relative
    w=max(50,round(r.w*gw)); h=max(25,round(r.h*gh))
    x=round(gx+r.x*gw); y=round(gy+r.y*gh)
    return {'left':x,'top':y,'width':min(w,gw),'height':min(h,gh)}


def find_maple_window(preferred_pid: int=0, preferred_hwnd: int=0, keyword: str='maple') -> GameWindow | None:
    if sys.platform != 'win32':
        return None
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user32.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]; user32.EnumWindows.restype=wintypes.BOOL
    user32.IsWindowVisible.argtypes=[wintypes.HWND]; user32.IsWindowVisible.restype=wintypes.BOOL
    user32.IsIconic.argtypes=[wintypes.HWND]; user32.IsIconic.restype=wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes=[wintypes.HWND]; user32.GetWindowTextLengthW.restype=ctypes.c_int
    user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int];user32.GetWindowTextW.restype=ctypes.c_int
    user32.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)];user32.GetClientRect.restype=wintypes.BOOL
    user32.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)];user32.ClientToScreen.restype=wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];user32.GetWindowThreadProcessId.restype=wintypes.DWORD
    kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel32.OpenProcess.restype=wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype=wintypes.BOOL
    kernel32.CloseHandle.argtypes=[wintypes.HANDLE];kernel32.CloseHandle.restype=wintypes.BOOL
    hits=[]
    key=(keyword or 'maple').lower()
    def callback(hwnd,_):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd): return True
        size=user32.GetWindowTextLengthW(hwnd)
        if size<1 or size>300:return True
        title_buf=ctypes.create_unicode_buffer(size+1)
        user32.GetWindowTextW(hwnd,title_buf,len(title_buf))
        title=title_buf.value
        pid=wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():return True
        handle=kernel32.OpenProcess(0x1000,False,pid.value)
        image=''
        if handle:
            try:
                buff=ctypes.create_unicode_buffer(32768)
                length=wintypes.DWORD(len(buff))
                if kernel32.QueryFullProcessImageNameW(handle,0,buff,ctypes.byref(length)):
                    image=buff.value
            finally:
                kernel32.CloseHandle(handle)
        base=Path(image).stem.lower()
        # Exclude launchers/browser windows with game-like tab titles.
        if not image or not (('maple' in base) or ('classic' in base and 'story' in title.lower())):
            return True
        if key not in title.lower() and 'maple' not in title.lower() and '메이플' not in title.lower():
            return True
        r=wintypes.RECT();p=wintypes.POINT(0,0)
        if not user32.GetClientRect(hwnd,ctypes.byref(r)) or not user32.ClientToScreen(hwnd,ctypes.byref(p)):
            return True
        w,h=int(r.right-r.left),int(r.bottom-r.top)
        if w < 550 or h < 350:return True
        cand=GameWindow(int(hwnd),int(pid.value),image,title,(int(p.x),int(p.y),w,h))
        score=w*h
        if preferred_pid and preferred_pid == cand.pid:score+=100_000_000
        if preferred_hwnd and preferred_hwnd == cand.hwnd:score+=200_000_000
        hits.append((score,cand))
        return True
    cb=callback_type(callback)
    user32.EnumWindows(cb,0)
    return max(hits,key=lambda item:item[0])[1] if hits else None
