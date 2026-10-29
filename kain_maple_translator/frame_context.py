"""Pixel-first scrollbar/context checks; unknown UI stays explicitly unknown."""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class FrameContext:
    at_bottom: bool | None = None
    gutter: tuple | None = None


def inspect_scrollbar(image):
    h,w=image.shape[:2]
    if h<55 or w<120:
        return FrameContext()
    start=max(0,w-32)
    hsv=cv2.cvtColor(image[:,start:,:3],cv2.COLOR_BGR2HSV)
    b,g,r=[image[:,start:,:3][:,:,i].astype('int16') for i in range(3)]
    track=(b-r>9)&(g-r>4)&(b>145)&(g>125)&(hsv[:,:,1]<100)
    coverage=np.mean(track,axis=0)
    xs=np.flatnonzero(coverage>.14)
    blue=(hsv[:,:,0]>=88)&(hsv[:,:,0]<=120)&(hsv[:,:,1]>65)&(hsv[:,:,2]>65)
    # Slate chat banners can occupy the same pale-blue colour range as the
    # rail. Their horizontal pixels used to widen xs beyond 25px, making a
    # perfectly visible scrollbar disappear whenever such a message arrived.
    # Anchor a bounded rail to a filled vertical thumb and its pale flanks;
    # never infer a gutter from chat colour or a right-edge letter alone.
    if xs.size>=6 and xs[-1]-xs[0]>25:
        candidates=[]
        thumb_mask=blue[12:max(13,h-12)].astype('uint8')
        _,_,components,_=cv2.connectedComponentsWithStats(thumb_mask,8)
        for tx,ty,tw,th,area in components[1:]:
            if not (3<=tw<=20 and th>=7 and area>=20 and area>=tw*th*.50):
                continue
            lo=max(0,int(tx)-3);hi=min(track.shape[1],int(tx+tw)+2)
            local=coverage[lo:hi]
            flanks=np.r_[coverage[lo:tx],coverage[tx+tw:hi]]
            if (np.count_nonzero(local>.14)>=6 and
                    np.count_nonzero(flanks>.45)>=2):
                candidates.append((int(tx+tw),int(area),lo,hi))
        if candidates:
            _,_,lo,hi=max(candidates)
            xs=np.arange(lo,hi)
    if xs.size<6 or xs[-1]-xs[0]>25 or float(np.max(coverage))<.45:
        return FrameContext()
    x0,x1=int(xs[0]),int(xs[-1])+1
    # Ignore up/down button icons when locating the draggable blue thumb.
    thumb=blue[12:max(13,h-12),x0:x1].astype('uint8')
    n,lab,stats,_=cv2.connectedComponentsWithStats(thumb,8)
    found=[]
    for x,y,ww,hh,area in stats[1:]:
        if ww>=3 and hh>=7 and area>=20:
            found.append((area,y+12,hh))
    if not found:
        return FrameContext()
    _,y,hh=max(found)
    # Require a substantial, broad pale-blue rail so ordinary blue glyphs
    # along the screen edge cannot pause chat collection.
    bottom = y+hh >= h-12-max(6,(h-24)*.12)
    if not bottom:
        bottom = _thumb_touches_down_button(blue[:,x0:x1],y,hh,h)
    return FrameContext(bool(bottom),(start+x0,0,x1-x0,h))


def _thumb_touches_down_button(blue,thumb_top,thumb_height,h):
    """Measure the thumb against the actual down-arrow button.

    The fixed 12px button margin only holds when the ROI ends at the button.
    At 1920x1080 the automatic ROI extends ~8px below the scrollbar and the
    button is taller, so a thumb resting on the button was reported as
    'browsing history' and every live frame was skipped. Use the observed
    button top instead; the rail gap at the bottom is the same 5-6px at
    1366x768 and 1920x1080.
    """
    rows=np.mean(blue,axis=1)>.35
    below=thumb_top+thumb_height
    ys=np.flatnonzero(rows[below:])
    if not ys.size:
        return False
    button_top=below+int(ys[0])
    run_end=button_top
    while run_end<h and rows[run_end]:
        run_end+=1
    button_height=run_end-button_top
    # A real arrow button, not a stray blue pixel row, and nothing but the
    # narrow rail between thumb and button.
    if button_height<max(6,thumb_height*.25) or button_height>thumb_height*1.2:
        return False
    return button_top-below <= max(6,round(button_height*.55))


def without_scrollbar(image, context):
    if context.gutter is None:
        return image
    x,y,w,h=context.gutter
    out=image.copy()
    # The rail's 1px frame lies just left of its blue track. Leaving it in
    # place connects every text baseline into a tall, rejected OCR block.
    x=max(0,x-6)
    from .ink_background import row_background
    background=row_background(image[:,:max(1,x-2),:3]).astype('uint8')
    out[:,x:,:3]=background[:,None,:]
    return out
