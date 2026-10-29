"""Short-interval screen capture with bounded, observable frame history."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from collections import OrderedDict
import queue
import threading
import time

import numpy as np

from .core import is_valid_region


@dataclass
class CapturedChat:
    image: np.ndarray
    region: dict
    captured_at: float
    capture_ms: float = 0.0
    changed: bool = True  # periodic confirmations must not evict actual changes
    source: str = "mss"
    window_hwnd: int = 0  # HWND of the game client, 0 for manual screen ROI
    queued_at: float = 0.0  # when this frame entered the capture -> OCR queue
    row_signature: tuple = ()  # exact foreground rows; empty when segmentation is uncertain


def logical_capture_identity(frame: CapturedChat) -> tuple:
    """Stable chat-history identity for the same Maple HWND/ROI size.

    Screen x/y changes due to moving the game window do not mean new text.
    WGC -> MSS fallback also preserves text-overlap context for one HWND.
    Different windows or dimensions still reset the OCR tracking pipeline.
    """
    w=int(frame.region['width']);h=int(frame.region['height'])
    if frame.window_hwnd:
        return ('hwnd', int(frame.window_hwnd), w, h)
    return ('screen',frame.source,w,h)


def covered_middle_frame(before, middle, after):
    """Drop a snapshot only if neighbouring snapshots retain every row.

    Require ordered scrolling overlap, full-resolution exact ink and matching
    capture geometry. Ambiguous repeated rows and uncertain segmentation keep
    their frames. No elapsed-time test can authorize dropping changed text.
    """
    a,b,c = before.row_signature, middle.row_signature, after.row_signature
    if not a or not b or not c or any(len(set(s)) != len(s) for s in (a,b,c)):
        return False
    if not (logical_capture_identity(before) == logical_capture_identity(middle)
            == logical_capture_identity(after)):
        return False
    def overlap(x,y):
        return next((n for n in range(min(len(x),len(y)),0,-1) if x[-n:] == y[:n]),0)
    left,right = overlap(a,b),overlap(b,c)
    return left > 0 and right > 0 and left+right >= len(b)


def _glyphs_alike(first, second):
    """Loose same-text test used ONLY to decide whether to enqueue a frame.

    Maple chat never edits a line in place: new text scrolls every row, so a
    frame whose rows all keep their position and glyph shape (within 1px,
    ignoring scattered edge flicker from scenery behind the text) shows no
    new message. Frames are never dropped on this basis; see row_signature.
    """
    import cv2
    from .fast_vision import aligned_masks
    pair = aligned_masks(first, second, slack=2)
    if pair is None:
        return False
    a, b, _ = pair
    kernel = np.ones((3, 3), np.uint8)
    near_a = cv2.dilate(a.astype(np.uint8), kernel).astype(bool)
    near_b = cv2.dilate(b.astype(np.uint8), kernel).astype(bool)
    stray = int(np.count_nonzero(a & ~near_b)) + int(np.count_nonzero(b & ~near_a))
    return stray <= max(4, int(min(first[2], second[2]) * .03))


class ChangeDetector:
    """Decide whether a captured chat frame shows different TEXT rows.

    Moving scenery behind translucent or outlined chat changes many pixels
    while the text is unchanged. Comparing glyph masks row by row (instead of
    exact hashes or raw pixel change) stops animated backgrounds from flooding
    the OCR queue with identical text, which built up seconds of backlog.
    The scrollbar is removed first, exactly as the OCR worker does: left in
    place its rail joins every baseline and segmentation was always uncertain.
    ``row_signature`` (used to drop fully covered scroll snapshots) still uses
    strict identities: only exact or edge-flicker-identical rows match there.
    """
    def __init__(self, registry_size=96):
        self.previous = None
        self.previous_ink = None
        self.registry = OrderedDict()
        self.registry_size = int(registry_size)
        self.next_id = 0

    def _row_id(self, signature, tone):
        from .fast_vision import near_identical_ink
        for rid in reversed(self.registry):
            other, other_tone = self.registry[rid]
            if other_tone == tone and near_identical_ink(signature, other):
                self.registry.move_to_end(rid)
                return rid
        self.next_id += 1
        self.registry[self.next_id] = (signature, tone)
        while len(self.registry) > self.registry_size:
            self.registry.popitem(last=False)
        return self.next_id

    @staticmethod
    def _same_text(rows, previous):
        if len(rows) != len(previous) or not rows:
            return False
        for (sig, tone, y, h, _), (old, old_tone, old_y, old_h, _) in zip(rows, previous):
            if tone != old_tone or abs(y-old_y) > 2 or abs(h-old_h) > 2:
                return False
            if sig is None or old is None:
                return False
            if not _glyphs_alike(sig, old):
                return False
        return True

    def observe(self, bgr):
        """Return (changed, row_signature) for one captured frame."""
        import cv2
        from . import fast_vision
        from .frame_context import inspect_scrollbar, without_scrollbar
        from .megaphone import detect_band
        thumb = bgr if bgr.shape[1] <= 800 else cv2.resize(
            bgr, (800, max(1, round(bgr.shape[0]*800/bgr.shape[1]))))
        identical = (self.previous is not None and self.previous.shape == thumb.shape
                     and np.array_equal(self.previous, thumb))
        if identical and self.previous_ink is not None:
            rows, uncertain, bright = self.previous_ink
        else:
            clean = without_scrollbar(bgr, inspect_scrollbar(bgr))
            first = fast_vision.ink_rows(clean)
            segments, uncertain, bright = fast_vision.ink_rows_border_retry(clean, first=first)
            rows = []
            for row in segments:
                tone = detect_band(clean, row.rect).tone
                signature = fast_vision.ink_signature(row.neutral)
                if signature is None:
                    rid = ('exact', hashlib.blake2b(
                        (row.neutral[:, :, 0] < 170).tobytes()+str(row.neutral.shape).encode(),
                        digest_size=12).digest())
                else:
                    rid = self._row_id(signature, tone)
                rows.append((signature, tone, int(row.rect[1]), int(row.rect[3]), rid))
        pixel_change = 1.0
        if self.previous is not None and self.previous.shape == thumb.shape:
            pixel_change = float(np.mean(np.max(cv2.absdiff(thumb, self.previous), axis=2) > 18))
        if self.previous_ink is None:
            changed = True
        elif rows and self.previous_ink[0]:
            changed = not self._same_text(rows, self.previous_ink[0])
            if uncertain:
                changed = changed or (len(rows) < 2 and pixel_change > .06)
        else:
            changed = bool(rows) != bool(self.previous_ink[0]) or pixel_change > .06
        self.previous = thumb.copy()
        self.previous_ink = (rows, uncertain, bright)
        # Uncertain segmentation (including bright-glyph rescue rows) never
        # authorizes dropping a snapshot: the R14 17:40 recording showed a
        # wrong 2-row split on such a frame. The live lag limit already
        # bounds the backlog, so compaction is not needed for speed.
        trusted = not uncertain
        return changed, (tuple((row[4], row[1]) for row in rows) if trusted else ())


class ChatCaptureStream:
    def __init__(self, settings, report_error, capacity=48, max_age_s=None, max_lag_s=None):
        self.settings = settings
        self.report_error = report_error
        self.frames = queue.Queue(maxsize=capacity)
        self.max_frames = capacity
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name='maple-chat-capture', daemon=True)
        self.overflows = 0
        self.stale_drops = 0  # Adaptive lag recovery, distinct from capacity overflows
        # Optional live-worker safety limit. Test/replay streams retain historic
        # timestamps unless explicitly opted into real-time age-based expiry.
        self.max_age_s = None if max_age_s is None else float(max_age_s)
        # Live catch-up limit (R13). Real 1080p footage: OCR ran ~0.8 frames/s
        # while changed frames kept arriving, so a FIFO of 48 made every chat
        # line 27 s late (p90 57 s) and still overflowed. Skip only snapshots
        # older than this when a newer one is already waiting, keeping the
        # OLDEST fresh one so consecutive OCR snapshots still overlap.
        self.max_lag_s = None if max_lag_s is None else float(max_lag_s)
        self.lag_drops = 0
        self.expired_drops = 0
        self.skipped_refreshes = 0
        self.covered_frames = 0
        self.events = 0
        self.refreshes = 0
        self.signature_uncertain_frames = 0
        self.signature_rows = 0
        self.signature_ms = 0.0
        self.capture_interval_ms = 80
        self.active_backend = "mss"
        self.backend_note = ""
        self.wgc_arrivals = 0
        self.wgc_queue_overflows = 0
        self.auto_region = None
        self.auto_method = 'waiting'
        self.auto_confidence = 0.0
        # Text-change analysis costs ~70 ms per frame on a busy streaming PC
        # (i7-7700 at 99% CPU with game+OBS), i.e. a whole core at 15/s,
        # while OCR handles ~1 frame/s. Chat rows stay visible for seconds,
        # so 5 analyses per second keep every row and free CPU for OCR.
        self.wgc_min_interval = .2

    def start(self):
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def publish(self, frame: CapturedChat):
        # Refresh-only frames are useful when idle (they confirm that a
        # partially recognised row persisted), but never delay a queued
        # *change*. Preserve every event frame as long as the bounded queue
        # allows: the game may show only four lines before they scroll away.
        if not frame.changed and not self.frames.empty():
            self.skipped_refreshes += 1
            return False
        while True:
            try:
                frame.queued_at = time.monotonic()
                self.frames.put_nowait(frame)
                self._compact_covered()
                if frame.changed:
                    self.events += 1
                else:
                    self.refreshes += 1
                return True
            except queue.Full:
                # Capacity may shrink when a larger capture region is chosen.
                # Drain enough old frames instead of raising a second Full.
                try:
                    self.frames.get_nowait()
                    self.overflows += 1
                except queue.Empty:
                    pass

    def _compact_covered(self):
        # Publish/get share Queue's mutex; never race a consumer while
        # removing an interior frame. The first and last frame always stay.
        with self.frames.mutex:
            pending = self.frames.queue
            i = 1
            while i < len(pending)-1:
                if covered_middle_frame(pending[i-1],pending[i],pending[i+1]):
                    del pending[i]
                    self.frames.unfinished_tasks -= 1
                    self.covered_frames += 1
                    self.frames.not_full.notify()
                    i = max(1,i-1)
                else:
                    i += 1

    def get(self, timeout=.15):
        try:
            frame = self.frames.get(timeout=timeout)
        except queue.Empty:
            return None
        # A four-line chat viewport is a rolling snapshot: when the OCR model
        # cannot keep up with incoming changed frames, working through 10+ old
        # snapshots delays every NEW message. Preserve the newest five changed
        # snapshots, which maintain the short scrolling history, and report how
        # many old intermediates were dropped. Do not alter small test queues.
        # Explicit legacy latency-only mode. Live R11 preserves changed
        # frames in acquisition order: newer pixels cannot prove that an
        # older four-line viewport contained no unique message.
        if self.max_age_s is not None and self.frames.qsize() >= 7:
            while self.frames.qsize() > 4:
                try:
                    frame = self.frames.get_nowait()
                    self.stale_drops += 1
                except queue.Empty:
                    break
        if self.max_age_s is not None:
            # A stale OCR input creates late, misleading chat. Process newest
            # available snapshot only if recent; do NOT assert that skipped
            # frames had no one-off messages. Record each drop for diagnostics.
            while frame is not None:
                # Age starts at acquisition, not queue insertion; a WGC
                # callback can enqueue an already obsolete screenshot.
                acquired = frame.captured_at if frame.captured_at > 0 else frame.queued_at
                if time.monotonic() - acquired <= self.max_age_s:
                    break
                # If the producer is momentarily stalled, the only remaining
                # frame may be older than 400ms. Reading it is better than
                # reporting no chat at all. Only discard an obsolete snapshot
                # if a newer frame is already available to replace it.
                try:
                    newer = self.frames.get_nowait()
                except queue.Empty:
                    break
                self.expired_drops += 1
                frame = newer
        if self.max_lag_s is not None:
            while frame is not None:
                acquired = frame.captured_at if frame.captured_at > 0 else frame.queued_at
                if time.monotonic() - acquired <= self.max_lag_s:
                    break
                try:
                    newer = self.frames.get_nowait()
                except queue.Empty:
                    break  # never go silent: the last frame is still read
                self.lag_drops += 1
                frame = newer
        return frame

    def _run(self):
        # WGC delivers HWND frames asynchronously.  MSS remains a complete
        # independent fallback if WGC is disabled, missing or incompatible.
        source = None
        source_hwnd = 0
        retry_wgc_after = 0.0
        last_probe = 0.0
        identity = None
        detector = None
        identity_changed = False
        last_analysed = float('-inf')
        last_publish = 0.0
        last_frame = None
        auto_hwnd = 0
        auto_relative = None
        game_rect_last = None
        game_for_fallback = None
        last_known_hwnd = 0
        try:
            import mss
            import cv2
            from .game_window import find_maple_window, region_to_relative, relative_to_region
            from .auto_chat_detect import detect_chat_region, estimate, local_crop
            from .layout import estimate_chat_area
            with mss.mss() as screenshotter:
                while not self.stop_event.is_set():
                    started=time.monotonic()
                    cfg=self.settings()
                    region=cfg.get('regions',{}).get('chat')
                    automatic=bool(cfg.get('auto_chat_region',False))
                    enabled=(not cfg.get('ocr_paused') and cfg.get('enabled',{}).get('chat')
                             and (automatic or is_valid_region(region)))
                    mode=cfg.get('capture_backend','wgc')
                    if mode not in ('wgc','mss'):
                        mode='mss'
                    if not enabled or mode!='wgc':
                        if source is not None:
                            source.close(); source=None; source_hwnd=0
                        if not enabled:
                            identity=last_frame=None
                            detector=None
                            self.stop_event.wait(.1)
                            continue
                    frame=None
                    used='mss'
                    if mode=='wgc' and started>=retry_wgc_after:
                        # Cache PID/HWND between probes; do not enumerate Win32
                        # game processes on every 33-ms frame.
                        if started-last_probe>=.85 or last_probe==0.0:
                            last_probe=started
                            try:
                                game=find_maple_window(keyword=cfg.get('game_title_keyword','maple'),
                                                       preferred_hwnd=source_hwnd or last_known_hwnd)
                            except Exception:
                                game=None
                            game_for_fallback=game
                            if game is not None:
                                last_known_hwnd=game.hwnd
                            if game and source is not None and game.hwnd!=source_hwnd:
                                source.close();source=None;source_hwnd=0
                            if game is not None:
                                if automatic:
                                    if auto_hwnd!=game.hwnd:
                                        auto_hwnd=game.hwnd
                                        auto_relative=None
                                        self.auto_region=None
                                        self.auto_method='waiting-for-frame'
                                    if auto_relative is not None:
                                        region=relative_to_region(game.rect,auto_relative)
                                        self.auto_region=dict(region)
                                    else:
                                        approximate=estimate(game.rect)
                                        region=approximate.region
                                if source is None:
                                    try:
                                        from .wgc_capture import WgcWindowSource
                                        # A WGC reconnect after MSS fallback gets a
                                        # fresh full-client visual calibration.
                                        if automatic and self.auto_method.startswith('mss-'):
                                            auto_relative=None
                                        # First native WGC frame probes the entire client
                                        # once; subsequent frames contain only chat pixels.
                                        full={'left':game.rect[0], 'top':game.rect[1],
                                              'width':game.rect[2], 'height':game.rect[3]}
                                        start_region=full if automatic and auto_relative is None else region
                                        source=WgcWindowSource(game.hwnd, game.rect, start_region)
                                        # Honour the same configured acquisition
                                        # interval as MSS. R13 left WGC at its
                                        # 33ms default while MSS used 80ms,
                                        # oversupplying moving-background frames
                                        # to the bounded OCR queue. This requests
                                        # native pacing before capture starts;
                                        # it does not discard queued chat frames.
                                        source.minimum_update_interval=round(max(.05,min(.25,float(cfg.get('capture_interval',.08))))*1000)
                                        self.capture_interval_ms=source.minimum_update_interval
                                        source.start()
                                        source_hwnd=game.hwnd
                                        self.backend_note='WGC connected'
                                    except Exception as exc:
                                        if source is not None:source.close()
                                        source=None;source_hwnd=0
                                        self.backend_note='WGC unavailable: '+str(exc)[:110]
                                        retry_wgc_after=started+10
                                else:
                                    # Do not replace pending full-client auto detection
                                    # with an estimated crop before the first frame.
                                    if not (automatic and auto_relative is None):
                                        source.set_geometry(game.rect,region)
                            elif source is not None:
                                source.close();source=None;source_hwnd=0
                        if source is not None:
                            raw=source.get(timeout=.045)
                            self.wgc_arrivals=source.arrivals
                            self.wgc_queue_overflows+=source.queue_overflows
                            source.queue_overflows=0
                            if source.finished or (not source.arrivals and started-source.started_at > 4):
                                self.backend_note='WGC stopped/no frames: '+str(source.error or 'capture closed or timed out')[:100]
                                source.close();source=None;source_hwnd=0
                                retry_wgc_after=started+10
                            elif raw is not None:
                                frame,region,timestamp=raw
                                started=timestamp
                                used='wgc'
                                if automatic and game_for_fallback is not None and auto_relative is None:
                                    # First WGC frame: direct CLIENT content, not screen.
                                    found=detect_chat_region(frame,game_for_fallback.rect)
                                    result=found if found is not None else estimate(game_for_fallback.rect)
                                    region=dict(result.region)
                                    self.auto_region=dict(region)
                                    self.auto_method=result.method
                                    self.auto_confidence=result.confidence
                                    auto_relative=region_to_relative(game_for_fallback.rect,region)
                                    frame=local_crop(frame,game_for_fallback.rect,region)
                                    source.set_geometry(game_for_fallback.rect,region)
                                    self.backend_note='WGC · '+result.method
                                elif automatic and game_for_fallback is not None:
                                    target=relative_to_region(game_for_fallback.rect,auto_relative)
                                    # The WGC callback can hand off 1-3 old full-client
                                    # frames produced before set_geometry(). Use the
                                    # *recorded frame region* rather than width alone:
                                    # 2x-DPI chat crops must never be mistaken for
                                    # uncropped full-client images.
                                    if region != target:
                                        full={'left':game_for_fallback.rect[0],
                                              'top':game_for_fallback.rect[1],
                                              'width':game_for_fallback.rect[2],
                                              'height':game_for_fallback.rect[3]}
                                        if region == full:
                                            frame=local_crop(frame,game_for_fallback.rect,target)
                                        else:
                                            # A stale game resize/move callback.
                                            continue
                                    region=target
                            elif (last_frame is not None and identity is not None and identity[0]=='wgc'
                                  and started-last_publish>=.24):
                                frame=last_frame.copy()
                                used='wgc'
                    if frame is None and (source is None or mode=='mss'):
                        # On unsupported WGC hardware, use the same automatically
                        # anchored chat geometry with MSS; no manual drag needed.
                        if automatic:
                            if mode=='mss':
                                if started-last_probe>=.85 or last_probe==0.0:
                                    last_probe=started
                                    try:
                                        game_for_fallback=find_maple_window(
                                            keyword=cfg.get('game_title_keyword','maple'),
                                            preferred_hwnd=last_known_hwnd)
                                        if game_for_fallback is not None:
                                            last_known_hwnd=game_for_fallback.hwnd
                                    except Exception: game_for_fallback=None
                            if game_for_fallback is None:
                                self.backend_note='게임 창 자동 연결 대기 (실행/창모드 확인)'
                                self.stop_event.wait(.2)
                                continue
                            game=game_for_fallback
                            if auto_hwnd!=game.hwnd:
                                auto_hwnd=game.hwnd
                                auto_relative=None
                            if auto_relative is None:
                                result=estimate(game.rect)
                                auto_relative=region_to_relative(game.rect,result.region)
                                self.auto_method='mss-'+result.method
                                self.auto_confidence=result.confidence
                            region=relative_to_region(game.rect,auto_relative)
                            self.auto_region=dict(region)
                        if not is_valid_region(region):
                            self.stop_event.wait(.15)
                            continue
                        try:
                            rect=tuple(int(region[k]) for k in ('left','top','width','height'))
                            shot=screenshotter.grab(dict(zip(('left','top','width','height'),rect)))
                            frame=np.ascontiguousarray(np.asarray(shot)[:,:,:3])
                            used='mss'
                        except Exception as exc:
                            self.report_error('MSS 화면 캡처 오류: '+str(exc))
                            self.stop_event.wait(.3)
                            continue
                    if frame is None:
                        self.stop_event.wait(.01)
                        continue
                    # Screen-position changes are NOT a different capture
                    # source. Track HWND/size rather than absolute (x, y).
                    hwnd = (game_for_fallback.hwnd if game_for_fallback is not None
                            and (used == 'wgc' or automatic) else 0)
                    current_id=(used,hwnd,int(region['width']),int(region['height']))
                    if identity != current_id:
                        identity=current_id
                        identity_changed=True
                        last_frame=None
                    if used=='wgc':
                        # Safety: confirm WGC callback returns a comparable
                        # colour frame; OCR consumes the same BGR format as MSS.
                        self.active_backend='wgc'
                    else:
                        self.active_backend='mss'
                    # WGC can deliver every game frame. Chat text stays on
                    # screen for seconds, so ~15 analysed frames/s are plenty;
                    # analysing all of them kept one CPU core busy and slowed
                    # the OCR thread. Periodic refresh frames are unaffected.
                    if used=='wgc' and 0 <= started-last_analysed < self.wgc_min_interval:
                        continue
                    last_analysed=started
                    bgr=np.ascontiguousarray(frame)
                    if used=='wgc' and (bgr.shape[1]!=region['width'] or bgr.shape[0]!=region['height']):
                        # DPI-scaled WGC buffers are mapped back to screen-space
                        # pixel coordinates before existing OCR bbox math.
                        bgr=cv2.resize(bgr,(region['width'],region['height']),
                                       interpolation=cv2.INTER_AREA)
                    # Text-row change detection with scrollbar removal and
                    # edge-flicker tolerant row identities (see ChangeDetector).
                    if detector is None or identity_changed:
                        detector=ChangeDetector()
                        identity_changed=False
                    signature_started=time.monotonic()
                    changed,row_signature=detector.observe(bgr)
                    # R14-FIX1 capture diagnostics, from the detector's rows.
                    ink_rows_seen,uncertain,_bright=detector.previous_ink
                    self.signature_ms=round((time.monotonic()-signature_started)*1000,2)
                    self.signature_rows=len(ink_rows_seen)
                    self.signature_uncertain_frames+=int(uncertain)
                    self.frames.maxsize=max(1,min(self.max_frames,64_000_000//max(1,bgr.nbytes)))
                    if changed or started-last_publish>=.24:
                        pushed=self.publish(CapturedChat(
                            bgr,dict(region),started,round((time.monotonic()-started)*1000,2),
                            changed,used,hwnd,
                            row_signature=row_signature))
                        if pushed:last_publish=started
                    last_frame=bgr
                    if used=='mss':
                        interval=max(.05,min(.25,float(cfg.get('capture_interval',.08))))
                        self.capture_interval_ms=round(interval*1000)
                        self.stop_event.wait(max(.001,interval-(time.monotonic()-started)))
        except Exception as ex:
            self.report_error('채팅 화면 캡처 오류: '+str(ex))
            self.stop_event.set()
        finally:
            if source is not None:
                source.close()
