"""Batch translation with one record per actual message, shared inference only."""
from __future__ import annotations
from collections import OrderedDict, deque
import threading
import time
from .timings import LatencyBook


class TranslationQueue:
    def __init__(self, translator, emit, report_error, max_pending=512, batch_size=8):
        self.translator = translator
        self.batch_size = max(1, int(batch_size))
        self.emit = emit
        self.report_error = report_error
        self.max_pending = max_pending
        self.condition = threading.Condition(threading.RLock())
        self.pending = OrderedDict()
        self.ready = deque()
        self.cache = OrderedDict()
        self.closed = False
        self.failed = 0
        self.completed = 0
        self.last_ms = 0.0
        self.book = LatencyBook()
        self.thread = threading.Thread(target=self._run, name='maple-translation-batches', daemon=True)
        self.thread.start()

    def submit(self, text: str, record: dict):
        # Preserve case and all digits: nickname/message identity is never the
        # cache key. Two players saying the same thing both receive a row.
        key = text.strip()
        with self.condition:
            if self.closed:
                return False
            if key in self.cache:
                value = self.cache[key]
                self.cache.move_to_end(key)
            elif sum(map(len, self.pending.values())) >= self.max_pending:
                self.failed += 1
                value = None
            elif key in self.pending:
                self.pending[key].append({**record, '_translation_queued_at': time.monotonic()})
                return True
            else:
                self.pending[key] = [{**record, '_translation_queued_at': time.monotonic()}]
                self.ready.append(key)
                self.condition.notify()
                return True
        if value is None:
            self.report_error('번역 대기열 과부하 · 원문을 표시합니다')
            self.emit({**record, 'translated': '[번역 대기 초과] '+key, 'translation_error': True})
            return False
        self.emit({**record, 'translated': value, 'translation_ms': 0.0})
        return True

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.ready)
                if self.closed:
                    return
                # Batch only already-available messages; no fixed latency tax.
                # CTranslate2 already runs up to 8 sentences per batch
                # (max_batch_size=8); taking only 3 made a burst of 8 chat
                # lines wait for three sequential model calls.
                keys = [self.ready.popleft() for _ in range(min(self.batch_size, len(self.ready)))]
            start = time.monotonic()
            try:
                values = self.translator.translate_many(keys, 'en-ko')
                if len(values) != len(keys):
                    raise RuntimeError('번역 결과 개수 불일치')
                errors = [None]*len(keys)
            except Exception:
                # Isolate a bad input/model batch: one failure cannot erase
                # the other seven messages. Retry each once individually.
                values, errors = [], []
                for key in keys:
                    try:
                        values.append(self.translator.translate(key, 'en-ko'))
                        errors.append(None)
                    except Exception as ex:
                        values.append('[번역 오류] '+key)
                        errors.append(str(ex))
            duration = round((time.monotonic()-start)*1000, 1)
            self.book.observe('translation_batch',duration)
            for key, value, error in zip(keys, values, errors):
                if not str(value).strip():
                    value, error = '[빈 번역 결과] '+key, '오프라인 모델의 빈 번역 결과'
                with self.condition:
                    records = self.pending.pop(key, [])
                    if self.closed:
                        return
                    self.last_ms = duration
                    if not error:
                        self.cache[key] = value
                        while len(self.cache) > 2048:
                            self.cache.popitem(last=False)
                        self.completed += len(records)
                    else:
                        self.failed += len(records)
                if error:
                    self.report_error('번역 실패 · 원문 보존: '+error)
                for record in records:
                    queued_at=record.pop('_translation_queued_at',None)
                    queue_ms=max(0.0,(start-queued_at)*1000) if queued_at is not None else 0.0
                    self.book.observe('translation_queue_wait',queue_ms)
                    self.emit({**record, 'translated': value, 'translation_ms': duration,
                               'translation_queue_wait_ms':round(queue_ms,1),
                               'translation_wait_ms': round((time.monotonic()-queued_at)*1000,1) if queued_at else duration,
                               'translation_error': bool(error)})

    def snapshot(self):
        with self.condition:
            return {**self.book.snapshot(), 'translation_pending': sum(map(len, self.pending.values())),
                    'translation_completed': self.completed, 'translation_errors': self.failed,
                    'translation_ms': self.last_ms}

    def close(self):
        with self.condition:
            self.closed = True
            self.pending.clear()
            self.ready.clear()
            self.condition.notify_all()
        if self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
