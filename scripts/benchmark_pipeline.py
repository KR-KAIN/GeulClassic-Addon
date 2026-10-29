"""Repeatable stage benchmark; synthetic five-line workload, not game FPS QA."""
from kain_maple_translator.console_io import configure_utf8_console
configure_utf8_console()
import argparse
import json
import math
import os
from pathlib import Path
import platform
import statistics
import time
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.vision import TextRecognizer
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.row_admission import classified_chat_rows
from kain_maple_translator.translation import Translator,warmup_models,translate_generic_many
from kain_maple_translator.glossary import money_ko


def summarize(data):
    values=sorted(data)
    return {'samples':len(values),'p50_ms':round(statistics.median(values),2),
            'p95_ms':round(values[max(0,math.ceil(.95*len(values))-1)],2),
            'max_ms':round(values[-1],2)}


def five_lines(price=220):
    messages=[f'Alice: S> [MEBA] {price}k OBO','Bob: B> [WG] 1.5m',
              'Carol: lfm 2 kpq','Dave: Where is the next map?',
              'Eve: I need help with this quest']
    colors=[(28,28,28),(184,160,227),(34,194,247),(190,210,60),(180,169,150)]
    frame=np.zeros((150,800,3),dtype='uint8')
    for i,(text,color) in enumerate(zip(messages,colors)):
        y=i*30;frame[y:y+30]=color
        ink=(245,245,245) if i==0 else (132,66,7) if i==4 else (10,10,10)
        cv2.putText(frame,text,(7,y+21),cv2.FONT_HERSHEY_SIMPLEX,.53,ink,1,cv2.LINE_AA)
    return frame


def benchmark(iterations=20):
    cv2.setNumThreads(1)
    engines=warmup_models()
    reader=TextRecognizer()
    dummy=five_lines()
    reader.ocr.recognize_txt([dummy[:30]])
    reader.korean_ocr.recognize_txt([dummy[:30]])
    reader.ocr(dummy,use_det=True,use_cls=False,use_rec=True)
    root=Path(__file__).resolve().parents[1]
    report={'environment':{'platform':platform.platform(),'logical_cpus':os.cpu_count(),
            'engine_state':engines['engines'],'game_running_verified':False,
            'onnx_telemetry_disabled':True,'python_network_blocked':True},
            'scope':'OCR/translation stages only. Excludes real screen acquisition, normal-chat confirmation, Qt painting and OBS polling.',
            'workloads':{}}
    for label,make in [('actual_gray_two_lines',lambda i:cv2.imread(str(root/'tests/fixtures/gray-blue-megaphone.png'))),
                       ('synthetic_five_new_lines',lambda i:five_lines(220+i))]:
        cold=[];cached=[];combined=[];parsed_counts=[];stage=[]
        for i in range(iterations):
            frame=make(i);ocr=IncrementalChatOCR(reader)
            start=time.perf_counter();lines=ocr.detect(frame,0,0);cold.append((time.perf_counter()-start)*1000)
            rows=classified_chat_rows(lines,frame,0,0);parsed_counts.append(len(rows))
            tr=Translator();tr.translate_many([row['body'] for row in rows],'en-ko')
            combined.append((time.perf_counter()-start)*1000)
            stage.append(dict(ocr.stats))
            start=time.perf_counter();ocr.detect(frame,0,0);cached.append((time.perf_counter()-start)*1000)
        report['workloads'][label]={'ocr':summarize(cold),'cached_ocr':summarize(cached),
             'ocr_and_translation':summarize(combined),'parsed_row_counts':parsed_counts,'last_cold_stages':stage[-1]}
    source=['Where should we go after this quest?','Can somebody explain how this skill works?',
            'That monster is harder than I expected.','Do you want to explore the next map?',
            'The goblin stole my lunch yesterday.']
    times=[]
    for _ in range(iterations):
        start=time.perf_counter();out=translate_generic_many(source,'en-ko');times.append((time.perf_counter()-start)*1000)
    report['five_generic_translation_batch']={**summarize(times),'source':source,'output':out}
    tr=Translator();times=[]
    prices=['220k','1.5m','2m','0.001m','450k','2b']
    for i in range(30):
        item=f'[Fixture Item {i}]';price=prices[i%len(prices)];text=f'S> {item} {price} OBO'
        start=time.perf_counter();out=tr.translate_fast(text);times.append((time.perf_counter()-start)*1000)
        assert out is not None and item in out and money_ko(price) in out,(text,out)
    report['trade_template_30_constructed_cases']={**summarize(times),'compiled':tr.trade_memory.compiled,
        'hits':tr.trade_memory.hits,'all_values_preserved':True,'neural_model_calls':0}
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--iterations',type=int,default=20)
    parser.add_argument('--output');args=parser.parse_args()
    # The benchmark consumes only already-bundled local model files. Native
    # ORT telemetry is disabled by TextRecognizer; Python network is denied.
    with patch('socket.socket.connect',side_effect=RuntimeError('network disabled during benchmark')):
        result=benchmark(max(3,args.iterations))
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(text,encoding='utf-8')
    else:print(text)
