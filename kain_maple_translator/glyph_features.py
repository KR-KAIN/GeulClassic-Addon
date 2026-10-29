"""Optional glyph capture diagnostics. No OCR inference is changed here."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import cv2
import numpy as np
from .core import config_path


def glyph_mask(neutral):
    """Use exactly the already background-neutralized ink image."""
    gray = neutral[:, :, 0] if neutral.ndim == 3 else neutral
    return (gray < 205).astype(np.uint8)


def separate_glyphs(neutral):
    """Column projection with strict sanity checks; return [] when ambiguous."""
    mask = glyph_mask(neutral)
    h,w=mask.shape
    if h<6 or w<2 or not mask.any():
        return []
    occupied=np.flatnonzero(mask.any(axis=0))
    ranges=[]
    a=prev=int(occupied[0])
    for idx in occupied[1:]:
        idx=int(idx)
        if idx>prev+1:
            ranges.append((a,prev+1));a=idx
        prev=idx
    ranges.append((a,prev+1))
    # Text touches boundaries or merged glyphs in bitmap fonts. Reject it
    # rather than teaching a dictionary a misleading character shape.
    if len(ranges)>200 or any(b-a>h*1.3 for a,b in ranges):
        return []
    pieces=[]
    for a,b in ranges:
        ys=np.flatnonzero(mask[:,a:b].any(axis=1))
        if not ys.size:
            return []
        top,bottom=int(ys[0]),int(ys[-1]+1)
        pixels=mask[top:bottom,a:b]
        if pixels.size==0 or np.count_nonzero(pixels)<2:
            return []
        # Each glyph retains original bitmap proportions; no collisions
        # from resampling or perceptual matching.
        key=hashlib.blake2b(pixels.tobytes()+f':{pixels.shape}'.encode(),digest_size=16).hexdigest()
        pieces.append((key,(a,top,b-a,bottom-top)))
    return pieces


def dominant_ink_color(original, neutral):
    mask=glyph_mask(neutral).astype(bool)
    if not mask.any():return 'unknown'
    colors=original[:,:,:3][mask]
    b,g,r=(int(x) for x in np.median(colors,axis=0))
    return f'{r//16:01x}{g//16:01x}{b//16:01x}'


def row_category(original, rect):
    from .megaphone import detect_band
    try:
        tone=detect_band(original,(0,0,original.shape[1],original.shape[0])).tone
    except Exception: tone='none'
    return tone if tone!='none' else 'normal'


class GlyphDebugRecorder:
    def __init__(self, enabled=False, folder=None, limit=40):
        self.enabled=bool(enabled)
        self.folder=Path(folder) if folder else config_path().parent/'diagnostics'/'glyph-crops'
        self.limit=int(limit)
        self.taken=0
        self.categories={}
        self.records=[]
        self.matched=0
        self.attempted=0
        self.failed=0

    def capture(self, row, category='normal'):
        if not self.enabled or self.taken>=self.limit:return
        # Four category quotas so one fast-moving normal channel cannot consume
        # all forty screenshots before megaphone/system text appears.
        caps={'normal':10,'yellow':10,'gray':10,'pink':10}
        group=category if category in caps else 'other'
        quota=caps.get(group,10)
        if self.categories.get(group,0)>=quota:return
        self.folder.mkdir(parents=True,exist_ok=True)
        index=self.taken+1
        prefix=f'line-{index:02d}-{group}'
        pieces=separate_glyphs(row.neutral)
        original=row.original
        cv2.imwrite(str(self.folder/(prefix+'-original.png')),original,[cv2.IMWRITE_PNG_COMPRESSION,0])
        preview=original.copy()
        for _,(x,y,w,h) in pieces:
            cv2.rectangle(preview,(x,y),(x+w-1,y+h-1),(0,255,255),1)
        cv2.imwrite(str(self.folder/(prefix+'-columns.png')),preview,[cv2.IMWRITE_PNG_COMPRESSION,0])
        self.taken=index
        self.categories[group]=self.categories.get(group,0)+1

    def observe(self, neutral, recognized):
        if not self.enabled:return
        self.attempted+=1
        glyphs=separate_glyphs(neutral)
        if not glyphs:
            self.failed+=1
        elif len(glyphs)==len(recognized or ''):
            self.matched+=1

    def stats(self):
        return {'glyph_debug_split_match_ratio':round(self.matched/max(1,self.attempted),4),
                'glyph_debug_split_failure_ratio':round(self.failed/max(1,self.attempted),4),
                'glyph_debug_saved_lines':self.taken}
