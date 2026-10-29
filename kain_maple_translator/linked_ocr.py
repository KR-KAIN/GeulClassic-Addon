"""Item-only Korean recognition from existing CTC positions and source pixels."""
from collections import OrderedDict
import hashlib
import re
import cv2
import numpy as np

LINK=re.compile(r'\[[^\[\]\n]{0,100}\]')
HANGUL=re.compile('[가-힣]')


_DAMAGED_CJK = re.compile(r'[\u3400-\u9fff\u3040-\u30ff]')
_LINKED_BRACKET = re.compile(r'\[[^\[\]\n]{0,100}\]')


def repair_corrupt_bracket(original: str, recognized: str, confidence: float) -> str | None:
    """Repair a CJK-corrupted linked name without touching intact item labels.

    Multiple item links occur in a single megaphone, so repairing just one
    requires validating all the other labels and every numeric context first.
    A genuine Korean name is NEVER overwritten by another OCR candidate.
    """
    if confidence < .83:
        return None
    source = list(_LINKED_BRACKET.finditer(str(original)))
    retry = list(_LINKED_BRACKET.finditer(str(recognized)))
    if not source or len(source) != len(retry):
        return None
    outside_src = _LINKED_BRACKET.sub('[]',original)
    outside_alt = _LINKED_BRACKET.sub('[]',recognized)
    if re.findall(r'\d+(?:[.,]\d+)*',outside_src) != re.findall(r'\d+(?:[.,]\d+)*',outside_alt):
        return None
    replacements = []
    for old,new in zip(source,retry):
        before,after = old.group()[1:-1], new.group()[1:-1]
        if before == after:
            continue
        # Do not alter a correctly recognized Korean name or a well-formed
        # English item name. Only obviously damaged CJK OCR can be repaired.
        if before.strip() and not _DAMAGED_CJK.search(before):
            return None
        if not 2 <= len(after.strip()) <= 85 or not HANGUL.search(after):
            return None
        if _DAMAGED_CJK.search(after) or re.search(r'[\[\]\r\n]',after):
            return None
        replacements.append((old.start(),old.end(),'['+after.strip()+']'))
    if not replacements:
        return None
    value=original
    for a,b,new in reversed(replacements):
        value=value[:a]+new+value[b:]
    return value


def character_centres(text,info,width):
    words=getattr(info,'words',None) or []
    cols=getattr(info,'word_cols',None) or []
    total=float(getattr(info,'line_txt_len',0) or 0)
    chars=[c for w in words for c in w];columns=[c for w in cols for c in w]
    if total<=0 or ''.join(chars)!=''.join(text.split()) or len(chars)!=len(columns):return None
    it=iter(columns)
    return [None if c.isspace() else (next(it)+.5)*width/total for c in text]


def pixel_brackets(neutral):
    binary=(neutral[:,:,0]<150).astype(np.uint8)
    _,labels,stats,_=cv2.connectedComponentsWithStats(binary,8)
    out=[]
    for n,(x,y,w,h,area) in enumerate(stats[1:],1):
        if not(h>=6 and 2<=w<=max(3,h*.48) and area>=h+2):continue
        shape=labels[y:y+h,x:x+w]==n
        columns=shape.sum(axis=0);stem=int(columns.argmax())
        if columns[stem]<h*.75:continue
        top=shape[:max(1,round(h*.15))].any(axis=0)
        bottom=shape[-max(1,round(h*.15)):].any(axis=0)
        if min(top.sum(),bottom.sum())<w*.7:continue
        middle=shape[max(1,h//3):max(2,h*2//3)]
        if stem<=max(0,w//4) and middle[:,-1].mean()<.3:kind='['
        elif stem>=w-1-max(0,w//4) and middle[:,0].mean()<.3:kind=']'
        else:continue
        out.append((kind,int(x),int(y),int(w),int(h)))
    return out


def _pixel_link_regions(text,image):
    """Use observed bracket pairs if a Korean retry invalidated CTC offsets."""
    matches=list(LINK.finditer(text))
    if not matches:return []
    pairs=[];opening=None
    for kind,x,y,w,h in sorted(pixel_brackets(image),key=lambda b:b[1]):
        if kind=='[':opening=(x,y,w,h)
        elif opening is not None:
            ox,oy,ow,oh=opening
            if x-ox>=8 and abs(y-oy)<=3 and .7<=h/oh<=1.4:
                pairs.append((max(0,ox-2),min(image.shape[1],x+w+2)))
            opening=None
    # The pixels must account for EVERY bracket. No proportion-of-text crop
    # is invented when offsets and source brackets are both unavailable.
    if len(pairs)!=len(matches):return []
    return [(m.start(),m.end(),x0,x1) for m,(x0,x1) in zip(matches,pairs)]


# Full-width brackets the English model sometimes emits for item labels
# ('[DIC 号】'); one-for-one so character positions stay valid.
_BRACKETS=str.maketrans({'【':'[','［':'[','「':'[','】':']','］':']','」':']'})


def link_regions(text,info,image):
    centres=character_centres(text,info,image.shape[1]+10)
    text=str(text).translate(_BRACKETS)
    if centres is None:return _pixel_link_regions(text,image)
    regions=[];brackets=pixel_brackets(image) if '[' in text else []
    for match in LINK.finditer(text):
        a,b=match.span();l,r=centres[a]-5,centres[b-1]-5
        before=next((c-5 for c in reversed(centres[:a]) if c is not None),-image.shape[0])
        after=next((c-5 for c in centres[b:] if c is not None),image.shape[1]+image.shape[0])
        x0=max(0,int(max((before+l)/2,l-image.shape[0]*.38)))
        x1=min(image.shape[1],int(min((r+after)/2,r+image.shape[0]*.38))+1)
        if x1-x0>=8:regions.append((a,b,x0,x1))
    # A missing closing bracket may be recovered only with both bracket
    # shapes in the pixels. With a recognized trade suffix the label ends
    # before it; without one (R17: a Korean label read as '[010 21 S 700K')
    # it ends at the first character right of the ']' seen in the pixels.
    for opening in re.finditer(r'\[',text):
        a=opening.start()
        if any(lo<=a<hi for lo,hi,_,_ in regions) or centres[a] is None:continue
        suffix=re.search(r'(?i)(?:[SBT]\s*>|WT[SB]\b|SELLING\b|BUYING\b|PMO\b|PM\b)',text[a+1:])
        b=a+1+suffix.start() if suffix else None
        if b is not None and ('[' in text[a+1:b] or centres[b] is None):continue
        left_hint=centres[a]-5
        right_limit=centres[b]-5 if b is not None else image.shape[1]
        opens=[box for box in brackets if box[0]=='[' and abs(box[1]-left_hint)<image.shape[0]*.7]
        if not opens:continue
        left=min(opens,key=lambda box:abs(box[1]-left_hint))
        closes=[box for box in brackets if box[0]==']' and left[1]+left[3]+5<box[1]<right_limit and
                abs(box[2]-left[2])<=3 and .7<=box[4]/left[4]<=1.4]
        if not closes:continue
        if b is not None:
            right=max(closes,key=lambda box:box[1])
        else:
            right=min(closes,key=lambda box:box[1])   # the label's own ']'
            edge=right[1]+right[3]
            b=next((j for j in range(a+1,len(text)) if centres[j] is not None and centres[j]-5>edge),len(text))
            if '[' in text[a+1:b]:continue
        regions.append((a,b,max(0,left[1]-2),min(image.shape[1],right[1]+right[3]+2)))
    return regions


def confident_english_link(text,a,b,info,image):
    if not re.fullmatch(r"\[[A-Za-z][A-Za-z '\-]{3,98}\]",text[a:b]):return False
    confs=list(getattr(info,'confs',[]) or [])
    if len(confs)!=len(text):return False
    letters=[confs[i] for i in range(a,b) if text[i].isalpha()]
    if not letters or min(letters)<.90 or float(np.mean(letters))<.98:return False
    centres=character_centres(text,info,image.shape[1]+10)
    if centres is None:return False
    positions=[c for c in centres[a:b] if c is not None]
    # A high score cannot excuse a large CTC gap hiding omitted Hangul.
    return max(np.diff(positions),default=0)<=max(8,image.shape[0]*.9)


def _label(text):
    value=str(text).strip();complete=list(LINK.finditer(value))
    # Source brackets delimit the label. Neighbouring S>/price glyphs may
    # enter the crop but never belong to its one complete [item] result.
    if len(complete)==1:return complete[0].group()[1:-1].strip()
    return value.strip('[]［］ ').strip()


def _native(image):
    color=tuple(int(v) for v in np.median(image,axis=(0,1)))
    return cv2.copyMakeBorder(image,2,2,4,4,cv2.BORDER_CONSTANT,value=color)


def _good(text,score):
    label=_label(text)
    return (len(HANGUL.findall(label))>=2 and score>=.87 and len(label)<=100 and
            not re.search(r'[\u3400-\u9fff\[\]\r\n]',label))


class LinkedItemOCR:
    def __init__(self,engine,capacity=512):
        self.engine=engine;self.capacity=capacity;self.cache=OrderedDict();self.stats={}

    def _measure_inputs(self,images):
        if not images:return
        self.stats['item_input_max_width_px']=max(self.stats['item_input_max_width_px'],max(im.shape[1] for im in images))
        self.stats['item_input_max_height_px']=max(self.stats['item_input_max_height_px'],max(im.shape[0] for im in images))
        self.stats['item_input_total_pixels']+=sum(im.shape[1]*im.shape[0] for im in images)

    def correct(self,reads,tasks,infos):
        self.stats=dict(item_ocr_inputs=0,item_ocr_cache_hits=0,item_ocr_confirmed=0,
                        item_ocr_unresolved=0,item_ocr_batches=0,item_english_skips=0,
                        item_input_max_width_px=0,item_input_max_height_px=0,item_input_total_pixels=0)
        if self.engine is None:return reads
        jobs=OrderedDict();plans=[];suspected=set()
        for i,((text,score),(neutral,original),info) in enumerate(zip(reads,tasks,infos)):
            for a,b,x0,x1 in link_regions(text,info,neutral):
                if confident_english_link(text,a,b,info,neutral):
                    self.stats['item_english_skips']+=1;continue
                # A 5px side margin preserves clipped brackets and final
                # syllable strokes in anti-aliased linked-item labels.
                pad=max(3,min(8,round(neutral.shape[0]*.18)))
                px0=max(0,x0-pad);px1=min(neutral.shape[1],x1+pad)
                crop=neutral[:,px0:px1]
                key=hashlib.blake2b(crop.tobytes()+str(crop.shape).encode(),digest_size=16).digest()
                plans.append((i,a,b,key))
                if key in self.cache:
                    self.cache.move_to_end(key);self.stats['item_ocr_cache_hits']+=1
                else:jobs.setdefault(key,(crop,original[:,px0:px1]))
        pending=list(jobs)
        if pending:
            first_images=[jobs[k][1] for k in pending]
            self._measure_inputs(first_images)
            first=self.engine.recognize_txt(first_images)
            self.stats['item_ocr_inputs']+=len(pending);self.stats['item_ocr_batches']+=1
            candidates=[]
            for key,text,score in zip(pending,first.txts or [],first.scores or []):
                if HANGUL.search(str(text)):suspected.add(key)
                if _good(text,float(score)):candidates.append((key,str(text),float(score)))
                elif float(score)>=.90 and not HANGUL.search(str(text)):self.cache[key]=None
                else:self.stats['item_ocr_unresolved']+=1
            if candidates:
                second_images=[_native(jobs[k][1]) for k,_,_ in candidates]
                self._measure_inputs(second_images)
                second=self.engine.recognize_txt(second_images)
                self.stats['item_ocr_inputs']+=len(candidates);self.stats['item_ocr_batches']+=1
                for (key,first_text,score),text,other_score in zip(candidates,second.txts or [],second.scores or []):
                    if (_good(text,float(other_score)) and
                        re.sub(r'\s+','',_label(first_text))==re.sub(r'\s+','',_label(text))):
                        self.cache[key]=('['+_label(first_text)+']',min(score,float(other_score)))
                    else:self.stats['item_ocr_unresolved']+=1
        replacements={}
        for i,a,b,key in plans:
            if self.cache.get(key):replacements.setdefault(i,[]).append((a,b,*self.cache[key]))
        output=list(reads)
        for i,a,b,key in plans:
            if key not in self.cache and (key in suspected or re.search('[\u3400-\u9fff가-힣]',reads[i][0][a:b])):
                output[i]=(output[i][0],min(output[i][1],.87))
        for i,changes in replacements.items():
            text,score=output[i];confs=list(getattr(infos[i],'confs',[]) or [])
            if len(confs)==len(text):
                protected=set(j for a,b,_,_ in changes for j in range(a,b))
                context=[c for j,c in enumerate(confs) if j not in protected and not text[j].isspace()]
                if context:score=float(np.mean(context))
            for a,b,label,confidence in sorted(changes,reverse=True):
                text=text[:a]+label+text[b:];score=min(score,confidence)
                self.stats['item_ocr_confirmed']+=1
            output[i]=(text,score)
        while len(self.cache)>self.capacity:self.cache.popitem(last=False)
        return output
