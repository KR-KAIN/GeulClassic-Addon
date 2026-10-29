"""Local video regression tool: pass your original recording and chat rectangle."""
import argparse,sys,json,time,statistics,dataclasses
from pathlib import Path
p=argparse.ArgumentParser(description='Replay a local video through chat OCR/admission; does not emulate WGC or Qt.')
p.add_argument('video');p.add_argument('output');p.add_argument('--step',type=float,default=.25)
p.add_argument('--region',type=int,nargs=4,default=(330,833,621,80),metavar=('X','Y','W','H'))
a=p.parse_args()
if a.step<=0 or min(a.region[:2])<0 or min(a.region[2:])<=0:
    p.error('step/region size must be positive and origin must be nonnegative')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
from kain_maple_translator.vision import TextRecognizer
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.row_admission import classified_chat_rows,RowAdmission
from kain_maple_translator.visual_message_ledger import FrameMessageLedger
from kain_maple_translator.frame_context import inspect_scrollbar,without_scrollbar
from kain_maple_translator.translation import Translator
from kain_maple_translator.channel_guard import ChannelGuard
v=cv2.VideoCapture(a.video)
if not v.isOpened():raise SystemExit('Cannot open video: '+a.video)
x,y,width,height=a.region
fps=v.get(cv2.CAP_PROP_FPS);total=int(v.get(cv2.CAP_PROP_FRAME_COUNT))
if fps<=0 or total<=0:raise SystemExit('Video has no usable frame metadata')
if x+width>v.get(cv2.CAP_PROP_FRAME_WIDTH) or y+height>v.get(cv2.CAP_PROP_FRAME_HEIGHT):
    raise SystemExit('Chat region is outside the video frame')
cv2.setNumThreads(1)
recognizer=TextRecognizer();engine=IncrementalChatOCR(recognizer)
admission=RowAdmission();ledger=FrameMessageLedger();tr=Translator(body_only=True);guard=ChannelGuard();report=[]
selected={round(i*a.step*fps) for i in range(int(total/fps/a.step)+1)}
for frame_ix in range(total):
 ok,f=v.read()
 if not ok:break
 if frame_ix not in selected:continue
 s=frame_ix/fps
 im=f[y:y+height,x:x+width].copy();scroll=inspect_scrollbar(im);im=without_scrollbar(im,scroll)
 start=time.perf_counter();lines=engine.detect(im,0,0);rows=classified_chat_rows(lines,im,0,0)
 for row in rows:
  rx,ry,rw,rh=row['rect'];row['_tracking_rect']=(rx,ry-height,rw,rh)
 admitted=admission.filter(rows,100+s);fresh=ledger.filter(admitted,rows,100+s)
 fresh=[row for row in fresh if guard.accept(row,100+s)]
 def fast_result(row):
  try:return {**row,'fast_translation':tr.translate_fast(row['body'],'en-ko'),'fast_error':None}
  except Exception as ex:return {**row,'fast_translation':None,'fast_error':type(ex).__name__+': '+str(ex)}
 item={'second':round(s,2),'ms':round((time.perf_counter()-start)*1000,2),'raw':[dataclasses.asdict(l) for l in lines],'rows':rows,'admitted':len(admitted),'fresh':[fast_result(r) for r in fresh],'stats':dict(engine.stats)}
 report.append(item)
 print(s,round(item['ms']),len(lines),len(rows),len(fresh),flush=True)
v.release()
if not report:raise SystemExit('No frames could be decoded')
result={'sample_count':len(report),'total_ms':round(sum(x['ms'] for x in report),2),'median_ms':round(statistics.median(x['ms'] for x in report),2),'row_observations':sum(len(x['rows']) for x in report),'admitted_observations':sum(x['admitted'] for x in report),'delivered_events':sum(len(x['fresh']) for x in report),'rows':report}
Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print({k:v for k,v in result.items() if k!='rows'},flush=True)
