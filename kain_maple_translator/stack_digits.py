"""Read outlined quickslot numbers using the game's bundled ItemNo glyphs.

The matcher uses only the count baseline and keeps alternate glyph scores;
empty keys and ambiguous partial strings are not quantities.
"""
from functools import lru_cache
from pathlib import Path
import sys
import cv2
import numpy as np
from .image_io import read_image


@lru_cache(maxsize=1)
def _glyphs():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'resources/hunt/digits'
    return {str(d):im for d in range(10)
            if (im:=read_image(root/f'{d}.png',cv2.IMREAD_UNCHANGED)) is not None}


def match_stack_digits(crop):
    """Return (integer, confidence), or None, without using a language model."""
    if crop is None or crop.size==0:return None
    h,w=crop.shape[:2]
    if min(h,w)<19 or len(_glyphs())!=10:return None
    # Only the lower strip can contain stack digits; avoid matching key labels.
    top=round(h*.46)
    gray=cv2.cvtColor(crop[top:],cv2.COLOR_BGR2GRAY).astype(np.float32)
    hint=_SCALE_HINT.get(w)
    if hint is not None:
        # Same keyboard, same glyph size: search only near the size that
        # read a count last time (~4x faster than all 33 sizes).
        # The width is the cache key, so a resized keyboard gets a new entry.
        return _match(crop,gray,h,w,top,np.arange(max(.95,hint-.1),min(1.76,hint+.101),.025))
    return _match(crop,gray,h,w,top,np.arange(.95,1.76,.025))


# crop width -> glyph size factor that last produced a count
_SCALE_HINT={}


def _match(crop,gray,h,w,top,factors):
    maps={};first=[]
    for factor in factors:
        scale=float(factor)*w/49.
        for digit,ref in _glyphs().items():
            rw,rh=round(ref.shape[1]*scale),round(ref.shape[0]*scale)
            tag=(digit,rw,rh)
            if tag in maps or min(rw,rh)<3 or rh>gray.shape[0] or rw>gray.shape[1]:continue
            im=cv2.resize(ref,(rw,rh),interpolation=cv2.INTER_LINEAR)
            mask=(im[:,:,3]>100).astype(np.uint8)*255
            target=cv2.cvtColor(im[:,:,:3],cv2.COLOR_BGR2GRAY).astype(np.float32)
            scores=cv2.matchTemplate(gray,target,cv2.TM_CCOEFF_NORMED,mask=mask)
            scores=np.nan_to_num(scores,nan=-1.,posinf=-1.,neginf=-1.)
            maps[tag]=scores
            x0=round(w*.07);x1=min(scores.shape[1],round(w*.25))
            y0=max(0,round(h*.40)-top)
            y1=min(scores.shape[0],round(h*1.00)-rh-top+1)
            if x1<=x0 or y1<=y0:continue
            _,score,_,(x,y)=cv2.minMaxLoc(scores[y0:y1,x0:x1])
            first.append((score,digit,x+x0,y+y0,rw,rh,scale))
    if not first:return None
    first.sort(reverse=True)
    # A lone '1' is a plain bar that also fits at the wrong scale, where
    # the next digit then fails and "15" silently became "1". Read from the
    # best first-digit candidate of several scales and prefer the complete
    # reading: a shorter result that is a prefix of a good longer one is a
    # truncation, never a different count.
    readings=[];tried=set()
    for cand in first:
        if len(tried)>=6 or cand[0]<.71:break
        key=(cand[1],round(cand[6],2))
        if key in tried:continue
        tried.add(key)
        same_scale=[v[0] for v in first if v[1]!=cand[1] and abs(v[6]-cand[6])<.03]
        if cand[0]-max(same_scale,default=-1.)<.055:continue
        reading=_read_digits(maps,cand)
        if reading is not None:readings.append(reading)
    if not readings:return None
    readings.sort(key=lambda item:item[1],reverse=True)
    best=readings[0]
    # Every reading already passed the per-digit and mean-quality checks, so
    # a longer one that extends the best is the full count ('10', not '1').
    for other in readings[1:]:
        if len(other[0])>len(best[0]) and other[0].startswith(best[0]):
            best=other
    if any(not best[0].startswith(t) and not t.startswith(best[0]) and q>=best[1]-.02
           for t,q,*_ in readings if t!=best[0]):
        return None  # two different, equally good counts: unknown
    if best[0].strip('1'):
        # A plain '1' bar fits many sizes; learn the size only from others.
        _SCALE_HINT[w]=best[3]*49./w
    return int(best[0]),best[2]


def _read_digits(maps,cand):
    """Follow digits to the right of one first-digit candidate."""
    score,digit,x,y,rw,rh,scale=cand
    text=digit;qualities=[score]
    for _ in range(3):
        options=[]
        for (char,tw,th),scores in maps.items():
            if abs(th-rh)>1 or y>=scores.shape[0]:continue
            ax=max(0,round(x+rw-scale*.3))
            bx=min(scores.shape[1],round(x+rw+scale*3)+1)
            if ax>=bx:continue
            # Glyphs share a top baseline; a one-pixel vertical search falsely
            # interprets the right half of a zero as a four.
            _,v,_,(dx,_dy)=cv2.minMaxLoc(scores[y:y+1,ax:bx])
            options.append((v,char,dx+ax,y,tw,th))
        if not options:break
        options.sort(reverse=True)
        v,char,nx,ny,tw,th=options[0]
        other=max((a[0] for a in options if a[1]!=char),default=-1.)
        if v<.50:break  # clear space after the final digit
        if v<.66 or v-other<.045:return None  # unreadable suffix, never truncate
        text+=char;qualities.append(v)
        x,y,rw,rh=nx,ny,tw,th
    if len(text)>1 and text.startswith('0'):return None
    if float(np.mean(qualities))<.73:return None
    return text,float(np.mean(qualities)),float(min(qualities)),float(scale)
