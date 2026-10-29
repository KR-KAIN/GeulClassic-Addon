"""Screen-only HUD recognizer for hunter session; separated from chat OCR.

This is best-effort: visual-only slot counts can become unreadable at small
resolutions. Missing readings stay unknown, never fabricated.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
import cv2
import numpy as np
from .hunt_stats import parse_exp_text,parse_meso_text
from .image_io import read_image

# Reference contains keyboard chrome (not particular potion identities).
REFERENCE = Path(getattr(sys,'_MEIPASS', Path(__file__).resolve().parents[1]))/'resources/hunt/keyboard-reference.png'
# Relative rects measured on the supplied 219x162 reference image.
# Keep the complete bottom-row tile. The stack count is drawn on the far
# LEFT edge and the artwork may extend to the RIGHT edge. The previous 41px
# center crop visibly amputated both the first digit and rounded potions.
SLOTS = {'Ctrl':(6,110,55,154), 'Del':(56,110,105,154),
         'End':(106,110,155,154), 'PgDn':(156,110,205,154)}
# Other keys can also hold potions. Only displayed slots with a visually
# occupied centre are considered; do not read the key label as an item.
ALL_KEYS = (
    ('1','2','3','4'), ('Shift','Ins','Hm','Pup'),
    ('Ctrl','Del','End','PgDn')
)


def _is_1080pish(shape):
    h,w=shape[:2]
    return abs(w/float(h)-16/9.)<0.06 and 1750<=w<=2050 and 980<=h<=1120


def _fixed_1080p_keyboard_boxes(image):
    if image is None or image.size==0 or not _is_1080pish(image.shape):
        return []
    h,w=image.shape[:2]
    # Grounded on the user's 1920x1080 Maple HUD screenshot.
    base=(round(w*0.680), round(h*0.759), round(w*0.114), round(h*0.149))
    x,y,bw,bh=base
    tweaks=[(0,0),(0,-4),(-4,-4),(3,-3),(-6,-2)]
    boxes=[]
    for dx,dy in tweaks:
        bx=max(0,min(w-bw,x+dx));by=max(0,min(h-bh,y+dy))
        boxes.append((bx,by,bw,bh))
    return boxes


def _fixed_1080p_exp_rois(frame):
    if frame is None or frame.size==0 or not _is_1080pish(frame.shape):
        return []
    h,w=frame.shape[:2]
    # The EXP label/value is centered in the lower HUD on 1080p captures.
    return [
        ('1080p HUD 고정 EXP 영역', frame[round(h*0.910):round(h*0.944), round(w*0.475):round(w*0.602)]),
        ('1080p HUD 보조 EXP 영역', frame[round(h*0.905):round(h*0.950), round(w*0.462):round(w*0.615)]),
    ]


def _keyboard_grid_verified(gray, box):
    """Validate twelve pale key faces, not correlation against sky/EXP UI.

    Template-matching alone creates convincing false positives because many
    game HUD textures have similar average brightness. Actual potion icons
    can darken three faces, so the test permits up to four dark keys.
    """
    x,y,w,h=box
    part=gray[y:y+h,x:x+w]
    if part.shape[:2]!=(h,w):return False
    pale=0
    contrasts=[]
    for r in range(3):
        for c in range(4):
            x1=round((20+50*c)*w/219);x2=round((41+50*c)*w/219)
            y1=round((17+50*r)*h/162);y2=round((35+50*r)*h/162)
            cell=part[y1:y2,x1:x2]
            if cell.size and float(np.mean(cell))>148:pale+=1
            # A real quickslot panel contains dark vertical dividers between
            # four repeated pale key faces. Sky, clouds and other flat HUD
            # regions can have twelve pale patches without any such grid.
            ix=round((10+50*c)*w/219)
            cy=round((28+50*r)*h/162)
            separator=part[max(0,cy-5):min(h,cy+6),max(0,ix-1):min(w,ix+2)]
            if cell.size and separator.size:
                contrasts.append(float(np.mean(cell))-float(np.mean(separator)))
    return (pale>=8 and len(contrasts)>=10 and
            sum(v>38 for v in contrasts)>=8 and np.mean(contrasts)>70)


def locate_keyboard(bgr, reference=None):
    if bgr is None or bgr.size==0:return None
    ref=read_image(REFERENCE) if reference is None else reference
    if ref is None:return None
    mask=np.ones(ref.shape[:2],np.uint8)*255
    for row in range(3):
        for col in range(4):
            x0=10+col*50;y0=8+row*50
            mask[y0+13:y0+43,x0+7:x0+40]=0
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    template=cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY)
    best=(-1.,None)
    # UI can be rendered at <70% of the reference size on low-resolution
    # game windows. The previous 0.70 floor silently missed all such cases.
    for factor in (0.46,0.52,0.58,0.64,0.70,0.78,0.85,0.92,1.0,1.08,1.18,1.30):
        tw,th=round(ref.shape[1]*factor),round(ref.shape[0]*factor)
        if tw>gray.shape[1] or th>gray.shape[0] or tw<80:continue
        t=cv2.resize(template,(tw,th),interpolation=cv2.INTER_AREA)
        m=cv2.resize(mask,(tw,th),interpolation=cv2.INTER_NEAREST)
        result=cv2.matchTemplate(gray,t,cv2.TM_CCORR_NORMED,mask=m)
        # A bright sky / flat HUD may outrank the keyboard by a hair.
        # Inspect several independent maxima instead of returning that false
        # positive immediately. Never rescan the entire frame with OCR.
        for _ in range(4):
            _,score,_,point=cv2.minMaxLoc(result)
            if score<.82:break
            box=(point[0],point[1],tw,th)
            if _keyboard_grid_verified(gray,box):
                if score>best[0]:best=(score,box)
                break
            # Suppress the false peak and inspect the next one.
            bx,by=point
            result[max(0,by-th//2):min(result.shape[0],by+th//2+1),
                   max(0,bx-tw//2):min(result.shape[1],bx+tw//2+1)]=0
    return best[1]


def locate_keyboard_near_hud(image):
    """Search the usual bottom/right keyboard first to avoid full-frame OCR lag.

    The game allows players to move the keyboard UI, so fall back to an
    unrestricted window search when it isn't in the expected region.
    """
    if image is None or image.size==0:return None
    h,w=image.shape[:2]
    x0=round(w*.38);y0=round(h*.45)
    likely=locate_keyboard(image[y0:,x0:])
    if likely is not None:
        x,y,bw,bh=likely
        return (x+x0,y+y0,bw,bh)
    # 1080p fullscreen captures often place the quickslot HUD at a stable
    # bottom-right location. Use this grounded fallback before an expensive
    # whole-frame search, because the template matcher can otherwise drift to
    # unrelated bright textures.
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    for box in _fixed_1080p_keyboard_boxes(image):
        if _keyboard_grid_verified(gray,box):
            return box
        crops=potion_crops(image,box)
        if sum(1 for crop in crops.values() if slot_occupied(crop))>=2:
            return box
    return locate_keyboard(image)


def potion_crops(image, keyboard, all_slots=False):
    if keyboard is None:return {}
    x,y,w,h=keyboard
    scale=w/219.
    result={}
    if all_slots:
        # Same full-tile geometry as SLOTS for every key. Keys are 50px
        # apart horizontally but only ~47.5px vertically; the old 12..53
        # crop also cut off the stack count's first digit (9 read as 1).
        selected={name:(6+col*50, round(110-(2-row)*47.5),
                        55+col*50, round(110-(2-row)*47.5)+44)
                  for row,group in enumerate(ALL_KEYS)
                  for col,name in enumerate(group)}
    else:
        selected=SLOTS
    for slot,(x1,y1,x2,y2) in selected.items():
        a,b,c,d=x+round(x1*scale),y+round(y1*scale),x+round(x2*scale),y+round(y2*scale)
        crop=image[max(0,b):min(image.shape[0],d),max(0,a):min(image.shape[1],c)]
        if crop.shape[0]>=20 and crop.shape[1]>=20:
            result[slot]=crop.copy()
    return result


def slot_occupied(crop):
    if crop is None or crop.size == 0:return False
    h,w=crop.shape[:2]
    # Interior, away from white key legends/grey bezel and stack digits.
    center=crop[int(h*.43):int(h*.79),int(w*.28):int(w*.78)]
    if center.size == 0:return False
    hsv=cv2.cvtColor(center,cv2.COLOR_BGR2HSV)
    return float(np.mean((hsv[:,:,1]>90)&(hsv[:,:,2]>65)))>.15


def icon_snapshot(crop):
    """Display a full-width potion sprite, with key chrome/count transparent.

    Do not crop the left 19%: Maple quickslot artwork and stacked numbers
    cross that boundary. This operation never affects count OCR inputs.
    """
    if crop is None or crop.size == 0:
        return None
    h,w=crop.shape[:2]
    bgra=cv2.cvtColor(crop,cv2.COLOR_BGR2BGRA)
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    # Key legends and white numerals are low-saturation. Keep the colored
    # sprite, then pad the mask to retain dark anti-aliased outlines.
    pixels=((hsv[:,:,1]>58)&(hsv[:,:,2]>48)).astype(np.uint8)*255
    pixels[:round(h*.16),:]=0  # Ignore decorative title/chrome above icon.
    n,labels,stats,_=cv2.connectedComponentsWithStats(
        cv2.dilate(pixels,np.ones((3,3),np.uint8)),8)
    mask=np.zeros((h,w),np.uint8)
    for k in range(1,n):
        lx,ly,lw,lh,area=(int(v) for v in stats[k])
        # Avoid isolated colored compression noise or tiny label specks.
        if area>=max(6,round(w*h*.008)) and ly+lh>h*.30:
            mask[labels==k]=255
    if np.count_nonzero(mask)>=max(12,round(w*h*.02)):
        mask=cv2.dilate(mask,np.ones((5,5),np.uint8),iterations=1)
        bgra[:,:,3]=mask
    else:
        # Desaturated/unknown sprite: retain interior, but not key labels or
        # the bottom-left count. Do not hallucinate the item identity.
        bgra[:,:,3]=0
        left=round(w*.14);top=round(h*.22)
        bgra[top:round(h*.86),left:w-2,3]=255
        bgra[round(h*.70):,:round(w*.48),3]=0
    # The stack digits are drawn OVER the bottom-left of the item, and the
    # key legend at the top. Both belong to the game HUD rather than the
    # display artwork and must remain invisible in the floating icon.
    bgra[:round(h*.29),:,3]=0
    bgra[:, :round(w*.10),3]=0
    bgra[round(h*.68):,:round(w*.45),3]=0
    # Remove the outermost bezel pixel only. The original v0.4.50 removed
    # ~19% of the LEFT edge, amputating round potion artworks.
    return bgra[1:-1,1:-1].copy() if min(h,w)>5 else bgra


def hud_number_crop(frame):
    """Small EXP-label pixels used for change triggering; not the whole HUD."""
    if frame is None or frame.size==0:return None
    h,w=frame.shape[:2]
    roi=find_exp_label_roi(frame)
    if roi is None:
        return frame[int(h*.925):int(h*.981),int(w*.46):int(w*.68)]
    x1,y1,x2,y2=roi
    return frame[y1:y2,x1:x2]


class ExpChangeGate:
    """Debounce identical HUD crops, but periodically retry even if unchanged.

    Pixel similarity is an optimization only, never evidence of zero XP.
    An unreadable sample is retried promptly and is not committed as baseline.
    """
    def __init__(self, minimum_interval=.16, verify_interval=1.3, retry_interval=.32):
        self.minimum_interval=float(minimum_interval)
        self.verify_interval=float(verify_interval)
        self.retry_interval=float(retry_interval)
        self.last_attempt=-1e9
        self.last_success=-1e9
        self.last_pixels=None
        self.retry_soon=False

    def reset(self):
        self.last_attempt=-1e9
        self.last_success=-1e9
        self.last_pixels=None
        self.retry_soon=False

    @staticmethod
    def fingerprint(frame):
        roi=hud_number_crop(frame)
        if roi is None or roi.size==0:return None
        gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray,(156,30),interpolation=cv2.INTER_AREA)

    def should_read(self, frame, now):
        now=float(now)
        if now-self.last_attempt < self.minimum_interval:return False
        pixels=self.fingerprint(frame)
        changed=(pixels is None or self.last_pixels is None or
                 float(np.mean(cv2.absdiff(pixels,self.last_pixels)))>1.2)
        first=self.last_attempt < -1e8
        due_retry=self.retry_soon and now-self.last_attempt>=self.retry_interval
        due_verify=self.last_success>=0 and now-self.last_success>=self.verify_interval
        if first or ((not self.retry_soon and changed) or due_retry or due_verify):
            self.last_attempt=now
            self.last_pixels=pixels
            return True
        return False

    def result(self, readable, now):
        self.retry_soon=not bool(readable)
        if readable:self.last_success=float(now)


def icon_identity(crop):
    if crop is None or crop.size == 0:return ''
    # Ignore the numeric count and key name; use central potion graphic only.
    h,w=crop.shape[:2]
    region=crop[max(2,int(h*.35)):int(h*.86),int(w*.20):int(w*.80)]
    if region.size<100:return ''
    hsv=cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
    # Hue histogram is stable across changes to stack count and scale.
    # Quantize hue *and* mean value more coarsely than a full histogram.
    # One-pixel OCR/stack-number changes must not reset accumulated counts.
    good=(hsv[:,:,1]>60)&(hsv[:,:,2]>65)
    if np.count_nonzero(good)<8:return ''
    hues=hsv[:,:,0][good]
    sat=hsv[:,:,1][good]
    return f'{int(np.median(hues)//12):02x}{int(np.median(sat)//48):x}{int(np.mean(good)*10):02x}'



def _digit_region(crop):
    """Uncut, numeric-only bottom-left ROI. Used by OCR and diff cache."""
    h,w=crop.shape[:2]
    # The first glyph straddles the tile's LEFT margin; SLOTS includes it.
    # Keep a little of the outlined baseline but exclude most of the sprite.
    return crop[max(0,round(h*.51)):min(h,round(h*.92)),:min(w,round(w*.59))]


def _number_preparations(crop):
    """Independent views of the small outlined game-number raster."""
    small=_digit_region(crop)
    if small.size==0:return []
    image=cv2.resize(small,None,fx=5,fy=5,interpolation=cv2.INTER_NEAREST)
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    white=((hsv[:,:,2]>160)&(hsv[:,:,1]<130)).astype('uint8')*255
    # Classic numerals have light centers with a dark outline. Distinct
    # grayscale and threshold views are inexpensive on this tiny region.
    return [cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(255-white,cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(cv2.threshold(gray,122,255,cv2.THRESH_BINARY)[1],cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(cv2.threshold(gray,175,255,cv2.THRESH_BINARY)[1],cv2.COLOR_GRAY2BGR)]


def _amount_consensus(readings):
    """Strong agreement wins over one weak OCR treatment, never word fragments."""
    groups={}
    for text,score in readings:
        value=recognize_amount(text)
        if value is not None and float(score)>=.47:
            groups.setdefault(value,[]).append(float(score))
    if not groups:return None
    ranked=sorted(groups.items(),key=lambda item:sum(item[1]),reverse=True)
    value,scores=ranked[0]
    strong=sum(c>=.72 for c in scores)
    if len(ranked)>1 and sum(scores)<sum(ranked[1][1])+.45:return None
    if strong>=2 or (len(groups)==1 and max(scores)>=.92):return value
    return None


def read_potion_amount(recognizer, crop):
    return read_potion_amounts(recognizer,{'slot':crop}).get('slot')


def recognize_amount(result):
    if not result:return None
    t=str(result).strip()
    # A Chinese character followed by 67, i1 or 1S is not a numeric reading.
    return int(t) if re.fullmatch(r'[0-9]{1,4}',t) else None


def find_exp_label_roi(frame):
    """Locate the green EXP bar in the bottom HUD, then crop its label."""
    if frame is None or frame.size==0:return None
    h,w=frame.shape[:2]
    offset=round(h*.87)
    bottom=frame[offset:]
    hsv=cv2.cvtColor(bottom,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(34,95,70),(94,255,255))
    count,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
    choices=[]
    for x,y,cw,ch,area in stats[1:]:
        y=int(y)+offset;x=int(x);cw=int(cw);ch=int(ch)
        if (y>=h*.91 and 6<=ch<=55 and cw>=max(28,int(w*.022))
                and cw>=ch*2.5 and area>=cw*4 and w*.38<=x<=w*.78):
            choices.append((cw*ch, x,y,cw,ch))
    if not choices:return None
    _,x,y,cw,ch=max(choices)
    # EXP label starts just above the bright green remaining-progress bar.
    left=max(0,x-round(w*.045));right=min(w,x+max(cw,round(w*.10)))
    top=max(0,y-round(h*.038));bottom=min(h,y+4)
    return (left,top,right,bottom) if right-left>=55 else None


def _read_hud_crop(ocr, crop, label='EXP'):
    """Read a *small label* with recognition first; detector is fallback.

    The game displays ``EXP.`` (with a period), not always ``EXP``.  A
    direct line recognizer is preferable for the fixed single-line status HUD:
    an object detector can discard the small punctuation and digits.
    """
    if crop is None or crop.size == 0:
        return ''
    # Prefer a complete numeric EXP value over a first-pass partial 'EXP' label.
    fallback_text=''
    for scale in (3.0, 2.0):
        enlarged = cv2.resize(crop,None,fx=scale,fy=scale,
                              interpolation=cv2.INTER_CUBIC)
        if hasattr(ocr,'recognize_lines'):
            try:
                result=ocr.recognize_lines([enlarged])
                candidates=list(getattr(result,'txts',None) or [])
                scores=list(getattr(result,'scores',None) or [])
                for t,confidence in zip(candidates,scores):
                    text=str(t).strip()
                    if confidence>=.35 and label in text.upper():
                        if label != 'EXP' or parse_exp_text(text)[1] is not None:
                            return text
                        fallback_text = fallback_text or text
            except Exception:
                pass
    # Preserve the previous detector path as a compatibility fallback.
    try:
        enlarged=cv2.resize(crop,None,fx=2.0,fy=2.0,
                            interpolation=cv2.INTER_CUBIC)
        lines=ocr.detect(enlarged,0,0,1.0)
        detected=' '.join(v.text for v in sorted(lines,key=lambda v:(v.rect[1]//28,v.rect[0]))
                        if v.confidence>=.30)
        return detected if (label != 'EXP' or parse_exp_text(detected)[1] is not None) else (fallback_text or detected)
    except Exception:
        return fallback_text


def read_hud_info(ocr, game_bgr):
    """Return (level, exp, percent, diagnostic) for the actual game HUD.

    An unreadable label is not the same as 0 EXP.  Diagnostics let the user
    distinguish a missing capture/ROI from a bad OCR read without guessing.
    """
    if not ocr or game_bgr is None or game_bgr.size==0:
        return None,None,None,'화면 또는 OCR 엔진 없음'
    h,w=game_bgr.shape[:2]
    if h<150 or w<500:return None,None,None,f'게임 프레임 크기 부족: {w}x{h}'
    rect=find_exp_label_roi(game_bgr)
    exp_rois=[]
    if rect:
        x1,y1,x2,y2=rect
        exp_rois.append(('EXP 게이지 자동 탐지',(y1,y2,x1,x2)))
    exp_rois.extend(_fixed_1080p_exp_boxes(game_bgr.shape))
    # When the green bar is lost to graphics settings or screenshot color,
    # still try the expected bottom HUD.  Do not make up EXP if it fails.
    # A short green bar (low EXP %) is not detected, so this is common.
    exp_rois.append(('게임 하단 HUD 보조 영역',
                     (int(h*.925),int(h*.981),int(w*.46),int(w*.68))))
    level_rois=[('LV 기본',(int(h*.917),int(h*.984),int(w*.16),int(w*.33)))]
    if _is_1080pish(game_bgr.shape):
        level_rois.insert(0,('LV 1080p',(int(h*.905),int(h*.960),int(w*.155),int(w*.305))))
    from .hunt_stats import parse_exp_text
    # Each OCR call costs ~0.3-1.5s on a busy CPU. Try the area that worked
    # last time for this frame size first instead of walking the whole list.
    shape=game_bgr.shape[:2]
    def remembered_first(kind,rois):
        name=_HUD_ROI_MEMORY.get((kind,shape))
        return sorted(rois,key=lambda item:item[0]!=name)
    def crop(box):
        y1,y2,x1,x2=box
        return game_bgr[y1:y2,x1:x2]
    lv=None
    for name,box in remembered_first('lv',level_rois):
        level_text=_read_hud_crop(ocr,crop(box),'LV')
        lv,_,_=parse_exp_text(level_text)
        if lv is not None:
            _HUD_ROI_MEMORY[('lv',shape)]=name
            break
    outputs=[]
    for name,box in remembered_first('exp',exp_rois):
        text=_read_hud_crop(ocr,crop(box))
        outputs.append(f'{name}: {text[:65] or "읽지 못함"}')
        _,exp,pct=parse_exp_text(text)
        if exp is not None:
            _HUD_ROI_MEMORY[('exp',shape)]=name
            return lv,exp,pct,f'{name} 판독: {text[:75]}'
    _HUD_ROI_MEMORY.pop(('exp',shape),None)
    return lv,None,None,' / '.join(outputs)[:180]


# (kind, frame shape) -> name of the HUD area that last gave a reading.
_HUD_ROI_MEMORY={}


def _fixed_1080p_exp_boxes(shape):
    if not _is_1080pish(shape):
        return []
    h,w=shape[:2]
    return [
        ('1080p HUD 고정 EXP 영역',(round(h*0.910),round(h*0.944),round(w*0.475),round(w*0.602))),
        # Classic HUD seen live on a 1920x1080 window: "EXP. 1,952[14.23%]"
        # sits on the bottom status line right of the MP bar.
        ('1080p HUD 하단 EXP 줄',(round(h*0.950),round(h*0.984),round(w*0.520),round(w*0.640))),
        ('1080p HUD 보조 EXP 영역',(round(h*0.905),round(h*0.950),round(w*0.462),round(w*0.615))),
    ]


def read_hud(ocr, game_bgr):
    level,exp,pct,_=read_hud_info(ocr,game_bgr)
    return level,exp,pct


def read_meso(ocr, game_bgr):
    """Visible inventory MESO only; no game-memory access or invented loot."""
    if not ocr or game_bgr is None or game_bgr.size==0:return None
    h,w=game_bgr.shape[:2]
    # Inventory can be moved to any horizontal position. The scan is slow
    # (once every 7 seconds) and requires a visible MESO label.
    roi=game_bgr[int(h*.15):h,0:w]
    if roi.size==0:return None
    try:
        lines=ocr.detect(roi,0,0,1.1)
        texts=' '.join(v.text for v in lines if v.confidence>=.45)
        return parse_meso_text(texts)
    except Exception:return None


def read_potion_amounts(recognizer, crops):
    """Raster recognition first; batch OCR is a conservative fallback."""
    from .stack_digits import match_stack_digits
    final={};pending={}
    for key,crop in crops.items():
        matched=match_stack_digits(crop)
        if matched is not None:final[key]=matched[0]
        else:pending[key]=crop;final[key]=None
    if not recognizer or not pending:return final
    indexed=[];images=[]
    for key,crop in pending.items():
        if crop is None or crop.size==0 or min(crop.shape[:2])<19:continue
        for prep in _number_preparations(crop):
            indexed.append(key);images.append(prep)
    if not images:return final
    try:
        result=recognizer.recognize_lines(images)
        texts=list(getattr(result,'txts',None) or [])
        confs=list(getattr(result,'scores',None) or [])
    except Exception:return final
    choices={key:[] for key in pending}
    for key,text,score in zip(indexed,texts,confs):choices[key].append((text,score))
    for key,reads in choices.items():final[key]=_amount_consensus(reads)
    return final
