"""Independent screen capture, incremental line OCR, and offline batches."""
from __future__ import annotations
import copy
from collections import deque
import logging
import threading
import time

from PySide6.QtCore import QThread, Signal

from .core import ChatFrameTracker, is_valid_region, should_translate_body
from .translation import Translator, prepare_models, warmup_models, engine_diagnostics
from .vision import TextRecognizer, red_announcement_regions, gray_blue_announcement_regions
from .fast_vision import IncrementalChatOCR
from .capture_stream import ChatCaptureStream, logical_capture_identity
from .translation_queue import TranslationQueue
from .row_admission import RowAdmission, classified_chat_rows
from .channel_guard import ChannelGuard
from .sliding_dedupe import SlidingChatDeduper
from .ttl_experiment import TTLTrial
from .visual_message_ledger import FrameMessageLedger
from .frame_context import inspect_scrollbar, without_scrollbar
from .runtime_metrics import RuntimeMeter, set_game_priority
from .timings import LatencyBook
from .stage_trace import StageTraceWriter

LOGGER = logging.getLogger(__name__)
# Oldest snapshot OCR may still start on when a newer one is waiting. The
# chat box keeps ~4 lines on screen for several seconds, so 2.5 s keeps
# overlapping snapshots while capping display delay (was 27 s median).
# Live R14-FIX1-M check: the worker always picks the oldest snapshot within
# this age, so consecutive snapshots end up one OCR duration apart whatever
# the limit is; a longer limit only adds delay (2.5 s gave 2.3 s median).
# R17 fast-chat check: 1.0 s still left frames waiting 0.77 s on average
# before OCR even started. The newest snapshot holds every line that is
# still visible, so a frame older than this is only extra delay.
LIVE_MAX_LAG_S = 0.4
_APPEARANCE = ('kind', 'prefix', 'tone', 'band_color', 'text_color', 'nickname_color', 'item_color')


def _glyph_dpi(hwnd):
    """Report actual Windows DPI when available; unknown is never guessed."""
    if not hwnd:
        return 'unknown'
    try:
        import ctypes
        return str(round(ctypes.windll.user32.GetDpiForWindow(int(hwnd))/96.0,4))
    except (AttributeError, OSError, ValueError, TypeError):
        return 'unknown'


class LiveWorker(QThread):
    translated = Signal(object)
    status = Signal(str)
    problem = Signal(str)
    inspection = Signal(object)

    def __init__(self, config: dict):
        super().__init__()
        self._config = copy.deepcopy(config)
        self._config_lock = threading.Lock()
        self._stop = threading.Event()
        self._chat_tracker = ChatFrameTracker()
        self._mega_tracker = ChatFrameTracker()
        self._sequence = 0
        self._session = time.monotonic_ns()
        self._translation_queue = None
        self._fast_translator = Translator(body_only=True)
        self._latency = LatencyBook()
        self._emitted_visual_ids=set()
        self._emitted_visual_order=deque()
        self._emitted_guard=threading.Lock()
        self._emitted_records_total=0
        self._visual_epoch=0

    def update_settings(self, config: dict) -> None:
        with self._config_lock:
            self._config = copy.deepcopy(config)

    def _settings(self):
        with self._config_lock:
            return copy.deepcopy(self._config)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        stream = None
        trace = None
        try:
            # Start diagnostics BEFORE model preparation: startup/model failures
            # must not prevent the requested JSONL file from being created.
            trace = StageTraceWriter()
            trace.record({'schema':2, 'event':'session_start',
                          'utc_unix_ms':round(time.time()*1000)})
            if trace.open_error:
                self.problem.emit('성능 로그 저장 실패: '+trace.open_error[:140])
            import cv2
            import numpy as np
            cv2.setNumThreads(1)
            self.status.emit('오프라인 EN↔KO 모델 확인 중…')
            prepare_models()
            self.status.emit('번역·OCR 모델 워밍업 중…')
            warmup_models(directions=('en-ko',))  # Incoming live chat first; KO->EN loads on first user request
            recognizer = TextRecognizer()
            dummy=np.full((32,200,3),255,dtype=np.uint8)
            cv2.putText(dummy,'KAIN 123',(5,23),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
            recognizer.ocr.recognize_txt([dummy])
            recognizer.korean_ocr.recognize_txt([dummy])
            recognizer.korean_link_ocr.recognize_txt([dummy])
            recognizer.ocr(dummy,use_det=True,use_cls=False,use_rec=True)
            incremental = IncrementalChatOCR(recognizer)
            incremental.glyph_debug.enabled=bool(self._settings().get('glyph_debug_enabled',False))
            incremental.glyph_dictionary_enabled=bool(self._settings().get('glyph_dictionary_enabled',False))
            trace.record({'schema':2, 'event':'ocr_ready',
                          'utc_unix_ms':round(time.time()*1000)})
            self._translation_queue = TranslationQueue(Translator(body_only=True), self._emit, self.problem.emit)
            stream = ChatCaptureStream(self._settings, self.problem.emit, capacity=48, max_lag_s=LIVE_MAX_LAG_S)
            stream.start()
            self.status.emit('채팅창 크기 유지 · 변경된 줄 우선 감지 · 일괄 번역 준비 완료')
            identity = None
            admission = RowAdmission()
            channel_guard = ChannelGuard()
            recent_dedupe = SlidingChatDeduper()
            visual_ledger = FrameMessageLedger()
            ttl_trial = TTLTrial.from_environment()
            trace.record({"schema": 2, "event": "ttl_trial_config",
                          "mode": ttl_trial.mode, "ttl_short_s": 2, "ttl_long_s": 15})
            bootstrap_pending=True
            bootstrap_events=set()
            bootstrap_epoch=None
            self._visual_epoch+=1
            last_report = 0.0
            last_overflows = 0
            last_overflow_report = -100.0
            last_inspection = -100.0
            last_delivered = time.monotonic()
            last_stall_warning = -100.0
            last_wait_status = time.monotonic()
            capture_events_at_delivery = 0
            captured_seen = 0
            emitted_recorded_at_previous_frame = 0
            ocr_rows_seen = 0
            newly_admitted = 0
            delivered_rows = 0
            browsing = False
            meter = RuntimeMeter()
            priority = None
            while not self._stop.is_set():
                cfg = self._settings()
                incremental.glyph_debug.enabled=bool(cfg.get('glyph_debug_enabled',False))
                incremental.glyph_dictionary_enabled=bool(cfg.get('glyph_dictionary_enabled',False))
                incremental.glyph_resolution=str(cfg.get('game_resolution','unknown'))
                incremental.glyph_dpi='unknown'
                desired_priority = bool(cfg.get('game_priority',False))
                if desired_priority != priority:
                    set_game_priority(desired_priority)
                    priority = desired_priority
                # Automatic WGC/MSS anchors need no user-drawn chat ROI.
                targets = ["chat"] if cfg['enabled'].get('chat') and (
                    cfg.get('auto_chat_region',False) or is_valid_region(cfg['regions'].get('chat'))) else []
                if not targets or cfg.get('ocr_paused'):
                    self._stop.wait(.1)
                    continue
                captured = stream.get()
                if captured is None:
                    if stream.stop_event.is_set():
                        raise RuntimeError('화면 캡처가 중단되었습니다 · OCR 진단 확인')
                    if cfg.get('auto_chat_region',True) and time.monotonic()-last_wait_status>5:
                        self.status.emit('메이플 게임 창 자동 연결 대기 · 게임 실행 및 창 표시 확인')
                        last_wait_status=time.monotonic()
                    continue
                region = captured.region
                # Discard obsolete coordinates after a user changes region.
                if not cfg.get('auto_chat_region',False) and region != cfg['regions']['chat']:
                    continue
                # Text rows use content identity, not the OS screen origin.
                # The Maple window may move without a new chat message.
                # When a HWND is known, keep history across WGC/MSS failover.
                current_id = logical_capture_identity(captured)
                if identity != current_id:
                    same_surface=(identity is not None and identity[:2]==current_id[:2])
                    identity = current_id
                    self._chat_tracker = ChatFrameTracker()
                    self._mega_tracker = ChatFrameTracker()
                    admission = RowAdmission()
                    channel_guard = ChannelGuard()
                    recent_dedupe = SlidingChatDeduper()
                    if not same_surface:
                        visual_ledger = FrameMessageLedger()
                        ttl_trial = TTLTrial.from_environment()
                        self._visual_epoch+=1
                    incremental = IncrementalChatOCR(recognizer)
                bgr = captured.image
                incremental.glyph_dictionary_enabled=bool(cfg.get('glyph_dictionary_enabled',False))
                incremental.glyph_debug.enabled=bool(cfg.get('glyph_debug_enabled',False))
                if incremental.glyph_dictionary_enabled:
                    incremental.glyph_resolution = str(cfg.get('game_resolution','unknown')) + f'|chat:{bgr.shape[1]}x{bgr.shape[0]}'
                    incremental.glyph_dpi = _glyph_dpi(captured.window_hwnd)
                try:
                    self._latency.observe('capture',captured.capture_ms)
                    started = time.monotonic()
                    frame_queue_wait_ms=max(0.,(started-(captured.queued_at or captured.captured_at))*1000)
                    context = inspect_scrollbar(bgr)
                    if context.at_bottom is False:
                        browsing = True
                        self.status.emit('게임 과거 채팅 탐색 중 · 신규 번역 대기')
                        self.inspection.emit({'region':dict(region),'raw':[],'parsed':[],
                            'metrics':{'source_scrollbar':'not_bottom',**meter.snapshot()}})
                        continue
                    resumed = browsing and context.at_bottom is True
                    if resumed:
                        browsing = False
                        self._chat_tracker = ChatFrameTracker()
                        self._mega_tracker = ChatFrameTracker()
                        admission = RowAdmission()
                        channel_guard = ChannelGuard()
                        recent_dedupe = SlidingChatDeduper()
                        visual_ledger = FrameMessageLedger()
                        ttl_trial = TTLTrial.from_environment()
                        self._visual_epoch+=1
                    bgr = without_scrollbar(bgr,context)
                    captured_seen += 1
                    lines = incremental.detect(bgr, int(region['left']), int(region['top']), float(cfg.get('ocr_scale', 1.8)))
                    after_detect=time.monotonic()
                    ocr_rows_seen += len(lines)
                    rows = classified_chat_rows(lines, bgr, int(region['left']), int(region['top']))
                    for row in rows:
                        x,y,w,h=row['rect']
                        # Track relative to the chat's bottom, independent of
                        # desktop origin and automatic ROI height changes.
                        row['_tracking_rect']=(x-int(region['left']),
                            y-int(region['top'])-int(region['height']),w,h)
                    admitted = admission.filter(rows, captured.captured_at)
                    newly_admitted += len(admitted)
                    # Admit full raw OCR history rather than just confirmed rows:
                    # otherwise the second OCR confirmation can look like a
                    # newly posted message or a flickering scroll replay.
                    ledger_suppressed_before = visual_ledger.suppressed
                    fresh = visual_ledger.filter(admitted, rows, captured.captured_at)
                    ledger_suppressed_this_frame = visual_ledger.suppressed - ledger_suppressed_before
                    if bootstrap_pending and rows:
                        bootstrap_events={r.get('_visual_event_id') for r in rows}
                        bootstrap_epoch=self._visual_epoch
                        bootstrap_pending=False
                    for row in fresh:
                        row['_startup_visible']=(self._visual_epoch==bootstrap_epoch and row.get('_visual_event_id') in bootstrap_events)
                    # R7 does not invoke recent_dedupe.filter at all. The R8
                    # experiment evaluates 2s and 15s on the very same fresh
                    # physical-message candidates. Default SHADOW changes no output.
                    trial_fresh, ttl_metrics = ttl_trial.evaluate(fresh, rows, captured.captured_at)
                    if resumed:
                        # Rebase visible history on return to the bottom. It is
                        # not a burst of new messages that should be replayed.
                        fresh = []
                        trial_fresh = []  # Preserve R7 no-replay contract after scrolling history.
                        self._chat_tracker.new([r for r in rows if r.get('kind','normal')=='normal'])
                        self._mega_tracker.new([r for r in rows if r.get('kind','normal')!='normal'])
                        recent_dedupe = SlidingChatDeduper()
                    guard_suppressed_this_frame = 0
                    delivered_this_frame = 0
                    for row in sorted(trial_fresh, key=lambda r: r['rect'][1]):
                        if not channel_guard.accept(row, captured.captured_at):
                            guard_suppressed_this_frame += 1
                            continue
                        delivered_this_frame += 1
                        delivered_rows += 1
                        last_delivered = time.monotonic()
                        capture_events_at_delivery = stream.events
                        body = row['body']
                        observed_at = row.get('first_observed_at', captured.captured_at)
                        from .uncertain_links import contains_uncertain_link, protect_uncertain_links
                        if contains_uncertain_link(body):
                            # Keep the source for diagnosis; never treat broken
                            # brackets/CJK OCR artifacts as verified item names.
                            safe_body = protect_uncertain_links(body)
                            record = self._record('chat', body, row['rect'], row['nickname'], row, observed_at)
                            record['item_ocr_uncertain'] = True
                            if should_translate_body(safe_body, row['confidence']):
                                self._queue('chat', safe_body, row['rect'], cfg, row['nickname'],
                                            row, observed_at, record=record)
                            else:
                                self._emit({**record, 'translated': safe_body, 'translation_ms': 0.0})
                        elif should_translate_body(body, row['confidence']):
                            self._queue('chat', body, row['rect'], cfg, row['nickname'], row, observed_at)
                        else:
                            # Already-admitted chat must not disappear simply
                            # because the language gate rejects punctuation,
                            # a short reply or a mixed-language sentence.
                            record = self._record('chat', body, row['rect'], row['nickname'], row, observed_at)
                            self._emit({**record, 'translated': body, 'translation_ms': 0.0})
                    with self._emitted_guard:
                        emitted_records_total=self._emitted_records_total
                    emitted_records_delta=max(0,emitted_records_total-emitted_recorded_at_previous_frame)
                    emitted_recorded_at_previous_frame=emitted_records_total
                    worker_post_ms=(time.monotonic()-after_detect)*1000
                    stage_post_total_ms=incremental.stats.get('stage_post_ms',0)+worker_post_ms
                    stats = {**incremental.stats, **self._translation_queue.snapshot(),
                             **self._latency.snapshot(), **meter.snapshot(),
                             **engine_diagnostics(),
                             'source_scrollbar': 'bottom' if context.at_bottom is True else 'unknown',
                             'trade_template_hits':self._fast_translator.trade_memory.hits,
                             'trade_templates_compiled':self._fast_translator.trade_memory.compiled,
                             'frame_age_ms': round((started-captured.captured_at)*1000, 1),
                             'stage_cap_ms':round(captured.capture_ms,2),
                             'stage_queue_wait_ms':round(frame_queue_wait_ms,2),
                             'stage_post_worker_ms':round(worker_post_ms,2),
                             'stage_post_pipeline_ms':round(stage_post_total_ms,2),
                             'profile_trace_path':str(trace.path) if trace else '',
                             'profile_trace_drops':trace.dropped if trace else 0,
                             'capture_backlog': stream.frames.qsize(), 'capture_overflows': stream.overflows,
                             'capture_stale_drops':stream.stale_drops,
                             'capture_expired_drops':stream.expired_drops, 'capture_lag_drops':stream.lag_drops,
                             'capture_covered_frames':stream.covered_frames,
                             'capture_signature_ms':stream.signature_ms,
                             'capture_signature_rows':stream.signature_rows,
                             'capture_signature_uncertain_frames':stream.signature_uncertain_frames,
                             'capture_interval_ms':stream.capture_interval_ms,
                             'sliding_duplicates_suppressed': visual_ledger.suppressed,
                             **ttl_metrics,
                             'ttl_guard_suppressed': guard_suppressed_this_frame,
                             'ttl_delivered_to_output': delivered_this_frame,
                             'ttl_output_emitted_total':emitted_records_total,
                             'ttl_output_emitted_delta':emitted_records_delta,
                             'ttl_visual_ledger_suppressed_total':visual_ledger.suppressed,
                             'ttl_visual_ledger_suppressed':ledger_suppressed_this_frame,
                             'capture_backlog_delay_ms': round(max(0.0,(time.monotonic()-captured.captured_at)*1000),1),
                             'capture_backend':stream.active_backend,
                             'capture_game_hwnd':captured.window_hwnd,
                             'capture_backend_note':stream.backend_note,
                             'auto_chat_region':dict(stream.auto_region) if stream.auto_region else None,
                             'auto_chat_method':stream.auto_method,
                             'auto_chat_confidence':stream.auto_confidence,
                             'auto_ui_scale':stream.auto_scale,
                             'auto_chat_game_size':list(stream.auto_size) if stream.auto_size else None,
                             'wgc_frames':stream.wgc_arrivals,
                             'wgc_dropped_previews':stream.wgc_queue_overflows}
                    stats.update(general_confirmation_pending=admission.pending,
                                 general_low_confidence_rejections=admission.rejected,
                                 rows_classified=len(rows),rows_admitted=len(admitted),
                                 rows_unique_new=len(fresh),rows_processed_total=delivered_rows)
                    if trace is not None:
                        # All entries are numeric measurements and geometry only.
                        # No OCR text, player names, game images, or private content.
                        selected=('stage_pre_ms','stage_ocr_ms','stage_post_ms','stage_post_worker_ms',
                                  'stage_post_pipeline_ms','stage_total_ms','stage_recovery_detector_ms',
                                  'ocr_ms','primary_ms','retry_ms','korean_ms','item_ocr_ms',
                                  'segmentation_ms','recovery_ms','badge_ms','recognition_batches',
                                  'recognition_inputs','retry_rows','korean_rows','item_ocr_inputs',
                                  'item_ocr_batches','ink_rows','new_rows','cache_hits','near_cache_hits',
                                  'detector_recoveries','ocr_cached_frame',
                                  'recovery_reasons','recovery_rows_found',
                                  'recovery_gate_blocked','recovery_cache_hit',
                                  'recovery_gate_block_reason','capture_expired_drops','capture_covered_frames',
                                  'capture_signature_ms','capture_signature_rows','capture_signature_uncertain_frames',
                                  'capture_interval_ms',
                                  'ttl_trial_mode','ttl_candidates','ttl_short_allowed','ttl_long_allowed',
                                  'ttl_extra_blocked','ttl_actual_blocked','ttl_visual_new_blocked',
                                  'ttl_total_candidates','ttl_total_short_allowed','ttl_total_long_allowed',
                                  'ttl_total_extra_blocked','ttl_total_actual_blocked',
                                  'ttl_short_skipped_total','ttl_long_skipped_total',
                                  'ttl_visual_ledger_suppressed','ttl_guard_suppressed','ttl_delivered_to_output',
                                  'ttl_output_emitted_total','ttl_output_emitted_delta',
                                  'ttl_visual_ledger_suppressed_total',
                                  'border_retry_used','rows_classified','rows_admitted',
                                  'rows_unique_new','rows_processed_total',
                                  'general_confirmation_pending','general_low_confidence_rejections',
                                  'glyph_debug_split_match_ratio','glyph_debug_split_failure_ratio','glyph_debug_saved_lines',
                                  'glyph_hit_rate','glyph_lines_resolved','glyph_lines_fallback','glyph_unknown_chars',
                                  'glyph_dict_size','glyph_at_only_skipped','glyph_shadow_compared',
                                  'glyph_shadow_mismatch','glyph_shadow_pairs','glyph_shadow_mismatch_rate',
                                  'glyph_profile_resolution','glyph_profile_dpi','glyph_profile_row_height','glyph_profile_ink_color',
                                  'glyph_profile_colors_by_kind',
                                  'input_width_px','input_height_px','input_bytes',
                                  'rec_input_max_width_px','rec_input_max_height_px',
                                  'rec_input_total_pixels',
                                  'korean_input_max_width_px','korean_input_max_height_px',
                                  'korean_input_total_pixels',
                                  'item_input_max_width_px','item_input_max_height_px','item_input_total_pixels',
                                  'detector_input_max_width_px','detector_input_max_height_px',
                                  'detector_input_total_pixels','detector_calls',
                                  'translation_pending','translation_queue_wait_p95_ms')
                        entry={key:stats.get(key,0) for key in selected}
                        entry.update(schema=1,utc_unix_ms=round(time.time()*1000),
                                     cap_ms=round(captured.capture_ms,2),
                                     pre_ms=stats.get('stage_pre_ms',0),
                                     ocr_model_path_ms=stats.get('stage_ocr_ms',0),
                                     post_ms=round(stage_post_total_ms,2),
                                     queue_wait_ms=round(frame_queue_wait_ms,2),
                                     capture_to_ocr_ms=round((started-captured.captured_at)*1000,2),
                                     backend=stream.active_backend,
                                     capture_queued_frames=stream.frames.qsize(),
                                     capture_stale_drops=stream.stale_drops,
                                     trace_dropped=trace.dropped)
                        trace.record(entry)
                    stats.update(capture_events=stream.events,
                                 capture_refreshes=stream.refreshes,
                                 capture_skipped_refreshes=stream.skipped_refreshes,
                                 frames_inspected=captured_seen,
                                 total_ocr_lines=ocr_rows_seen,
                                 admitted_rows=newly_admitted,
                                 delivered_rows=delivered_rows,
                                 seconds_since_delivery=round(time.monotonic()-last_delivered,1))
                    report_now = time.monotonic()
                    # Continuous UI signal delivery can itself delay OCR processing.
                    # Diagnostics stay frequent, but are not emitted per frame.
                    if report_now-last_inspection >= .35:
                        red_candidates = len(red_announcement_regions(bgr))
                        self.inspection.emit({'region': dict(region),
                            'red_candidates': red_candidates,
                            'gray_candidates': len(gray_blue_announcement_regions(bgr)),
                            'raw': [line.text for line in lines[:35]],
                            'parsed': [f"{row['nickname']} : {row['body']}" for row in rows[:30]],
                            'metrics': stats})
                        last_inspection = report_now
                    # An active OCR stream with no delivered messages is
                    # diagnostically distinct from a completely stopped capture.
                    if (len(rows) >= 2 and stream.events-capture_events_at_delivery >= 8
                            and report_now-last_delivered > 20
                            and report_now-last_stall_warning > 30):
                        LOGGER.warning('Potential chat output stall: %s',
                            {k: stats[k] for k in ('frames_inspected','total_ocr_lines',
                                'admitted_rows','delivered_rows','capture_backlog')})
                        last_stall_warning=report_now
                    if stream.overflows > last_overflows and report_now-last_overflow_report >= 5:
                        last_overflows = stream.overflows
                        last_overflow_report = report_now
                        self.problem.emit(f'화면 변경 보관 한도 초과 ({last_overflows}프레임) · 채팅 누락 가능성 확인 필요')
                    if time.monotonic()-last_report > 2.5:
                        auto_label=''
                        if cfg.get('auto_chat_region',True):
                            auto_label=(' · 채팅 위치 자동 탐지' if 'visual' in stream.auto_method
                                       else ' · 채팅 위치 자동 추정(확인 권장)')
                        if rows:
                            # Put measured backlog first: compact controls show
                            # only the first 42 characters, with the full detail
                            # available in the tooltip. Model time alone can
                            # look fast while the displayed chat is seconds old.
                            if frame_queue_wait_ms>=500:
                                self.status.emit(f"화면 대기 {frame_queue_wait_ms/1000:.1f}초 ({stream.frames.qsize()}장) · OCR {stats['ocr_ms']}ms · 번역 대기 {stats['translation_pending']}")
                            else:
                                self.status.emit(f"캡처 {stream.active_backend.upper()}{auto_label} · 채팅 {len(rows)}줄 · OCR {stats['ocr_ms']}ms · 재사용 {stats['cache_hits']}줄 · 번역 대기 {stats['translation_pending']}")
                        else:
                            self.status.emit('캡처 '+stream.active_backend.upper()+auto_label+' · 채팅 미검출 · OCR 진단 확인')
                        last_report = time.monotonic()
                except Exception as ex:
                    LOGGER.exception('Chat OCR scan failure')
                    self.problem.emit('chat 인식 오류: '+str(ex))
                    self._stop.wait(.1)
        except Exception as ex:
            LOGGER.exception('OCR worker failed')
            if trace is not None:
                trace.record({'schema':2, 'event':'worker_error',
                              'utc_unix_ms':round(time.time()*1000),
                              'error_type':type(ex).__name__})
            self.problem.emit('OCR 초기화 오류: '+str(ex))
        finally:
            if trace is not None:
                trace.record({'schema':2, 'event':'session_end',
                              'utc_unix_ms':round(time.time()*1000)})
                trace.close()
            if stream is not None:
                stream.close()
            if self._translation_queue is not None:
                self._translation_queue.close()
            self.status.emit('인식 중지됨')

    def _emit(self, record):
        if not self._stop.is_set():
            # A completed fast translation and an asynchronous retry must
            # never render the same physical on-screen event twice.
            event=record.get('visual_event_id')
            if event is not None:
                with self._emitted_guard:
                    if event in self._emitted_visual_ids:return
                    self._emitted_visual_ids.add(event)
                    self._emitted_visual_order.append(event)
                    if len(self._emitted_visual_order)>4096:
                        stale=self._emitted_visual_order.popleft()
                        self._emitted_visual_ids.discard(stale)
            order=record.get('order')
            if order:
                self._latency.observe('capture_to_emit',(time.monotonic()-order[0])*1000)
            with self._emitted_guard:
                self._emitted_records_total+=1
            self.translated.emit(record)

    def _record(self, zone, source, rect, nickname, appearance, captured_at=None):
        self._sequence += 1
        return {'zone': zone, 'original': source, 'nickname': nickname, 'rect': rect,
                'fresh': True, 'message_id': f'{self._session}-{self._sequence}',
                'order': (captured_at or time.monotonic(), self._sequence),
                'captured_unix':time.time()-max(0.,time.monotonic()-(captured_at or time.monotonic())),
                'visual_session':self._session,
                'startup_visible':bool((appearance or {}).get('_startup_visible')),
                'source_ink':(appearance or {}).get('visual_key',''),
                'source_local_rect':(appearance or {}).get('_tracking_rect'),
                'visual_event_id': ((self._visual_epoch, (appearance or {}).get('_visual_event_id'))
                                    if (appearance or {}).get('_visual_event_id') is not None else None),
                **{key: (appearance or {}).get(key, '') for key in _APPEARANCE}}

    def _queue(self, zone, text, rect, cfg, nickname='', appearance=None, captured_at=None, record=None):
        source = text.strip()
        if record is None:
            record = self._record(zone, source, rect, nickname, appearance, captured_at)
        try:
            result = self._fast_translator.translate_fast(source, 'en-ko')
        except Exception as ex:
            LOGGER.warning('Fast rule planning failed; using normal translation: %s', ex)
            result = None
        if result is not None:
            self._emit({**record, 'translated': result, 'translation_ms': 0.0})
        else:
            self._translation_queue.submit(source, record)
