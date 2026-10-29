"""Detect the classic Maple chat HUD from a WGC CLIENT frame (no screen selection).

Bounded, conservative visual recognition of the chat input bar's blue '전체'
button; returns a screen-space chat ROI and the game's UI scale. Does not run
OCR on the whole game. When UI skins/resolutions don't match, caller can fall
back to a labelled geometry estimate. This module never reads game memory or
packets.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

import cv2
import numpy as np

from .layout import (CHAT_HEIGHT, CHAT_WIDTH, estimate_chat_area,
                     game_ui_scale)

# The blue chat-target button ('전체', '파티', ...) at UI scale 1.0, measured
# from the client's bottom centre on 1280x720, 1366x768, 1920x1200 and
# 2560x1440 clients (both UI size settings). The game keeps the whole bottom
# HUD centred, so the button's right edge alone tells the UI scale.
BUTTON_W = 80
BUTTON_RIGHT_FROM_CENTRE = 316
BUTTON_BOTTOM_FROM_BOTTOM = 44     # bottom of its colour blob, dark rim included
BUTTON_BLOB_H = 18
# The chat text sits this far above the button's bottom edge.
CHAT_TOP_ABOVE_BUTTON = 90


@dataclass(frozen=True)
class ChatLocation:
    region: dict
    method: str
    confidence: float
    scale: float = 0.0


def estimate(game_rect: tuple[int,int,int,int]) -> ChatLocation:
    x,y,w,h=estimate_chat_area(game_rect)
    return ChatLocation(dict(left=x,top=y,width=w,height=h), 'geometry-estimate', .20,
                        game_ui_scale(game_rect[2],game_rect[3]))


def _snap(scale: float, guess: float) -> float:
    """Measured scale, snapped to the two values the game itself uses."""
    for exact in (guess, float(round(scale))):
        if exact >= 1.0 and abs(scale-exact) <= .03*exact:
            return exact
    return scale


def _light_fraction(hsv: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> float:
    """Share of near-white pixels in a frame box (the chat input field)."""
    h,w=hsv.shape[:2]
    x0,x1=max(0,x0),min(w,x1)
    y0,y1=max(0,y0),min(h,y1)
    if x1-x0<4 or y1-y0<2:
        return 0.0
    box=hsv[y0:y1,x0:x1]
    light=(box[...,2]>=190)&(box[...,1]<=60)
    return float(light.mean())


def detect_chat_region(client_bgr: np.ndarray, game_rect: tuple[int,int,int,int]) -> ChatLocation | None:
    """Find the blue chat-target button next to the white chat input field.

    The only search area is the bottom HUD band, never the minimap,
    characters, or game scene. The button's position gives the game's UI
    scale (the HUD stays centred), so '기본 비율' and '최적 비율' both work.
    Absence is not treated as a confident match.
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
    guess=game_ui_scale(gw,gh)
    lo=.9
    hi=max(guess,float(math.ceil(guess)))*1.08
    centre=gw/2
    # Search box, client pixels: from the button's left edge at the largest
    # scale to its right edge at the smallest, bottom HUD rows only.
    x0=centre-(BUTTON_RIGHT_FROM_CENTRE+BUTTON_W)*hi-12
    x1=centre-BUTTON_RIGHT_FROM_CENTRE*lo+12
    y0=gh-(BUTTON_BOTTOM_FROM_BOTTOM+BUTTON_BLOB_H)*hi-12
    y1=gh-BUTTON_BOTTOM_FROM_BOTTOM*lo+10
    xmin=max(0,round(x0*sx));xmax=min(fw,round(x1*sx))
    ymin=max(0,round(y0*sy));ymax=min(fh,round(y1*sy))
    if xmax-xmin<45 or ymax-ymin<15:
        return None
    sample=client_bgr[ymin:ymax,xmin:xmax,:3]
    hsv=cv2.cvtColor(sample,cv2.COLOR_BGR2HSV)
    raw=cv2.inRange(hsv, (92,50,38), (119,255,215))
    # Join the white letter knockouts inside the solid blue button.
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(max(4,int(9*sx*guess)),3))
    mask=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,kernel)
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    # The input field right of the button sits outside the sample box.
    full_hsv=None
    best=None
    for c in contours:
        x,y,w,h=cv2.boundingRect(c)
        right=(xmin+x+w)/sx
        bottom=(ymin+y+h)/sy
        s=(centre-right)/BUTTON_RIGHT_FROM_CENTRE
        if not (lo<=s<=hi):
            continue
        width=w/sx;height=h/sy
        # The whole button must be there; a character standing against its
        # left end may widen the blob, never shorten it.
        if not (.85*BUTTON_W*s<=width<=1.9*BUTTON_W*s):
            continue
        if not (.7*BUTTON_BLOB_H*s<=height<=2.2*BUTTON_BLOB_H*s):
            continue
        dy=abs(bottom-(gh-BUTTON_BOTTOM_FROM_BOTTOM*s))/(3*s+2)
        if dy>1.6:
            continue
        # Solid blue across the button's own box (letters allowed).
        bl=round((right-BUTTON_W*s)*sx)-xmin
        br=round(right*sx)-xmin
        bt=round((bottom-BUTTON_BLOB_H*s+3*s)*sy)-ymin
        bb=round((bottom-3*s)*sy)-ymin
        core=raw[max(0,bt):max(0,bb),max(0,bl):max(0,br)]
        fill=float((core>0).mean()) if core.size else 0.0
        if fill<.45:
            continue
        if full_hsv is None:
            band0=max(0,ymin-4)
            full_hsv=(band0,cv2.cvtColor(client_bgr[band0:min(fh,ymax+4),:,:3],cv2.COLOR_BGR2HSV))
        band0,band=full_hsv
        field=_light_fraction(band,round((right+5*s)*sx),round((right+70*s)*sx),
                              round((bottom-13*s)*sy)-band0,round((bottom-6*s)*sy)-band0)
        if field<.5:
            continue
        extra=max(0.0,width/(BUTTON_W*s)-1.0)
        score=1.0-.22*dy-.35*extra-.3*(1.0-fill)-.25*(1.0-field)
        if score<.48:
            continue
        if best is None or score>best[0]:
            best=(score,right,bottom,s)
    if best is None:
        return None
    score,right,bottom,s=best
    s=_snap(s,guess)
    # The top of the chat input bar is the bottom of the chat OCR region.
    # Restrict ROI to the message pane; exclude the blue selector and HP/MP bars.
    width=max(160,min(gw,round(CHAT_WIDTH*s)))
    height=max(35,min(160,round(CHAT_HEIGHT*s)))
    left=gx+round(right-BUTTON_W*s)
    top=gy+round(bottom-CHAT_TOP_ABOVE_BUTTON*s)
    left=max(gx,min(left,gx+gw-width))
    top=max(gy,min(top,gy+gh-height))
    return ChatLocation(dict(left=left,top=top,width=width,height=height),
                        'visual-chat-toolbar',round(max(0.,min(1.,score)),3),round(s,4))


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
