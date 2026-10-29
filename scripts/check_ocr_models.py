"""Validate bundled OCR model hashes and real language-appropriate inference.

The multilingual/English recognizer is tested against a Latin/digit fixture.
The Korean recognizers are tested against *Korean* labelled fixtures; the
32px Korean model must not be rejected because it misreads an English digit.
"""
from __future__ import annotations

from kain_maple_translator.console_io import configure_utf8_console
configure_utf8_console()

import hashlib
import json
import re
from pathlib import Path

import cv2
import numpy as np
from kain_maple_translator.vision import TextRecognizer


def _texts(result):
    return tuple(str(value).strip() for value in (getattr(result, "txts", None) or ()) if str(value).strip())


def verify_recognizers(reader, fixtures: Path) -> None:
    """All three recognizers and detection must perform real inference."""
    latin = np.full((48, 300, 3), 255, dtype=np.uint8)
    cv2.putText(latin, 'KAIN chat 123', (8, 32), cv2.FONT_HERSHEY_SIMPLEX,
                .7, (0, 0, 0), 2, cv2.LINE_AA)

    en_result = _texts(reader.ocr.recognize_txt([latin]))
    print('MULTILINGUAL RECOGNITION:', repr(en_result), flush=True)
    if not any('123' in text for text in en_result):
        raise RuntimeError('Multilingual OCR real inference failed; outputs=' + repr(en_result))

    linked_dir = fixtures / 'linked-labels-v28'
    linked = cv2.imread(str(linked_dir / 'korean-link-crop.png'))
    if linked is None:
        raise RuntimeError('Korean item validation fixture missing: korean-link-crop.png')

    # 32px whole-line Korean model: use Korean text fixtures, not OpenCV's
    # Latin-only Hershey font. Try multiple labelled samples because a single
    # tiny anti-aliased crop can be uncertain without a damaged model.
    sample_names = ('korean-link-crop.png', 'ko-02.png', 'ko-26.png', 'ko-01.png')
    korean_outputs = []
    whole_line_ok = False
    for name in sample_names:
        sample = cv2.imread(str(linked_dir / name))
        if sample is None:
            raise RuntimeError('Korean whole-line fixture missing: ' + name)
        observed = _texts(reader.korean_ocr.recognize_txt([sample]))
        korean_outputs.append((name, observed))
        print('KOREAN WHOLE-LINE RECOGNITION:', name, repr(observed), flush=True)
        if any(len(re.findall(r'[가-힣]', text)) >= 2 for text in observed):
            whole_line_ok = True
            break
    if not whole_line_ok:
        raise RuntimeError('Korean whole-line OCR real inference failed on Korean fixtures; '
                           'outputs=' + repr(korean_outputs))

    # Independently prove the 48px link-specific inference still reads a
    # known real Hangul label; do not bypass a broken Korean ONNX model.
    link_result = _texts(reader.korean_link_ocr.recognize_txt([linked]))
    print('KOREAN ITEM RECOGNITION:', repr(link_result), flush=True)
    if not any('[아대공격력주문서60%]' in ''.join(text.split()) for text in link_result):
        raise RuntimeError('Korean item OCR real inference failed; outputs=' + repr(link_result))

    det_result = _texts(reader.ocr(latin, use_det=True, use_cls=False, use_rec=True))
    print('MULTILINGUAL DETECTOR RECOGNITION:', repr(det_result), flush=True)
    if not det_result:
        raise RuntimeError('OCR detector real inference failed; outputs=' + repr(det_result))
    print('OCR PASS: detector + multilingual, Korean whole-line and Korean item models verified', flush=True)


def check() -> None:
    root = Path(__file__).resolve().parents[1] / 'resources' / 'ocr'
    manifest = json.loads((root / 'model-manifest.json').read_text('utf-8'))
    for name, meta in manifest.items():
        path = root / name
        if not path.is_file():
            raise RuntimeError('OCR model missing: ' + name)
        if path.stat().st_size != meta['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != meta['sha256']:
            raise RuntimeError('OCR model hash mismatch: ' + name)
        print('HASH PASS', name, flush=True)
    fixtures = root.parents[1] / 'tests' / 'fixtures'
    if not fixtures.is_dir():
        # public clone: the real game screenshots are not published; the
        # models still load and their hashes were verified above
        TextRecognizer()
        print('OCR PASS: models load and hashes match (real-screenshot check skipped: '
              'tests/fixtures is not in the public repository)', flush=True)
        return
    verify_recognizers(TextRecognizer(), fixtures)


if __name__ == '__main__':
    check()
