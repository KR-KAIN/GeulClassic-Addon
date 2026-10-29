"""Offline Global Classic potion PNGs, with separate capture references.

Only current Classic potions and recovery/buff consumables are loaded. Captured reference
images may confirm artwork, but the displayed bytes are always the clean PNG.
"""
from __future__ import annotations
from pathlib import Path
import os
import sys
import json
import hashlib
from collections import OrderedDict
import cv2
import numpy as np
from .image_io import read_image

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'resources'/'hunt'/'potions'
_CATALOG=json.loads((ROOT/'manifest.json').read_text(encoding='utf8'))
POTIONS={entry['item_id']:entry['name_en'] for entry in _CATALOG['icons']}

def user_root():
    return Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'.local'/'share'))/'KAINMapleTranslator'/'potion-icons'

def _fit(im):
    if im is None or im.size==0:return None
    if im.shape[2]==4:
        alpha=im[:,:,3]>35
        bgr=im[:,:,:3]
    else:
        bgr=im[:,:,:3]
        hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
        alpha=(hsv[:,:,1]>55)&(hsv[:,:,2]>48)
    # Item background, stack digits, letters and chrome should not be used.
    if np.count_nonzero(alpha)<35:return None
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    ys,xs=np.where(alpha)
    x0,x1=max(0,xs.min()-1),min(bgr.shape[1],xs.max()+2)
    y0,y1=max(0,ys.min()-1),min(bgr.shape[0],ys.max()+2)
    if x1-x0<5 or y1-y0<5:return None
    obj=hsv[y0:y1,x0:x1]
    m=alpha[y0:y1,x0:x1].astype('uint8')
    # The thumbnail itself is transparent; compare colors and silhouettes.
    v=cv2.resize(obj,(28,28),interpolation=cv2.INTER_NEAREST)
    a=cv2.resize(m,(28,28),interpolation=cv2.INTER_NEAREST)>0
    return v,a

class PotionIconLibrary:
    def __init__(self, resource=ROOT, user=None):
        self.templates=[];self._raw={};self._references=[];self._slot_templates=[]
        self._cache=OrderedDict();self._scaled={};self._exact={}
        self.aliases={}
        records={}
        for folder in (Path(resource),Path(user) if user else user_root()):
            if not folder.is_dir():continue
            for path in sorted(folder.glob('*.png')):
                if path.stem not in POTIONS:continue
                if path.stat().st_size>150_000:continue
                raw=read_image(path,cv2.IMREAD_UNCHANGED)
                if raw is None or raw.ndim!=3 or raw.shape[2]!=4:continue
                records[path.stem]=(raw,path.read_bytes())
        groups={}
        for name,(raw,png) in sorted(records.items()):
            digest=hashlib.blake2b(raw.tobytes()+str(raw.shape).encode(),digest_size=16).digest()
            canonical=groups.setdefault(digest,name)
            self.aliases[name]=canonical
            if canonical!=name:continue
            self._raw[name]=raw;self._exact[digest]=name
            self._slot_templates.append((name,raw,png,name))
            feat=_fit(raw)
            self.templates.append((name,feat,png))
        display={name:blob for name,_,blob in self.templates}
        for filename,name in _CATALOG.get('reference_images',{}).items():
            path=Path(resource)/filename
            canonical=self.aliases.get(name)
            if canonical not in display or not path.is_file():continue
            raw=read_image(path,cv2.IMREAD_UNCHANGED)
            if raw is not None:
                feat=_fit(raw)
                if feat is not None:self._references.append((canonical,feat,display[canonical]))
                self._slot_templates.append((canonical,raw,display[canonical],filename))

    def _slot_scores(self, icon, refine=None):
        """Match intact art at multiple HUD scales; stack digits are excluded."""
        bgr=icon[:,:,:3]
        h,w=bgr.shape[:2]
        background=np.median(bgr.reshape(-1,3),axis=0)
        scales=sorted(set(round(v,3) for v in (1.,*(w/49*f for f in (.75,.85,.92,1.,1.08,1.15,1.25,1.4)))))
        if refine:
            scales=sorted({round(v+delta,3) for v in scales for delta in (-.025,-.0125,0.,.0125,.025)})
        scores=[]
        for name,raw,png,template_id in self._slot_templates:
            if refine and name not in refine:continue
            best=0.
            for scale in scales:
                key=(template_id,scale)
                if key not in self._scaled:
                    tw,th=max(1,round(raw.shape[1]*scale)),max(1,round(raw.shape[0]*scale))
                    self._scaled[key]=cv2.resize(raw,(tw,th),interpolation=cv2.INTER_AREA)
                ref=self._scaled[key]
                rh,rw=ref.shape[:2]
                if rh>h or rw>w or min(rh,rw)<9:continue
                alpha=ref[:,:,3:4].astype(np.float32)/255.
                template=np.uint8(ref[:,:,:3]*alpha+background*(1-alpha))
                mask=np.ones((rh,rw),np.uint8)
                mask[round(rh*.65):,:round(rw*.4)]=0
                matches=cv2.matchTemplate(bgr,template,cv2.TM_CCOEFF_NORMED,mask=mask)
                matches=np.nan_to_num(matches,nan=-1.,posinf=-1.,neginf=-1.)
                _,correlation,_,(x,y)=cv2.minMaxLoc(matches)
                if correlation<.50:continue
                observed=bgr[y:y+rh,x:x+rw]
                ref_hsv=cv2.cvtColor(ref[:,:,:3],cv2.COLOR_BGR2HSV)
                got_hsv=cv2.cvtColor(observed,cv2.COLOR_BGR2HSV)
                colored=(ref[:,:,3]>160)&(ref_hsv[:,:,1]>65)&(ref_hsv[:,:,2]>55)&(mask>0)
                if colored.sum()>=12:
                    hue=np.abs(ref_hsv[:,:,0].astype(float)-got_hsv[:,:,0]);hue=np.minimum(hue,180-hue)
                    # A hard 16-degree pass let red/orange/yellow potions
                    # tie despite different liquids. Preserve their hue gap.
                    color=float(np.mean(np.exp(-.5*(hue[colored]/6.)**2)*
                                        (got_hsv[:,:,1][colored]>55)))
                else:
                    opaque=(ref[:,:,3]>180)&(mask>0)
                    color=1.-min(1.,float(np.mean(cv2.absdiff(observed,template)[opaque]))/85.) if opaque.any() else 0.
                best=max(best,.72*float(correlation)+.28*color)
            if best:scores.append((best,name,png))
        return scores

    def identify(self, icon, min_score=.84, gap=.055):
        if icon is None or icon.size==0 or icon.ndim!=3 or icon.shape[2] not in (3,4):return None
        digest=hashlib.blake2b(icon.tobytes()+str(icon.shape).encode(),digest_size=16).digest()
        if digest in self._exact:
            name=self._exact[digest]
            return next((name,png,1.) for n,_,png in self.templates if n==name)
        # Counts change over the lower-left artwork. Reuse a positive match
        # from the remaining sprite, so every consumed potion need not cause
        # another catalogue scan or briefly change the tracked slot identity.
        art=icon.copy();h,w=art.shape[:2]
        art[:round(h*.29)]=0
        art[round(h*.51):,:round(w*.59)]=0
        art_key=b'art'+hashlib.blake2b(art.tobytes()+str(art.shape).encode(),digest_size=16).digest()
        if art_key in self._cache:
            self._cache.move_to_end(art_key);return self._cache[art_key]
        if digest in self._cache:
            self._cache.move_to_end(digest);return self._cache[digest]
        candidates=self._slot_scores(icon)
        top=sorted(candidates,reverse=True,key=lambda v:v[0])
        if top and .72<=top[0][0]<.92:
            # A one-pixel size change matters on a 16px bottle. Refine only
            # plausible candidates, instead of scanning every icon densely.
            candidates.extend(self._slot_scores(icon,{v[1] for v in top[:2]}))
        # References from the actual user capture tolerate the game's reduced
        # HUD raster. Their IDs resolve back to canonical, full-width PNGs.
        from .hunt_capture import icon_snapshot
        preview=icon_snapshot(icon[:,:,:3]) if icon.shape[2]==3 else icon
        candidates.extend(self._reference_scores(preview))
        best={}
        for score,name,png in candidates:
            if score>best.get(name,(0.,name,png))[0]:best[name]=(score,name,png)
        ranked=sorted(best.values(),reverse=True,key=lambda v:v[0])
        value=None
        if ranked and ranked[0][0]>=min_score and (len(ranked)<2 or ranked[0][0]-ranked[1][0]>=gap):
            first=ranked[0];value=(first[1],first[2],round(first[0],3))
        self._cache[art_key if value else digest]=value
        while len(self._cache)>64:self._cache.popitem(last=False)
        while len(self._scaled)>600:self._scaled.pop(next(iter(self._scaled)))
        return value

    def _reference_scores(self, icon):
        item=_fit(icon)
        if item is None:return []
        hsv,mask=item
        candidates=[]
        for name,(ref,refmask),png in self._references:
            common=mask & refmask
            if common.sum()<110:continue
            # Median circular hue distance and silhouette shape penalize
            # visually similar but different potion colors.
            hue=np.abs(hsv[:,:,0].astype(float)-ref[:,:,0])
            hue=np.minimum(hue,180-hue)
            hsv_score=1.-min(1.,float(np.median(hue[common]))/42.)
            saturation=1.-min(1.,float(np.mean(np.abs(hsv[:,:,1].astype(float)[common]-ref[:,:,1][common])))/150.)
            shape=float(np.count_nonzero(common))/max(1,float(np.count_nonzero(mask|refmask)))
            score=.45*hsv_score+.19*saturation+.36*shape
            candidates.append((score,name,png))
        return candidates
