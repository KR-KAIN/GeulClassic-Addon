"""Repeatable source-pixel reuse/burst benchmark, not Windows FPS certification."""
from pathlib import Path
import hashlib,json,time,statistics,argparse
import numpy as np
import cv2
from kain_maple_translator.vision import TextRecognizer
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.capture_stream import ChatCaptureStream,CapturedChat
from kain_maple_translator.frame_context import inspect_scrollbar,without_scrollbar

def run(root):
    cv2.setNumThreads(1)
    frame=cv2.imread(str(root/'tests/fixtures/user-four-colour-rows.png'))
    if frame is None:raise RuntimeError('Missing bundled four-colour fixture')
    frame=without_scrollbar(frame,inspect_scrollbar(frame))
    reader=TextRecognizer();clock=[0.];engine=IncrementalChatOCR(reader,clock=lambda:clock[0])
    timings=[];inputs=[];hashes=[]
    for index in range(12):
        clock[0]=index*3. # A paused chat seen over 33 seconds, no wall-clock sleeping.
        started=time.perf_counter();lines=engine.detect(frame,0,0)
        timings.append(round((time.perf_counter()-started)*1000,3))
        inputs.append(engine.stats.get('recognition_inputs',0))
        hashes.append(hashlib.sha256('\n'.join(l.text for l in lines).encode()).hexdigest())
    stream=ChatCaptureStream(lambda:{},lambda _:None,capacity=48)
    for index in range(30):
        item=CapturedChat(np.full((20,80,3),index,np.uint8),dict(left=0,top=0,width=80,height=20),float(index))
        item.row_signature=tuple(range(index,index+4))
        stream.publish(item)
    frames=0;covered=set()
    while not stream.frames.empty():
        item=stream.get(timeout=0);covered.update(item.row_signature);frames+=1
    return {'scope':'Linux CPU, same bundled OCR; static source image and controlled 30-frame scrolling burst. Not live Windows latency.',
            'static_reuse':{'samples':12,'virtual_interval_s':3,'wall_total_ms':round(sum(timings),3),
              'median_ms':round(statistics.median(timings),3),'timings_ms':timings,'recognition_inputs':sum(inputs),
              'inputs_per_pass':inputs,'stable_text':len(set(hashes))==1,'text_sha256':hashes[0]},
            'capture_burst':{'submitted_frames':30,'frames_read':frames,'unique_rows_retained':len(covered),
              'expected_unique_rows':33,'covered_compactions':getattr(stream,'covered_frames',0),
              'stale_drops':stream.stale_drops,'expired_drops':stream.expired_drops,'overflows':stream.overflows}}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=run(args.root)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(text)
