"""Detect the classic Maple chat HUD from a WGC CLIENT frame (no screen selection).

Bounded, conservative visual recognition of the chat input bar's blue '전체'
button; returns a screen-space chat ROI. Does not run OCR on the whole game.
When UI skins/resolutions don't match, caller can fall back to a labelled
geometry estimate. This module never reads game memory or packets.
"""
from __future__ import annotations
from dataclasses import dataclass

import cv2
import numpy as np

from .layout import estimate_chat_area

@dataclass(frozen=True)
class ChatLocation:
    region: dict
    method: str
    confidence: float


def estimate(game_rect: tuple[int,int,int,int]) -> ChatLocation:
    x,y,w,h=estimate_chat_area(game_rect)
    return ChatLocation(dict(left=x,top=y,width=w,height=h), 'geometry-estimate', .20)


def detect_chat_region(client_bgr: np.ndarray, game_rect: tuple[int,int,int,int]) -> ChatLocation | None:
    """Find the blue '전체' button near the Maple bottom-center chat HUD.

    The only search area is the expected bottom HUD band, never the minimap,
    characters, or game scene. Absence is not treated as a confident match.
    """
    if client_bgr is None or client_bgr.ndim!=3 or client_bgr.shape[2]<3:
        return None
    fh,fw=client_bgr.shape[:2]
    gx,gy,gw,gh=map(int,game_rect)
    if min(fw,fh,gw,gh)<100:
        return None
    # WGC full-client images are in CLIENT-local pixel coordinates; allow DPI
    # scaling only when both axes have the same scale.
    sx,sy=fw/gw,fh/gh
    if abs(sx-sy)>.045 or not (.75<=sx<=2.10):
        return None
    ref=estimate_chat_area((0,0,gw,gh))
    rx,ry,rw,rh=ref
    scale=min(gw/1366.0,gh/768.0)
    # Blue chat selector is immediately below the displayed chat lines.
    xmin=max(0,round((rx-max(105,130*scale))*sx))
    xmax=min(fw,round((rx+max(180,220*scale))*sx))
    ymin=max(0,round((ry+rh-max(46,52*scale))*sy))
    ymax=min(fh,round((ry+rh+max(45,52*scale))*sy))
    if xmax-xmin<45 or ymax-ymin<15:
        return None
    sample=client_bgr[ymin:ymax,xmin:xmax,:3]
    hsv=cv2.cvtColor(sample,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv, (92,50,38), (119,255,215))
    # Join text knockouts within the solid blue button; avoid connecting
    # unrelated HUD components across large spaces.
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(max(4,int(11*sx*scale)),3))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel)
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    best=None
    expect_x=(rx+45*scale)*sx
    expect_y=(ry+rh+7*scale)*sy
    for c in contours:
        x,y,w,h=cv2.boundingRect(c)
        cx=xmin+x+w/2;cy=ymin+y+h/2
        physical_w=w/sx;physical_h=h/sy
        if not (42*scale<=physical_w<=155*scale and 13*scale<=physical_h<=39*scale):
            continue
        if not (2.7<=w/max(1,h)<=9.0):
            continue
        if not (0.43 <= cv2.contourArea(c)/max(1,w*h) <= 1.05):
            continue
        dx=abs(cx-expect_x)/max(32,100*scale*sx)
        dy=abs(cy-expect_y)/max(16,30*scale*sy)
        score=1.0-0.34*dx-0.42*dy
        if score<.48:
            continue
        if best is None or score>best[0]:
            best=(score,xmin+x,ymin+y,w,h)
    if best is None:
        return None
    score,bx,by,bw,bh=best
    # The top of the chat input bar is the bottom of the chat OCR region.
    # Restrict ROI to the message pane; exclude the blue selector and HP/MP bars.
    width=rw
    height=rh
    left=gx+round(bx/sx)
    top=gy+round(by/sy)-height-round(3*scale)
    left=max(gx,min(left,gx+gw-width))
    top=max(gy,min(top,gy+gh-height))
    return ChatLocation(dict(left=left,top=top,width=width,height=height),
                        'visual-chat-toolbar',round(max(0.,min(1.,score)),3))


def local_crop(client: np.ndarray, game_rect: tuple[int,int,int,int], region: dict) -> np.ndarray:
    """Crop client frame using the same coordinates as region (BGR copy)."""
    gx,gy,gw,gh=game_rect
    fh,fw=client.shape[:2]
    x=round((region['left']-gx)*fw/gw)
    y=round((region['top']-gy)*fh/gh)
    w=round(region['width']*fw/gw)
    h=round(region['height']*fh/gh)
    if x<0 or y<0 or x+w>fw or y+h>fh or w<50 or h<25:
        raise ValueError('Auto located chat crop outside client frame')
    return np.ascontiguousarray(client[y:y+h,x:x+w,:3])
