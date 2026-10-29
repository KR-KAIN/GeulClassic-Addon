"""Compare OCR on 24 labelled synthetic scroll lines; not native game accuracy.

Optional --source points at an older source tree for a controlled comparison.
Default execution needs only this independent folder and its bundled models.
"""
import os
os.environ['ORT_DISABLE_TELEMETRY']='1'
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time
import unicodedata
from unittest.mock import patch


def compact(value):
    return ''.join(unicodedata.normalize('NFKC',value).casefold().split())


def edits(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]


def run(root,stress=False):
    import cv2
    import numpy as np
    from kain_maple_translator.vision import TextRecognizer
    from kain_maple_translator.fast_vision import IncrementalChatOCR
    from kain_maple_translator.row_admission import classified_chat_rows
    cv2.setNumThreads(1)
    samples=['S> glove att 60% Kfan +1 100% scrolls',
             'S> claw ATT+2 60% scroll 220k','S> 8att WG 2m','B> GFA 60% / GMA 100%']
    palettes=[('cyan',(199,221,95),(50,100,80)),('yellow',(6,183,235),(15,90,125)),
              ('pink',(185,170,220),(125,40,75))]
    reader=TextRecognizer()
    warm=np.full((32,400,3),255,dtype=np.uint8)
    cv2.putText(warm,'Alice: S> 60%',(5,23),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
    reader.ocr.recognize_txt([warm])
    results=[]
    for font in ((.30,.38) if stress else (.38,.55)):
        for color,background,foreground in palettes:
            for body in samples:
              for degradation in (('jpeg_q55','soft_blur') if stress else ('clean',)):
                image=np.full((32,700,3),background,dtype=np.uint8)
                cv2.putText(image,'Alice: '+body,(5,23),cv2.FONT_HERSHEY_SIMPLEX,font,foreground,1,cv2.LINE_AA)
                if degradation=='jpeg_q55':
                    ok,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,55]);assert ok
                    image=cv2.imdecode(encoded,cv2.IMREAD_COLOR)
                elif degradation=='soft_blur':
                    image=cv2.GaussianBlur(image,(3,3),.60)
                engine=IncrementalChatOCR(reader)
                start=time.perf_counter();lines=engine.detect(image,0,0);rows=classified_chat_rows(lines,image,0,0)
                elapsed=(time.perf_counter()-start)*1000
                observed=rows[0]['body'] if len(rows)==1 else ''
                numbers=lambda s:__import__('re').findall(r'\d+(?:[.,]\d+)*',s)
                results.append({'font':font,'color':color,'degradation':degradation,'truth':body,'observed':observed,
                                'raw':[line.text for line in lines],'rows':len(rows),
                                'exact_ignoring_spacing_case':compact(body)==compact(observed),
                                'numeric_sequence_exact':numbers(body)==numbers(observed),
                                'edits':edits(compact(body),compact(observed)),
                                'truth_characters':len(compact(body)),'ocr_ms':round(elapsed,2),
                                'critical_retries':engine.stats.get('critical_retry_rows',0),
                                'numeric_disagreements':engine.stats.get('numeric_retry_disagreements',0)})
    values=sorted(row['ocr_ms'] for row in results)
    return {'scope':'Labelled synthetic OpenCV-font scroll bodies, not the absent source chat of the latest screenshot.',
            'stress':stress,
            'source_version':root.name,'cases':len(results),'exact_rows':sum(row['exact_ignoring_spacing_case'] for row in results),
            'exact_numeric_rows':sum(row['numeric_sequence_exact'] for row in results),
            'total_character_edits':sum(row['edits'] for row in results),
            'total_characters':sum(row['truth_characters'] for row in results),
            'ocr_p50_ms':round(statistics.median(values),2),'ocr_p95_ms':values[math.ceil(len(values)*.95)-1],
            'critical_retry_inputs':sum(row['critical_retries'] for row in results),
            'numeric_disagreements':sum(row['numeric_disagreements'] for row in results),'results':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source');parser.add_argument('--output');parser.add_argument('--stress',action='store_true');args=parser.parse_args()
    root=Path(args.source).resolve() if args.source else Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    with patch('socket.socket.connect',side_effect=RuntimeError('offline benchmark')):report=run(root,args.stress)
    if args.output:Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False),flush=True)
