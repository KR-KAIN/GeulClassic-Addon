"""Non-blocking, metadata-only live OCR stage profiling.

Never records OCR text, screenshots, image pixels, or translated messages.
Writes JSONL on a separate bounded thread so disk I/O does not block capture.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import threading
import time


def profile_path():
    local=os.environ.get('LOCALAPPDATA')
    base=Path(local) if local else (Path.home()/'.local'/'share')
    return base/'KAINMapleTranslator'/'diagnostics'/'OCR-STAGE-TRACE-EXPORT.jsonl'


class StageTraceWriter:
    def __init__(self, path=None, max_bytes=8_000_000):
        self.path=Path(path) if path is not None else profile_path()
        self.max_bytes=max_bytes
        self._queue=queue.Queue(maxsize=1024)
        self.dropped=0
        self._closed=False
        self._ready=threading.Event()
        self.open_error=None
        self._thread=threading.Thread(target=self._run,daemon=True,name='maple-ocr-stage-trace')
        self._thread.start()
        # File creation completes at startup (not after a first expensive OCR).
        # This wait is once per worker start, never inside the capture loop.
        self._ready.wait(timeout=1.5)

    def record(self, fields):
        if self._closed:return
        try:self._queue.put_nowait(dict(fields))
        except queue.Full:self.dropped+=1

    def _run(self):
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            if self.path.is_file() and self.path.stat().st_size>=self.max_bytes:
                self.path.replace(self.path.with_suffix('.previous.jsonl'))
            handle=self.path.open('a',encoding='utf-8',buffering=1)
        except OSError as exc:
            self.open_error=str(exc)
            self._ready.set()
            return  # Diagnostic I/O must never crash or slow the translator.
        self._ready.set()
        fp=handle
        try:
            while True:
                try:item=self._queue.get(timeout=.25)
                except queue.Empty:
                    if self._closed:return
                    continue
                if item is None:return
                try:
                    fp.write(json.dumps(item,ensure_ascii=False,separators=(',',':'))+'\n')
                    if fp.tell()>=self.max_bytes:
                        fp.close()
                        try:self.path.replace(self.path.with_suffix('.previous.jsonl'))
                        except OSError:pass
                        fp=self.path.open('w',encoding='utf-8',buffering=1)
                except (OSError,TypeError,ValueError):
                    # A bad diagnostic row is expendable, unlike chat history.
                    continue
        finally:
            fp.close()

    def close(self):
        self._closed=True
        try:self._queue.put_nowait(None)
        except queue.Full:
            # Daemon thread will exit once it drains and sees _closed.
            pass
        self._thread.join(timeout=1.0)
