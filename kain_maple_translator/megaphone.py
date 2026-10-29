"""Classify chat-band appearance from actual pixels, independent of English content.

IMPORTANT: The official MapleStory sources document FOUR megaphone products,
not a stable palette-to-product taxonomy for *Classic World*. This module
reconstructs the source background when confident, and uses conservative
labels when there is no reliable item-link/megaphone evidence. It never
assumes that sale text means an item megaphone.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
import numpy as np
import cv2

# Palette labels describe observed hues, not official item taxonomy.
@dataclass(frozen=True)
class Band:
    tone: str = 'none'
    background: str = ''
    coverage: float = 0.0


def _slate_blue_text_mask(bgr: np.ndarray) -> np.ndarray:
    """Blue lettering on the muted slate-grey Classic megaphone background.

    The thin gold underline is *not* part of this signature. Testing blue
    glyphs as well as a broad matte slate field avoids labelling ordinary
    grey UI panels as announcements.
    """
    bgr3=bgr[:,:,:3].astype(np.int16)
    b,g,r=bgr3[:,:,0],bgr3[:,:,1],bgr3[:,:,2]
    return ((b-r>=50)&(b-g>=19)&(b>=65)&(b<=195)&
            (g>=24)&(g<=165)&(r<=112)&(r<g-10))


def _slate_background_mask(bgr: np.ndarray) -> np.ndarray:
    bgr3=bgr[:,:,:3].astype(np.int16)
    b,g,r=bgr3[:,:,0],bgr3[:,:,1],bgr3[:,:,2]
    return ((r>=112)&(r<=208)&(g>=125)&(g<=211)&(b>=136)&(b<=221)&
            (g-r>=7)&(b-g>=4)&(b-r>=17)&(b-r<=67))


def _slate_gray_band(bgr: np.ndarray) -> Band:
    """Require a majority slate field *and* contrasting blue characters."""
    if bgr.size == 0 or bgr.ndim != 3 or bgr.shape[2] < 3:
        return Band()
    background=_slate_background_mask(bgr)
    coverage=float(np.mean(background))
    if coverage<.70:
        # Adapt to brightness/opacity while still requiring a broad slate
        # field AND blue foreground. A grey UI rectangle alone is not enough.
        pixels = bgr[:, :, :3].astype(np.int16)
        median = np.median(pixels, axis=(0, 1))
        b, g, r = median
        if not (55 <= r <= 215 and 5 <= g-r <= 32 and 3 <= b-g <= 30 and 14 <= b-r <= 67):
            return Band()
        background = np.max(np.abs(pixels-median), axis=2) < 26
        coverage = float(np.mean(background))
        bb, gg, rr = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
        blue = (bb-rr > 36) & (bb-gg > 13) & (rr < r-25) & (gg < g-15)
        if coverage < .60 or np.count_nonzero(blue) < max(5, int(bgr.shape[0]*bgr.shape[1]*.003)):
            return Band()
        b, g, r = np.median(pixels[background], axis=0).astype(int)
        return Band('gray', f'#{r:02x}{g:02x}{b:02x}', round(coverage, 3))
    blue=_slate_blue_text_mask(bgr)
    # Reject solid grey settings panels and weak blue anti-aliasing noise.
    min_pixels=max(5,int(bgr.shape[0]*bgr.shape[1]*.003))
    if np.count_nonzero(blue)<min_pixels:
        return Band()
    pix=bgr[:,:,:3][background]
    b,g,r=np.median(pix,axis=0).astype(int)
    return Band('gray',f'#{r:02x}{g:02x}{b:02x}',round(coverage,3))


def detect_band(bgr: np.ndarray, relative_rect: tuple[int,int,int,int]) -> Band:
    """Find a nearly full-width, saturated horizontal strip BEHIND a row.

    The crop should be only the user's chosen Maple bottom chat rectangle.
    OpenCV BGR image, rectangle relative to the crop; no screen/network access.
    """
    if bgr is None or bgr.ndim != 3 or bgr.shape[2] < 3:
        return Band()
    height,width=bgr.shape[:2]
    x,y,w,h=map(int,relative_rect)
    if min(height,width,h,w) <= 0:
        return Band()
    # A thin horizontal band extends across most of the CHAT PANEL, not just
    # a character's letters. Inspect around baseline and require consistency.
    yl=max(0,min(height-1,y+max(1,h//3)))
    yh=max(yl+1,min(height,y+max(3,2*h//3+1)))
    strip=bgr[yl:yh, max(0,int(width*.03)):max(1,int(width*.97)), :3]
    if strip.size == 0:return Band()
    # Low-saturation slate banners are invisible to the saturated-hue path.
    # Distinguish them by blue lettering, never by a yellow bottom border.
    slate=_slate_gray_band(strip)
    if slate.tone!='none':return slate
    hsv=cv2.cvtColor(strip,cv2.COLOR_BGR2HSV)
    # Bright saturated pixels. Normal transparent game backgrounds, dark
    # translucent windows and white text do not satisfy the coverage guard.
    mask=(hsv[:,:,1] >= 55)&(hsv[:,:,2]>=92)
    coverage=float(np.mean(mask))
    if coverage < .54:
        # Pale pastel megaphones (especially pink) have S=30..55 on
        # some game/client display profiles. Require a broad flat backdrop
        # to avoid classifying bright scenery behind transparent chat.
        soft=(hsv[:,:,1]>=31)&(hsv[:,:,2]>=110)
        if float(np.mean(soft)) < .72:
            return Band()
        core=strip[soft].astype(np.float32)
        if core.shape[0] < 30:
            return Band()
        spread=np.median(np.abs(core-np.median(core,axis=0)),axis=0)
        if float(np.max(spread))>22:
            return Band()
        # Saturated scenery and empty coloured UI blocks are not chat.
        # A real announcement contains contrasting characters on the field.
        median=np.median(core,axis=0)
        contrast=np.max(np.abs(strip.astype(np.float32)-median),axis=2)
        if int(np.count_nonzero(contrast>30)) < max(8,int(strip.shape[0]*strip.shape[1]*.003)):
            return Band()
        mask=soft
        coverage=float(np.mean(mask))
    colors=hsv[:,:,0][mask].astype('float32')
    # Circular hue statistics robust to text outlines and solid banners.
    if len(colors)<20:return Band()
    a=colors*np.pi/90
    mean=np.arctan2(np.sin(a).mean(),np.cos(a).mean())
    hue=float((mean%(np.pi*2))*90/np.pi)
    distance=np.abs(((colors-hue+90)%180)-90)
    chroma_consistency=float(np.mean(distance<18))
    if chroma_consistency<.62:return Band()
    pix=strip[mask]
    color=np.median(pix,axis=0).astype(int)
    b,g,r=[int(v) for v in color]
    # The red megaphone has a strongly dominant red channel. It must not
    # be confused with Maple's pale pink announcement background.
    is_red=(r>=110 and r-g>=48 and r-b>=42 and r>=g*1.35 and r>=b*1.28)
    if is_red:tone='red'
    elif 15<=hue<=42:
        # Real [아확] banners are bright yellow/gold. Dark olive chat
        # backgrounds can have identical hue and saturation; treating those
        # as item megaphones misroutes white 'gz' normal chat.
        if float(np.median(hsv[:,:,2][mask])) < 155 or max(r,g)<155:
            return Band()
        tone='yellow'
    elif 72<=hue<=103:tone='cyan'
    elif 104<=hue<=137:tone='blue'
    elif 138<=hue<=179 or 0<=hue<15:tone='pink'
    elif 43<=hue<72:tone='green'
    else:return Band()
    return Band(tone,f'#{r:02x}{g:02x}{b:02x}',round(coverage,3))


def classify(band: Band, body: str) -> dict:
    """Colour-first labels for Classic World announcements.

    These are USER-CONFIGURED screen-palette names, not claims about
    official game-item IDs. Never infer [아확] merely from bracketed text,
    and never demote verified colours due to a missing item link.
    """
    # Keep unchanged kind identifiers for compatibility with the rest of
    # LiveWorker, Qt renderer and OBS. Only confirmed source colour chooses
    # the Korean badge. Unverified colours stay [확성], not normal chat.
    palette = {
        'gray': ('unknown', '[일확]'),
        'pink': ('super', '[고확]'),
        'cyan': ('unknown', '[하이퍼]'),
        'green': ('unknown', '[하이퍼]'),
        'yellow': ('item', '[아확]'),
    }
    if band.tone == 'none':
        return {'kind':'normal', 'prefix':'', 'tone':'none', 'band_color':''}
    kind,prefix = palette.get(band.tone, ('unknown','[확성]'))
    return {'kind':kind, 'prefix':prefix, 'tone':band.tone,
            'band_color':band.background}


def row_appearance(image: np.ndarray, rect: tuple[int,int,int,int], origin: tuple[int,int], body: str, source_meta=None)->dict:
    x,y,w,h=rect
    band=detect_band(image,(x-origin[0],y-origin[1],w,h))
    if band.tone == 'none' and w >= 70:
        # Selected rectangles can extend beyond the real chat panel. The old
        # full-width vote then labelled real megaphones as ordinary chat.
        # Check the actual OCR line span as a second, local background vote.
        lx, ly = max(0,x-origin[0]-5), max(0,y-origin[1]-2)
        local = image[ly:min(image.shape[0], y-origin[1]+h+3),
                      lx:min(image.shape[1], x-origin[0]+w+10), :3]
        if local.shape[0] >= 6 and local.shape[1] >= 70:
            band = detect_band(local, (0, 0, local.shape[1], local.shape[0]))
    result = classify(band,body)
    if not body:return result
    lx, ly = max(0, x-origin[0]), max(0, y-origin[1])
    patch = image[ly:ly+h, lx:lx+w, :3]
    if patch.size:
        # Read foreground colour apart from the background, using the body
        # half of the text line to reduce nickname-colour contamination.
        # Base the vote on BODY pixels, not nickname or colored item links.
        # The latter occur in ordinary chat as well and used to leak into the
        # megaphone decision when the text begins with a bracketed item.
        source_meta = source_meta or {}
        body_start = source_meta.get('body_start')
        if not isinstance(body_start, (int, float)) or body_start < 0:
            body_start = min(patch.shape[1]//3, 110)
        body_start = max(0, min(patch.shape[1], int(body_start)))
        sample = patch[:, body_start:]
        excluded = []
        for x0, x1 in source_meta.get('item_ranges', []):
            try:
                excluded.append((int(x0)-body_start, int(x1)-body_start))
            except (ValueError, TypeError):
                continue
        # Some megaphones have neither a coloured strip nor a CH badge.
        # Inspect source glyphs BEFORE the white/black OCR normalization.
        if band.tone == 'none' and re.sub(r'\[[^\]]*\]', '', body).strip():
            glyph_tone=_coloured_glyphs(sample, excluded)
            if glyph_tone is not None:
                # Mark *verified source-pixel* evidence separately from
                # tentative OCR/category guesses. A coloured BODY on a flat
                # dark panel is a legitimate bannerless announcement; keep
                # it even without an explicit CH badge. This flag must not
                # be inferred from a text-colour string sampled over scenery.
                # Bannerless announcements also inherit the SAME palette
                # as a detected full-width colour band. Item-link colours
                # are excluded from this vote above.
                label = classify(Band(glyph_tone), body)
                result.update(kind=label['kind'], prefix=label['prefix'],
                              tone=glyph_tone, glyph_color_confirmed=True)
        from .source_palette import sample_palette
        result.update(sample_palette(patch,band.background,source_meta))
        if result.get('source_white_body') and (band.tone == 'none' or
                (band.tone=='yellow' and (not band.background or
                 max(int(band.background[i:i+2],16) for i in (1,3,5))<160))):
            result.update(kind='normal',prefix='',tone='none',band_color='')
    return result


def _coloured_glyphs(sample, excluded_regions=()):
    if sample.size == 0:
        return None
    from .ink_background import row_background
    background=row_background(sample)
    # A textured/bright game scene cannot supply reliable glyph colour.
    if float(np.median(np.max(background,axis=1))) > 135:
        return None
    delta=np.max(np.abs(sample.astype(np.float32)-background[:,None]),axis=2)
    strong=delta>max(45,float(np.percentile(delta,90)))
    for x0, x1 in excluded_regions:
        x0=max(0, min(strong.shape[1], x0))
        x1=max(0, min(strong.shape[1], x1))
        strong[:, x0:x1] = False
    pixels=sample[strong]
    if len(pixels)<12:
        return None
    hsv=cv2.cvtColor(pixels.reshape(1,-1,3),cv2.COLOR_BGR2HSV)[0]
    # White body letters win over coloured item links and a coloured sender.
    bright=hsv[:,2]>=max(105,float(np.percentile(hsv[:,2],70))*.80)
    hsv=hsv[bright]
    if len(hsv)<12 or float(np.mean(hsv[:,1]<45))>=.20:
        return None
    colored=hsv[hsv[:,1]>65]
    if len(colored)<len(hsv)*.70:
        return None
    hues=colored[:,0].astype(float)
    angles=hues*np.pi/90
    hue=float(np.arctan2(np.sin(angles).mean(),np.cos(angles).mean())%(2*np.pi)*90/np.pi)
    if np.mean(np.abs((hues-hue+90)%180-90)<16)<.75:
        return None
    if hue<10 or hue>=174:return 'red'
    if hue<43:return 'yellow'
    if hue<73:return 'green'
    if hue<104:return 'cyan'
    if hue<138:return 'blue'
    return 'pink'


def tinted_rgba(hex_value: str, opacity: float=0.26)->str:
    valid=bool(re.fullmatch(r'#[0-9a-fA-F]{6}',str(hex_value or '')))
    color=hex_value if valid else '#4a6179'
    return f'rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},{max(0,min(1,float(opacity))):.3f})'
