"""Windows.Graphics.Capture HWND source.  OCR always consumes the original BGR ROI.

The callback only copies pixels and never runs OCR or translation.  All Win32
imports are lazy so manual MSS still runs if WGC is not supported.  WGC uses a
window content frame, NOT a monitor screenshot or memory/packet hook.
"""
from __future__ import annotations
import ctypes
import queue
import sys
import threading
import time

import numpy as np


def visual_window_rect(hwnd: int) -> tuple[int,int,int,int]:
    """Bounds (x,y,w,h) of the outer visible game window, in physical pixels."""
    if sys.platform != 'win32':
        raise RuntimeError('WGC needs Windows')
    from ctypes import wintypes
    rc = wintypes.RECT()
    dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
    # DWMWA_EXTENDED_FRAME_BOUNDS=9: matches the visible DWM window border.
    api = dwm.DwmGetWindowAttribute
    api.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    api.restype = ctypes.c_long
    if api(hwnd, 9, ctypes.byref(rc), ctypes.sizeof(rc)) != 0:
        win = ctypes.WinDLL('user32', use_last_error=True)
        win.GetWindowRect.argtypes=[wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        win.GetWindowRect.restype=wintypes.BOOL
        if not win.GetWindowRect(hwnd, ctypes.byref(rc)):
            raise OSError('GetWindowRect failed')
    return (rc.left, rc.top, rc.right-rc.left, rc.bottom-rc.top)


def roi_frame_bounds(frame_shape, client_rect, outer_rect, region):
    """Map a screen-pixel chat rectangle to an HWND WGC window image.

    WGC can return just the client content or the decorated window, depending
    on DWM/window mode.  Compare dimensions before selecting the origin and
    reject geometries that would silently OCR the wrong part of the screen.
    """
    fh,fw = int(frame_shape[0]),int(frame_shape[1])
    if fw < 50 or fh < 25:
        raise ValueError('WGC frame too small')
    cx,cy,cw,ch = [int(x) for x in client_rect]
    ox,oy,ow,oh = [int(x) for x in outer_rect]
    rx,ry,rw,rh = [int(region[k]) for k in ('left','top','width','height')]
    if cw <= 0 or ch <= 0 or rw < 25 or rh < 15:
        raise ValueError('Invalid game/ROI geometry')
    # Never capture outside the actual game CLIENT rectangle.
    if (rx < cx-2 or ry < cy-2 or rx+rw > cx+cw+2 or ry+rh > cy+ch+2):
        raise ValueError('Chat ROI outside game client')
    def score(box):
        _,_,w,h = box
        return max(abs(fw-w)/max(1,w), abs(fh-h)/max(1,h))
    # Prefer true client coordinates on borderless fullscreen and client-only frames.
    anchor = client_rect if score(client_rect) <= score(outer_rect)+.004 else outer_rect
    ax,ay,aw,ah = anchor
    if aw<=0 or ah<=0:
        raise ValueError('WGC window size differs from game bounds')
    # WinRT can report scaled frame pixels for mixed-DPI windows.  Permit
    # uniform DPI scaling, but not an arbitrary crop from an unrelated frame.
    if score(anchor) > .15:
        client_sx,client_sy=fw/cw,fh/ch
        if not (0.80 <= client_sx <= 2.0 and abs(client_sx-client_sy) < .03):
            raise ValueError('WGC window size differs from game bounds')
        ax,ay,aw,ah=client_rect
    sx,sy=fw/aw,fh/ah
    x1=round((rx-ax)*sx);y1=round((ry-ay)*sy)
    x2=round((rx+rw-ax)*sx);y2=round((ry+rh-ay)*sy)
    # Allow a one-pixel DWM rounding error, but never a large off-window crop.
    if x1 < -2 or y1 < -2 or x2 > fw+2 or y2 > fh+2:
        raise ValueError('WGC ROI clipped by frame')
    x1=max(0,x1);y1=max(0,y1);x2=min(fw,x2);y2=min(fh,y2)
    if x2-x1 < 25 or y2-y1 < 15:
        raise ValueError('WGC ROI unexpectedly empty')
    return x1,y1,x2,y2


class WgcWindowSource:
    """Bounded callback-to-capture-thread handoff.  One HWND per instance."""
    def __init__(self, hwnd, client_rect, region, *, outer_rect=None,
                 capture_factory=None, max_pending=8, minimum_update_interval=33):
        self.hwnd=int(hwnd)
        self._geometry_lock=threading.Lock()
        outer=tuple(outer_rect) if outer_rect else visual_window_rect(self.hwnd)
        self._geometry=(tuple(client_rect),outer,dict(region))
        self.client_rect,self.outer_rect,self.region=self._geometry
        self.queue=queue.Queue(maxsize=max_pending)
        self.minimum_update_interval=int(minimum_update_interval)
        self._capture_factory=capture_factory
        self._control=None
        self._capture=None
        self._closed=threading.Event()
        self.error=None
        self.arrivals=0
        self.queue_overflows=0
        self.geometry_retries=0
        self.geometry_errors=0
        self.last_frame_at=0.0
        self.started_at=0.0

    def set_geometry(self, client_rect, region, outer_rect=None):
        # A complete snapshot prevents a frame from using a new client origin
        # together with an old ROI after the window is dragged or resized.
        if outer_rect is None:
            try:
                outer_rect=visual_window_rect(self.hwnd)
            except (OSError, RuntimeError):
                outer_rect=None
        with self._geometry_lock:
            if outer_rect is None:
                outer_rect=self._geometry[1]
            updated=(tuple(client_rect),tuple(outer_rect),dict(region))
            if updated == self._geometry:
                return
            self._geometry=updated
            self.client_rect,self.outer_rect,self.region=updated
            # Old callback pixels and the new screen-space ROI must not mix.
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break

    def start(self):
        if self._capture_factory is None:
            from windows_capture import WindowsCapture
            self._capture_factory=WindowsCapture
        capture=self._capture_factory(window_hwnd=self.hwnd, cursor_capture=False,
                                      draw_border=None, secondary_window=False,
                                      minimum_update_interval=self.minimum_update_interval)
        self._capture=capture
        self.started_at=time.monotonic()

        @capture.event
        def on_frame_arrived(frame, control):
            if self._closed.is_set():
                control.stop()
                return
            try:
                # BGRA WGC mapped buffer is only valid inside this callback.
                pixels=frame.frame_buffer
                with self._geometry_lock:
                    client_rect,outer_rect,region=self._geometry
                coords=roi_frame_bounds(pixels.shape, client_rect,
                                        outer_rect, region)
                x1,y1,x2,y2=coords
                crop=np.ascontiguousarray(pixels[y1:y2,x1:x2,:3])
                item=(crop, dict(region), time.monotonic())
                # Keep memory bounded.  This queue holds pixels only; there is
                # no long OCR work in the native capture callback.
                while True:
                    try:
                        self.queue.put_nowait(item)
                        break
                    except queue.Full:
                        self.queue.get_nowait()
                        self.queue_overflows+=1
                self.arrivals+=1
                self.geometry_retries=0
                self.last_frame_at=item[2]
            except ValueError as exc:
                # A window resize can briefly deliver a frame from the old
                # swapchain after GetClientRect has already updated. Drop that
                # stale frame, not the entire HWND capture session. Persistent
                # geometry errors remain fatal and will trigger MSS fallback.
                message=str(exc)
                if ('WGC window size differs' in message or
                        'WGC ROI clipped by frame' in message) and self.geometry_retries < 15:
                    self.geometry_retries+=1
                    self.geometry_errors+=1
                    return
                self.error=message
                self._closed.set()
                control.stop()
            except Exception as exc:
                self.error=str(exc)
                self._closed.set()
                control.stop()

        @capture.event
        def on_closed():
            self._closed.set()
        try:
            self._control=capture.start_free_threaded()
        except Exception:
            self._closed.set()
            raise

    def get(self, timeout=.05):
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def finished(self):
        if self._closed.is_set():
            return True
        if self._control is None:
            return False
        try:
            return bool(self._control.is_finished())
        except Exception:
            return True

    def close(self):
        self._closed.set()
        if self._control is not None:
            try:
                self._control.stop()
            except Exception:
                pass
        self._control=None
        self._capture=None
