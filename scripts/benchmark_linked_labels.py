"""Repeatable synthetic label + real four-row replay; no live gameplay claims."""
import os
os.environ['ORT_DISABLE_TELEMETRY'] = '1'
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
from unittest.mock import patch


def compact(value):
    return ''.join(value.split())


def timings(values):
    ordered = sorted(values)
    return dict(p50_ms=round(statistics.median(ordered), 2),
                p95_ms=round(ordered[math.ceil(len(ordered)*.95)-1], 2),
                max_ms=round(ordered[-1], 2))


def run(source, fixtures, repeats):
    import cv2
    import numpy as np
    from kain_maple_translator.vision import TextRecognizer
    from kain_maple_translator.fast_vision import IncrementalChatOCR
    from kain_maple_translator import row_admission
    from kain_maple_translator.translation import Translator
    classify = row_admission.classified_chat_rows
    cv2.setNumThreads(1)
    reader = TextRecognizer()
    warm = np.full((32,240,3), 255, dtype=np.uint8)
    cv2.putText(warm, 'Test 123', (4,24), cv2.FONT_HERSHEY_SIMPLEX, .6, (0,0,0), 1)
    for name in ('ocr', 'korean_ocr', 'korean_link_ocr'):
        engine = getattr(reader, name, None)
        if engine is not None: engine.recognize_txt([warm])
    records = []
    for case in json.loads((fixtures/'linked-labels-v28/labels.json').read_text(encoding='utf8')):
        image = cv2.imread(str(fixtures/'linked-labels-v28'/case['file']))
        engine = IncrementalChatOCR(reader)
        start = time.perf_counter()
        lines = engine.detect(image, 0, 0)
        rows = classify(lines, image, 0, 0)
        elapsed = (time.perf_counter()-start)*1000
        observed = rows[0]['body'] if len(rows) == 1 else ''
        found = re.findall(r'\[[^\[\]]*\]', observed)
        records.append(dict(case, observed=observed, raw=[line.text for line in lines],
            label_exact=bool(found and compact(found[0]) == compact(case['label'])),
            body_exact=compact(observed) == compact(case['body']),
            numbers_exact=re.findall(r'\d+',observed) == re.findall(r'\d+',case['body']),
            classification_exact=len(rows) == 1 and (rows[0]['kind']=='normal') == (case['kind']=='normal'),
            elapsed_ms=round(elapsed,2)))
    groups = {}
    for lang in ('ko','en'):
        subset = [r for r in records if r['language']==lang]
        groups[lang] = dict(cases=len(subset), **{key:sum(r[key] for r in subset)
            for key in ('label_exact','body_exact','numbers_exact','classification_exact')},
            **timings([r['elapsed_ms'] for r in subset]))
    image = cv2.imread(str(fixtures/'user-native-palette-rows.png'))
    translator = Translator(body_only=True)
    fresh, unchanged, batches = [], [], []
    for _ in range(repeats):
        if hasattr(row_admission,'_CLASSIFIED_CACHE'): row_admission._CLASSIFIED_CACHE.clear()
        engine = IncrementalChatOCR(reader)
        start = time.perf_counter()
        lines = engine.detect(image,0,0)
        rows = classify(lines,image,0,0)
        translated = [translator.translate_fast(r['body']) for r in rows]
        fresh.append((time.perf_counter()-start)*1000)
        start = time.perf_counter()
        same = engine.detect(image,0,0)
        classify(same,image,0,0)
        unchanged.append((time.perf_counter()-start)*1000)
        batches.append(engine.stats.get('recognition_batches',-1))
    return dict(source=source.name, scope='Synthetic development fixtures; real 4-row CPU replay. No screen capture, rendering or live game load. Fresh uses resident warmed models and rule translation; unchanged measures OCR + classification.',
        synthetic=groups, actual_four_rows=dict(repeats=repeats,fresh=timings(fresh),
            unchanged=timings(unchanged),unchanged_ocr_batches=batches,rows=rows,translations=translated),
        records=records)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source')
    parser.add_argument('--output',required=True)
    parser.add_argument('--repeats',type=int,default=20)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=Path(args.source).resolve() if args.source else root
    sys.path.insert(0,str(source))
    with patch('socket.socket.connect',side_effect=RuntimeError('offline benchmark')):
        report=run(source,root/'tests/fixtures',args.repeats)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},ensure_ascii=False),flush=True)
