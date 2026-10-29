"""R12: replay a gameplay recording through capture -> queue -> OCR -> admission.

usage (OPEN-BUILD-CONSOLE.bat 창에서):
    python scripts\\replay_video_latency.py "D:\\녹화\\2026-10-27 11-06-26.mp4"

The recording must show the whole game client (e.g. a full-screen OBS
capture). The chat ROI is located with the same automatic detector the
addon uses. A simulated clock replays frames in real time: frame i arrives at
i/fps and the OCR worker is busy for the measured time of each frame, exactly
like LiveWorker. Translation inference is NOT included. No text is written to
disk; delivered chat is printed to this console only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kain_maple_translator.console_io import configure_utf8_console  # noqa: E402
configure_utf8_console()

import cv2  # noqa: E402
import numpy as np  # noqa: E402


def load_rois(path):
    from kain_maple_translator.auto_chat_detect import detect_chat_region, estimate
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit('영상을 열 수 없습니다: ' + str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frames, region = [], None
    import os
    manual = os.environ.get('REPLAY_REGION')  # "left,top,width,height" for scaled recordings
    if manual:
        l, t, w, h = (int(v) for v in manual.split(','))
        region = {'left': l, 'top': t, 'width': w, 'height': h}
        print('채팅 영역:', region, '(REPLAY_REGION 지정)', flush=True)
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if region is None:
            h, w = frame.shape[:2]
            found = detect_chat_region(frame, (0, 0, w, h))
            region = (found or estimate((0, 0, w, h))).region
            print('채팅 영역:', region, '(자동 탐지)' if found else '(추정값)', flush=True)
        r = region
        frames.append(frame[r['top']:r['top']+r['height'], r['left']:r['left']+r['width']].copy())
    return frames, float(fps), region


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    from kain_maple_translator.capture_stream import ChatCaptureStream, CapturedChat, ChangeDetector
    from kain_maple_translator.vision import TextRecognizer
    from kain_maple_translator.fast_vision import IncrementalChatOCR
    from kain_maple_translator.row_admission import RowAdmission, classified_chat_rows
    from kain_maple_translator.channel_guard import ChannelGuard
    from kain_maple_translator.visual_message_ledger import FrameMessageLedger
    from kain_maple_translator.frame_context import inspect_scrollbar, without_scrollbar

    frames, fps, region = load_rois(sys.argv[1])
    print(f'프레임 {len(frames)}개 · {fps:.1f}fps · 길이 {len(frames)/fps:.1f}초', flush=True)
    detector = ChangeDetector()
    stream = ChatCaptureStream(lambda: {}, lambda m: None, capacity=48)
    engine = IncrementalChatOCR(TextRecognizer())
    admission, guard, ledger = RowAdmission(), ChannelGuard(), FrameMessageLedger()
    browsing = False
    worker_free = 0.0
    last_analysed = last_publish = float('-inf')
    tail = int(fps * 2)
    i = 0
    proc, skipped, delivered = [], 0, []
    max_lag = float(sys.argv[2]) if len(sys.argv) > 2 else None
    lag_drops = 0
    while True:
        while i < len(frames)+tail and i/fps <= worker_free:
            t = i/fps
            image = frames[min(i, len(frames)-1)]
            i += 1
            if 0 <= t-last_analysed < stream.wgc_min_interval:
                continue
            last_analysed = t
            changed, signature = detector.observe(image)
            if changed or t-last_publish >= .24:
                if stream.publish(CapturedChat(image, dict(region), t, 0.0, changed, 'wgc', 1,
                                               row_signature=signature)):
                    last_publish = t
        if stream.frames.empty():
            if i >= len(frames)+tail:
                break
            worker_free = i/fps
            continue
        captured = stream.frames.get_nowait()
        # Same rule as ChatCaptureStream.get(max_lag_s) on the simulated clock.
        while max_lag is not None and worker_free-captured.captured_at > max_lag and not stream.frames.empty():
            captured = stream.frames.get_nowait()
            lag_drops += 1
        start = max(worker_free, captured.captured_at)
        began = time.perf_counter()
        bgr = captured.image
        context = inspect_scrollbar(bgr)
        accepted = []
        if context.at_bottom is False:
            browsing = True
            skipped += 1
        else:
            if browsing and context.at_bottom is True:
                browsing = False
                admission, guard, ledger = RowAdmission(), ChannelGuard(), FrameMessageLedger()
            bgr = without_scrollbar(bgr, context)
            lines = engine.detect(bgr, region['left'], region['top'], 1.8)
            rows = classified_chat_rows(lines, bgr, region['left'], region['top'])
            for row in rows:
                x, y, w, h = row['rect']
                row['_tracking_rect'] = (x-region['left'], y-region['top']-region['height'], w, h)
            fresh = ledger.filter(admission.filter(rows, captured.captured_at), rows, captured.captured_at)
            accepted = [row for row in sorted(fresh, key=lambda r: r['rect'][1])
                        if guard.accept(row, captured.captured_at)]
        elapsed = time.perf_counter()-began
        proc.append(elapsed*1000)
        worker_free = start+elapsed
        for row in accepted:
            seen = row.get('first_observed_at', captured.captured_at)
            delivered.append((worker_free, worker_free-captured.captured_at, row['nickname'], row['body']))
            print(f"{worker_free:6.2f}s 표시 (캡처 후 {worker_free-captured.captured_at:4.2f}s) | {row['nickname']} : {row['body']}",
                  flush=True)
    arr = np.array(proc) if proc else np.array([0.])
    delays = np.array([d[1] for d in delivered]) if delivered else np.array([0.])
    print('\n=== 요약 (번역 추론 시간 제외) ===')
    print(f'OCR 처리 프레임 {len(proc)}개 · 프레임당 중앙값 {np.median(arr):.0f}ms · p95 {np.percentile(arr, 95):.0f}ms')
    print(f'과거 채팅 탐색으로 건너뛴 프레임 {skipped}개')
    print(f'전달된 채팅 {len(delivered)}개 · 캡처→표시 중앙값 {np.median(delays):.2f}s · 최대 {delays.max():.2f}s')
    print(f'캡처 보관 한도 초과 {stream.overflows}회 · 지연 한도로 건너뛴 프레임 {lag_drops}개')


if __name__ == '__main__':
    main()
