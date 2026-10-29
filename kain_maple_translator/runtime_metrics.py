"""Lightweight process CPU samples; optional Windows game-priority mode."""
import os
import sys
import threading
import time


class RuntimeMeter:
    def __init__(self):
        self.wall = time.monotonic()
        stamp = os.times()
        self.cpu = stamp.user+stamp.system
        self.last = {}

    def snapshot(self):
        now = time.monotonic()
        if now-self.wall >= .5:
            stamp = os.times()
            cpu = stamp.user+stamp.system
            percent = max(0,(cpu-self.cpu)/(now-self.wall)*100)
            self.last = {'process_cpu_core_pct':round(percent,1),
                         'process_cpu_machine_pct':round(percent/max(1,os.cpu_count() or 1),1),
                         'python_threads':threading.active_count()}
            self.wall,self.cpu = now,cpu
        return dict(self.last)


def set_game_priority(enabled):
    if sys.platform != 'win32':
        return False
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetCurrentProcess.restype=wintypes.HANDLE
    api.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    api.SetPriorityClass.restype=wintypes.BOOL
    # The user controls this setting; never elevate above ordinary priority.
    return bool(api.SetPriorityClass(api.GetCurrentProcess(),0x4000 if enabled else 0x20))
