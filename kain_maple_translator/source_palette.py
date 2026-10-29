"""Sample real glyph cores independently for sender, linked items and body."""
import re
import numpy as np


def _rgb(value):return np.array([int(value[i:i+2],16) for i in (5,3,1)],dtype=float)


def _hex(bgr):
    b,g,r=[int(v) for v in bgr]
    return f'#{r:02x}{g:02x}{b:02x}'


def white_body_ink(color, background, band_color=''):
    """Recognize white text composited over a dark coloured game scene.

    Alpha-blended white is C = alpha*255 + (1-alpha)*background. Its
    displayed RGB need not be neutral or exceed 175 in every channel.
    Require consistent channel alpha; yellow/pink/blue body text must not
    gain the ordinary-white admission shortcut. Keep the displayed colour.
    """
    color=np.asarray(color,dtype=float)
    background=np.asarray(background,dtype=float)
    if color.min()>=175 and color.max()-color.min()<35:
        return True
    if band_color or background.max()>150 or color.min()<140:
        return False
    alpha=(color-background)/np.maximum(1.,255.-background)
    return bool(alpha.min()>=.50 and alpha.max()<=1.02 and np.ptp(alpha)<=.085
                and np.min(color-background)>=55)


def _mode(pixels,background=None):
    if len(pixels)<5:return ''
    if background is not None:
        delta=np.max(np.abs(pixels.astype(float)-background),axis=1)
        pixels=pixels[delta>=np.percentile(delta,78)]
    q=pixels.astype(np.uint16)>>3;code=q[:,0]*1024+q[:,1]*32+q[:,2]
    values,counts=np.unique(code,return_counts=True);choices=[]
    for i in np.argsort(counts)[-12:]:
        color=np.median(pixels[code==values[i]],axis=0);weight=float(counts[i])
        if background is not None:weight*=max(1.,float(np.max(np.abs(color-background))))**.7
        choices.append((weight,color))
    return _hex(max(choices,key=lambda v:v[0])[1])


def sample_palette(patch,band_color='',meta=None):
    if patch.size==0:return {}
    meta=meta or {};height,width=patch.shape[:2];pixels=patch[:,:,:3]
    if re.fullmatch(r'#[0-9a-fA-F]{6}',band_color):bg=_rgb(band_color)
    else:
        from .ink_background import row_background
        bg=np.median(row_background(pixels),axis=0)
    delta=np.max(np.abs(pixels.astype(float)-bg),axis=2)
    valid_y=np.mean(delta>35,axis=1)<.65
    ink=(delta>28)&valid_y[:,None]
    start=max(0,min(width,int(meta.get('body_start',min(width//3,110)))))
    end=max(1,min(width,int(meta.get('name_end') or min(width//4,75))))
    links=np.zeros((height,width),dtype=bool)
    if 'item_regions' in meta:
        for x0,y0,x1,y1 in meta['item_regions']:
            links[max(0,int(y0)):min(height,int(y1)),max(0,int(x0)-1):min(width,int(x1)+1)]=True
    else:
        for x0,x1 in meta.get('item_ranges',[]):links[:,max(0,int(x0)-1):min(width,int(x1)+1)]=True
    body_mask=np.zeros_like(ink)
    if 'body_regions' in meta:
        for x0,y0,x1,y1 in meta['body_regions']:
            body_mask[max(0,int(y0)):min(height,int(y1)),max(0,int(x0)):min(width,int(x1))]=True
        body_mask &= ink
    else:
        body_mask=ink.copy();body_mask[:,:start]=False
    body_mask[links]=False
    # A link-only row provides no evidence for the ordinary body colour.
    # Do not fall back to its bright yellow item glyphs.
    body=_mode(pixels[body_mask],bg);nick=_mode(pixels[:,:end][ink[:,:end]],bg)
    item=_mode(pixels[ink&links],bg);out={}
    if body:
        out['text_color']=body;c=_rgb(body)
        out['source_white_body']=white_body_ink(c,bg,band_color)
    if nick:out['nickname_color']=nick
    if item:out['item_color']=item
    if band_color:
        sampled=_mode(pixels[(delta<22)&valid_y[:,None]])
        if sampled:out['band_color']=sampled
    return out
