"""Video-only capture signature replay; no model inference or speed simulation."""
import argparse,hashlib,json,time,sys
from pathlib import Path
import cv2,numpy as np
p=argparse.ArgumentParser(description='Replay video pixels at a selected acquisition cadence; does not emulate Windows WGC or OCR.')
p.add_argument('video');p.add_argument('output')
p.add_argument('--source-root',default=str(Path(__file__).resolve().parents[1]))
p.add_argument('--step',type=float,default=.08)
p.add_argument('--region',type=int,nargs=4,default=(330,833,621,80))
p.add_argument('--legacy-cache-confidence',action='store_true',help='Reproduce R13 identical-frame uncertainty bug for comparison')
a=p.parse_args()
if a.step<=0 or min(a.region[:2])<0 or min(a.region[2:])<=0:p.error('Invalid step/region')
sys.path.insert(0,str(Path(a.source_root).resolve()))
from kain_maple_translator.capture_stream import CapturedChat,covered_middle_frame
from kain_maple_translator.fast_vision import ink_rows
from kain_maple_translator.megaphone import detect_band
def capture_row_signature(image):
 rows,uncertain=ink_rows(image)
 return tuple((hashlib.blake2b((r.neutral[:,:,0]<170).tobytes()+str(r.neutral.shape).encode(),digest_size=12).digest(),detect_band(image,r.rect).tone,r.rect) for r in rows),uncertain
cv2.setNumThreads(1)
v=cv2.VideoCapture(a.video); fps=v.get(5);total=int(v.get(7))
if not v.isOpened() or fps<=0 or total<=0:raise SystemExit('Cannot decode video')
x,y,width,height=a.region
if x+width>v.get(3) or y+height>v.get(4):raise SystemExit('Region outside video')
selected={round(n*a.step*fps) for n in range(int(total/fps/a.step)+1)}
previous=previous_ink=None;previous_uncertain=True;last_publish=-10
entries=[];pending=[];covered=0;certain=0;empty=0;changed_count=0;refresh_count=0;ms=[]
for i in range(int(v.get(7))):
 ok,f=v.read()
 if not ok:break
 if i not in selected:continue
 bgr=f[y:y+height,x:x+width].copy();s=i/fps;start=time.perf_counter()
 same=previous is not None and np.array_equal(previous,bgr)
 if same and previous_ink is not None:
  signature=previous_ink;uncertain=False if a.legacy_cache_confidence else previous_uncertain
 else: signature,uncertain=capture_row_signature(bgr)
 pixel_change=1. if previous is None else float(np.mean(np.max(cv2.absdiff(bgr,previous),axis=2)>18))
 if previous_ink is None:changed=True
 elif signature and previous_ink:
  changed=signature!=previous_ink
  if uncertain: changed=changed or (len(signature)<2 and pixel_change>.06)
 else:changed=signature!=previous_ink or pixel_change>.06
 if not uncertain:certain+=1
 if not signature:empty+=1
 emitted=changed or s-last_publish>=.24
 if emitted:
  changed_count+=int(changed);refresh_count+=int(not changed);last_publish=s
  row_sig=tuple((r[0],r[1]) for r in signature) if not uncertain else ()
  frame=CapturedChat(np.empty((0,0,3),np.uint8),dict(left=x,top=y,width=width,height=height),s,row_signature=row_sig)
  pending.append(frame)
  pos=1
  while pos<len(pending)-1:
   if covered_middle_frame(pending[pos-1],pending[pos],pending[pos+1]):
    del pending[pos];covered+=1;pos=max(1,pos-1)
   else:pos+=1
 entries.append({'frame':i,'second':round(s,3),'rows':len(signature),'uncertain':bool(uncertain),'changed':bool(changed),'published':bool(emitted),'pixel_change':round(pixel_change,5)})
 previous=bgr;previous_ink=signature;previous_uncertain=uncertain
 ms.append((time.perf_counter()-start)*1000)
 if i%300==0:print(i,flush=True)
out={'video':Path(a.video).name,'video_sha256':hashlib.sha256(Path(a.video).read_bytes()).hexdigest(),'roi':a.region,'frames':len(entries),'fps':fps,'acquisition_step_seconds':a.step,'certain_segmentation':certain,'empty_segmentation':empty,'changed_snapshots':changed_count,'periodic_confirmations':refresh_count,'offline_compaction_covered':covered,'remaining_snapshots_without_consumer':len(pending),'capture_replay_processing_ms':round(sum(ms),2),'capture_replay_median_ms':round(float(np.median(ms)),2),'note':'Sequential capture signature replay at selected timestamps only; no OCR consumer, WGC emulation or measured live-app delay. OS minimum_update_interval requests a throttle, not this exact schedule. Cadence comparison does not prove all future brief chat messages are retained. Offline compaction stats are algorithm coverage, not runtime dropped frames.','entries':entries}
Path(a.output).write_text(json.dumps(out,indent=2));print({k:v for k,v in out.items() if k!='entries'})
