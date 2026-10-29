"""Conservative calibrated badge split; no match always keeps full-line OCR."""
from pathlib import Path
import sys
import cv2
import numpy as np
from .image_io import read_image


def delimiter_pairs(neutral, start=12, end=None):
    """Pixel evidence for ':' or ';', before OCR and outside message text."""
    height,width=neutral.shape[:2]
    end=min(width-12, int(width*.60)) if end is None else min(width-12,end)
    binary=(neutral[:,:,0]<115).astype('uint8')
    _,_,stats,_=cv2.connectedComponentsWithStats(binary,8)
    dots=[]
    for bx,by,bw,bh,area in stats[1:]:
        if (start<=bx<=end and 1<=bw<=max(5,round(height*.22)) and
                1<=bh<=max(6,round(height*.30)) and 2<=area<=max(24,height*1.1)):
            dots.append((int(bx),int(by),int(bw),int(bh)))
    pairs=[]
    for a in dots:
        for b in dots:
            if (abs(a[0]-b[0])<=max(2,round(height*.10)) and
                    max(3,height*.13)<=b[1]-a[1]<=min(14,height*.65)):
                left=min(a[0],b[0])
                right=max(a[0]+a[2],b[0]+b[2])
                pairs.append((left,right+2))
    return sorted(set(pairs))


class BadgeSplitter:
    def __init__(self, template=None):
        path = Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'resources/chat-templates/channel-coin.png'
        self.template = template if template is not None else read_image(path)

    def locate_rows(self, image):
        """Locate verified CH sprites even where background hid a baseline."""
        template=self.template
        if template is None or image.shape[1]<160:
            return []
        height,width=image.shape[:2]
        white=(np.min(image,axis=2)>185).astype('uint8')
        _,_,components,_=cv2.connectedComponentsWithStats(white,8)
        candidates=[]
        for scale in (.8,1.,1.25,1.5,2.):
            tw,th=round(template.shape[1]*scale),round(template.shape[0]*scale)
            if th>height or tw>width*.55 or min(tw,th)<6:
                continue
            target=cv2.resize(template,(tw,th),interpolation=cv2.INTER_CUBIC)
            scores=cv2.matchTemplate(image[:,:max(60,int(width*.55))],target,cv2.TM_CCOEFF_NORMED)
            ys,xs=np.where(scores>=.82)
            for y,x in zip(ys,xs):
                for bx,by,bw,bh,area in components[1:]:
                    if (th*2.1<=bw<=th*4.8 and th*.6<=bh<=th*1.6 and
                            area>=bw*bh*.12 and bx>=15 and bx<=x+tw/2<=bx+bw and
                            by-2<=y+th/2<=by+bh+2 and
                            0<=bx+bw-(x+tw/2)<=tw*1.2):
                        candidates.append((float(scores[y,x]),int(y),th))
                        break
        found=[]
        for quality,y,th in sorted(candidates,reverse=True):
            if any(abs(y+th/2-(yy+hh/2))<min(th,hh)*.7 for yy,hh in found):
                continue
            found.append((y,th))
        return sorted(found)

    def split(self, original, neutral):
        template = self.template
        if template is None or original.shape[1] < 110:
            return None
        height,width = original.shape[:2]
        candidates=[]
        for scale in (.8,1.,1.25,1.5,2.):
            tw,th=round(template.shape[1]*scale),round(template.shape[0]*scale)
            if th>height or tw>width or min(tw,th)<6:
                continue
            target=cv2.resize(template,(tw,th),interpolation=cv2.INTER_CUBIC)
            score=cv2.matchTemplate(original[:,:max(60,int(width*.55))],target,cv2.TM_CCOEFF_NORMED)
            _,quality,_,(x,y)=cv2.minMaxLoc(score)
            if quality>=.82:
                candidates.append((quality,x,y,tw,th))
        if not candidates:
            return None
        # A coin match alone is insufficient. Confirm the surrounding full
        # white CH rectangle, which remains connected around the red digits.
        white=(np.min(original,axis=2)>185).astype('uint8')
        _,_,components,_=cv2.connectedComponentsWithStats(white,8)
        validated=[]
        for quality,x,y,tw,th in candidates:
            for bx,by,bw,bh,area in components[1:]:
                if (th*2.1<=bw<=th*4.8 and th*.6<=bh<=th*1.6 and
                        area>=bw*bh*.12 and bx<=x+tw/2<=bx+bw and
                        by-2<=y+th/2<=by+bh+2 and
                        0<=bx+bw-(x+tw/2)<=tw*1.2):
                    validated.append((quality,int(bx),int(bx+bw),x,y,tw,th))
        if not validated:
            return None
        quality,badge_left,badge_right,x,y,tw,th=max(validated)
        # The captured sprite is the coin in a white CH badge. Walk to that
        # badge's left edge; read the player's NAME rather than CH/icon ink.
        header_end=max(0,badge_left-2)
        if header_end<15:
            return None  # clipped-out player name, never fabricate one
        # Confirm the actual colon; a fixed +6 would cut letters on another DPI.
        pairs=delimiter_pairs(neutral,max(0,badge_right-2),badge_right+max(14,th))
        colon=pairs[0][1] if pairs else None
        if colon is None or width-colon<12:
            return None
        return (header_end,colon,round(float(quality),4))

    def split_plain(self, original, neutral):
        """No CH icon is required: verify a short name then its delimiter.

        Bracketed item names and later time/URL punctuation cannot be chosen
        as a header separator. A failed name read still falls back to OCR.
        """
        for left,right in delimiter_pairs(neutral):
            prefix=(neutral[:,:max(0,left-2),0]<150).astype('uint8')
            if prefix.shape[1]<12:
                continue
            _,_,stats,_=cv2.connectedComponentsWithStats(prefix,8)
            # Empty word-sized gaps indicate body text, CH graphics or an
            # item label before this ':' rather than a single player name.
            xs=np.flatnonzero(prefix.any(axis=0))
            if not xs.size or np.max(np.diff(xs),initial=0)>max(7,neutral.shape[0]*.3):
                continue
            tall=sum(1 for x,y,w,h,area in stats[1:] if h>=neutral.shape[0]*.35 and area>=4)
            if tall<2:
                continue
            return (max(0,left-2),right,1.)
        return None
