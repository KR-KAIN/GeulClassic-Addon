"""Low-cost screen change detection and RapidOCR text box extraction."""
from __future__ import annotations
import cv2
import numpy as np
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Line:
    text: str
    confidence: float
    rect: tuple[int, int, int, int]  # screen-space x, y, w, h
    channel_hint: bool = False
    ink_key: str = ""
    source_meta: dict = field(default_factory=dict)


def changed(bgr: np.ndarray, previous: np.ndarray | None) -> tuple[bool, np.ndarray]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Check enough pixels to capture a short message without processing every frame with OCR.
    hh, ww = gray.shape
    scale = min(1.0, 720.0 / max(ww, 1))
    thumb = cv2.resize(gray, (max(1, int(ww * scale)), max(1, int(hh * scale))), interpolation=cv2.INTER_AREA)
    if previous is None or previous.shape != thumb.shape:
        return True, thumb
    diff = cv2.absdiff(thumb, previous)
    changed_pixels = float(np.mean(diff > 13))
    return changed_pixels > 0.0015 or float(np.mean(diff)) > 0.65, thumb


def red_announcement_regions(bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Locate vivid red megaphone rows inside the *selected chat region*.

    This is only a visual cue for additional OCR, never text generated from
    colour alone. Covers solid red banners and red glyphs on dark chat.
    """
    if bgr is None or bgr.ndim != 3 or bgr.shape[2] < 3:
        return []
    height, width = bgr.shape[:2]
    if width < 90 or height < 12:
        return []
    hsv = cv2.cvtColor(bgr[:,:,:3], cv2.COLOR_BGR2HSV)
    b, g, r = [bgr[:,:,i].astype(np.int16) for i in range(3)]
    red = ((r >= 105) & (r-g>=45) & (r-b>=40) &
           (hsv[:,:,1]>=85) & (hsv[:,:,2]>=90))
    # Solid red strips: robust to icons and lettering. Red text: smaller
    # coverage, but only accept if it stretches across a meaningful width.
    margin=max(2,int(width*.02))
    pixels=red[:,margin:width-margin]
    counts=np.count_nonzero(pixels,axis=1)
    occupied=np.where(counts>=max(8,int(width*.018)))[0]
    if len(occupied)==0:
        return []
    runs=[]
    start=last=int(occupied[0])
    for at in occupied[1:]:
        at=int(at)
        if at-last>4:
            runs.append((start,last));start=at
        last=at
    runs.append((start,last))
    regions=[]
    for start,end in runs:
        y0=max(0,start-5);y1=min(height,end+7)
        band=red[y0:y1]
        coords=np.where(band)
        if not len(coords[1]):continue
        span=int(coords[1].max())-int(coords[1].min())
        strong_row=(int(counts[start:end+1].max())>=int(width*.35))
        if span < width*.23 and not strong_row:
            continue
        # Red text might be thin; leave breathing room for anti-aliased edges.
        x0=max(0,int(coords[1].min())-15)
        x1=min(width,int(coords[1].max())+17)
        if strong_row:
            x0=0;x1=width
        if y1-y0<9 or x1-x0<55:continue
        regions.append((x0,y0,x1-x0,y1-y0))
    return regions[:5]


def gray_blue_announcement_regions(bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Find slate-grey banners with blue lettering in the selected chat crop.

    This is intentionally independent of the thin yellow border: a yellow
    stripe alone must not trigger a grey megaphone. Screen coordinates are
    never inferred outside the caller's explicit OCR rectangle.
    """
    if bgr is None or bgr.ndim != 3 or bgr.shape[2] < 3:
        return []
    height,width=bgr.shape[:2]
    if height<13 or width<110:return []
    from .megaphone import _slate_background_mask, _slate_blue_text_mask
    inner=bgr[:,max(0,int(width*.04)):max(1,int(width*.96)),:3]
    bg=_slate_background_mask(inner)
    blue=_slate_blue_text_mask(inner)
    # Entire horizontal background, rather than thin blue letters, is used
    # for row boundaries, so a two-line announcement stays in one ROI.
    candidates=np.where(np.mean(bg,axis=1)>.72)[0]
    if candidates.size==0:return []
    runs=[];start=last=int(candidates[0])
    for y in candidates[1:]:
        y=int(y)
        if y-last>3:
            runs.append((start,last));start=y
        last=y
    runs.append((start,last))
    out=[]
    for start,end in runs:
        if end-start<10:continue
        y0=max(0,start-3);y1=min(height,end+4)
        # Grey alone does not mean megaphone; blue glyphs are mandatory.
        glyphs=int(np.count_nonzero(blue[start:end+1]))
        if glyphs<max(10,int((end-start+1)*width*.004)):
            continue
        out.append((0,y0,width,y1-y0))
    return out[:3]


def enhance_gray_blue_chat(crop: np.ndarray) -> np.ndarray:
    """Readable neutral OCR image, emphasizing slate-background blue text."""
    from .megaphone import _slate_background_mask, _slate_blue_text_mask
    bg=_slate_background_mask(crop)
    blue=_slate_blue_text_mask(crop)
    if np.mean(bg)<.45 or np.count_nonzero(blue)<8:
        return enhance_colored_chat(crop)
    # Keep original edges as grayscale where foreground is non-blue (such as
    # channel badges); emphasize blue ink without manufacturing text.
    gray=cv2.cvtColor(crop[:,:,:3],cv2.COLOR_BGR2GRAY)
    result=np.where(bg,246,gray).astype(np.uint8)
    result=np.where(blue,16,result).astype(np.uint8)
    return cv2.cvtColor(result,cv2.COLOR_GRAY2BGR)


def colorful_chat_regions(bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Large, bright solid chat strips (yellow/pink/cyan), not arbitrary red text.

    Returns image-local bounding boxes for a *bounded* supplemental OCR pass.
    It never reads another game area or generates text on its own.
    """
    if bgr is None or bgr.ndim != 3 or bgr.shape[2] < 3:
        return []
    height,width=bgr.shape[:2]
    if height < 15 or width < 100:
        return []
    hsv=cv2.cvtColor(bgr[:,:,:3],cv2.COLOR_BGR2HSV)
    inner=hsv[:,max(0,int(width*.05)):max(1,int(width*.95))]
    bright=(inner[:,:,1]>=50)&(inner[:,:,2]>=110)
    coverage=np.count_nonzero(bright,axis=1)/max(1,bright.shape[1])
    lines=np.where(coverage>.68)[0]
    if len(lines)==0:
        return []
    bands=[]
    top=bottom=int(lines[0])
    for i in lines[1:]:
        i=int(i)
        if i-bottom>3:
            if bottom-top>=5:
                y0=max(0,top-5);y1=min(height,bottom+7)
                bands.append((0,y0,width,y1-y0))
            top=i
        bottom=i
    if bottom-top>=5:
        y0=max(0,top-5);y1=min(height,bottom+7)
        bands.append((0,y0,width,y1-y0))
    return bands[:2]


def enhance_colored_chat(crop: np.ndarray) -> np.ndarray:
    """Normalize dark Maple glyphs on saturated chat backgrounds."""
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    boosted=cv2.createCLAHE(clipLimit=1.9,tileGridSize=(4,4)).apply(gray)
    # Avoid an extreme binary threshold that would delete antialiased glyphs.
    return cv2.cvtColor(boosted,cv2.COLOR_GRAY2BGR)


def red_background_difference(crop: np.ndarray) -> np.ndarray:
    """Highlight characters against red banner pixels with a neutral canvas."""
    hsv = cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    red = (crop[:,:,2].astype(np.int16)-crop[:,:,1].astype(np.int16)>45) & (hsv[:,:,1]>85)
    red_pixels = crop[red]
    if red_pixels.size<max(30,int(crop.shape[0]*crop.shape[1]*.03)):
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(cv2.createCLAHE(clipLimit=2.5,tileGridSize=(4,4)).apply(gray),cv2.COLOR_GRAY2BGR)
    background=np.median(red_pixels,axis=0).astype(np.int16)
    delta=np.max(np.abs(crop.astype(np.int16)-background),axis=2)
    # White background with black foreground is OCR-friendly even if the
    # original glyphs were yellow, black, or light pink on a red banner.
    threshold=max(32,int(np.percentile(delta,65)))
    output=np.where(delta>threshold,15,245).astype(np.uint8)
    return cv2.cvtColor(output,cv2.COLOR_GRAY2BGR)


def _dedupe_ocr_boxes(lines: list[Line]) -> list[Line]:
    """Prefer higher-confidence result when an OCR retry overlaps its base box."""
    # Chat-like, complete reads outrank a high-confidence fragment. On red
    # strips the first OCR pass may see only the sender, dropping the body.
    def _quality(entry: Line):
        value=entry.text.strip()
        looks_like_chat=bool(re.match(r'^[\w.\-]{2,24}\s*(?:\bCH\s*\d{1,3}\b)?\s*[:：]\s*\S',value))
        # Higher-confidence *short* OCR is frequently only half a megaphone.
        # Reward a complete message strongly, but never use text to invent
        # missing characters. The actual OCR candidate still has to exist.
        content_len=len(value.partition(':')[2].strip()) if looks_like_chat else len(value)
        return (float(entry.confidence) + (0.40 if looks_like_chat else 0)
                + min(0.85, content_len * 0.080))
    kept=[]
    for line in sorted(lines,key=lambda v:(-_quality(v),v.rect[1], v.rect[0])):
        x,y,w,h=line.rect
        overlap=False
        for other in kept:
            ox,oy,ow,oh=other.rect
            inter=max(0,min(x+w,ox+ow)-max(x,ox))*max(0,min(y+h,oy+oh)-max(y,oy))
            if inter/max(1,min(w*h,ow*oh))>=.72:
                # Distinct same-line boxes can occupy overlapping rectangles;
                # only suppress a candidate that appears to read the *same*
                # text span (or a longer read of that very same span).
                a=re.sub(r'\s+','',line.text).casefold()
                b=re.sub(r'\s+','',other.text).casefold()
                if a in b or b in a or (abs(x-ox)<7 and abs(y-oy)<6 and abs(w-ow)<12):
                    overlap=True;break
        if not overlap:kept.append(line)
    return sorted(kept,key=lambda v:(v.rect[1],v.rect[0]))


def ocr_threads() -> int:
    """ONNX threads per OCR model. Was fixed at 2; on an 8-thread PC the
    chat OCR then used ~1/4 of the CPU while fast chat queued up frames."""
    import os
    forced = os.environ.get('KAIN_OCR_THREADS')
    if forced and forced.isdigit():
        return max(1, min(8, int(forced)))
    return max(2, min(4, (os.cpu_count() or 4) // 2))


class TextRecognizer:
    def __init__(self):
        import onnxruntime
        # Offline means no platform telemetry either. Disable it BEFORE any
        # RapidOCR session is constructed; do not silently swallow a failure.
        onnxruntime.disable_telemetry_events()
        from rapidocr import RapidOCR, OCRVersion, ModelType, LangRec
        model_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'resources' / 'ocr'
        names = ('PP-OCRv6_rec_small.onnx', 'PP-OCRv6_det_small.onnx', 'korean_PP-OCRv5_rec_mobile.onnx')
        for name in names:
            if not (model_root/name).is_file():
                raise RuntimeError(f'OCR 모델 누락: {name} · ZIP 전체를 다시 풀어 BUILD-WINDOWS.bat 실행')
        self.ocr = RapidOCR(params={
            'Global.use_cls': False,
            'Global.return_word_box': True,
            'EngineConfig.onnxruntime.intra_op_num_threads': ocr_threads(),
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
            'Det.limit_type': 'max', 'Det.limit_side_len': 1280,
            'Det.model_path': str(model_root/names[1]),
            'Rec.model_path': str(model_root/names[0]),
        })
        # Default PP-OCRv6 recognition does not include Korean. Read mixed
        # Hangul/English rows with a dedicated, build-bundled Korean model.
        self.korean_ocr = RapidOCR(params={
            'Global.use_det': False, 'Global.use_cls': False,
            'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
            'Rec.lang_type': LangRec.KOREAN,
            'Rec.rec_img_shape': [3, 32, 320],
            'Rec.model_path': str(model_root/names[2]),
            'EngineConfig.onnxruntime.intra_op_num_threads': ocr_threads(),
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        })

        # Dedicated 48px item recognition; established whole-line path stays 32px.
        self.korean_link_ocr = RapidOCR(params={
            'Global.use_det': False, 'Global.use_cls': False, 'Global.return_word_box': True,
            'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
            'Rec.lang_type': LangRec.KOREAN, 'Rec.rec_img_shape': [3, 48, 320],
            'Rec.model_path': str(model_root/names[2]),
            'EngineConfig.onnxruntime.intra_op_num_threads': ocr_threads(),
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        })

    def recognize_lines(self, images):
        from .recognition_batch import recognize_width_buckets
        return recognize_width_buckets(self.ocr,images)

    def detect(self, bgr: np.ndarray, left: int, top: int, scale: float = 1.25) -> list[Line]:
        """Main OCR plus targeted red/grey megaphone passes inside selected chat."""
        self.last_detect_inputs=[]
        main=self._detect_once(bgr,left,top,scale)
        candidates=[]
        for x,y,w,h in red_announcement_regions(bgr):
            crop=bgr[y:y+h,x:x+w,:3]
            # Colour-normalized retry, even when normal chat elsewhere in the
            # same frame already succeeded. This repairs missed red speech.
            enhanced=red_background_difference(crop)
            candidates.extend(self._detect_once(enhanced,left+x,top+y,max(scale,1.6)))
        # Grey/blue megaphones need a dedicated pass even if OCR has already
        # read another colorful chat line elsewhere in the current frame.
        for x,y,w,h in gray_blue_announcement_regions(bgr):
            crop=bgr[y:y+h,x:x+w,:3]
            enhanced=enhance_gray_blue_chat(crop)
            candidates.extend(self._detect_once(enhanced,left+x,top+y,max(scale,1.6)))
        # Colored Classic chat backgrounds make black/pastel antialiased
        # glyphs merge (e.g. "Patch" -> "Patc E"). A bounded targeted
        # contrast retry helps when the frame contains a mixed-language
        # trade message, weak OCR confidence, or no recognized text.
        retry_colored=(not main or any(x.confidence < .78 or
                       re.search(r'(?i)\b(?:also\s+have|for\s+\d+(?:\.\d+)?[kmb])\b',x.text)
                       for x in main))
        if retry_colored:
            for x,y,w,h in colorful_chat_regions(bgr):
                crop=bgr[y:y+h,x:x+w,:3]
                candidates.extend(self._detect_once(enhance_colored_chat(crop),
                                    left+x,top+y,max(scale,1.5)))
        return _dedupe_ocr_boxes(main+candidates)

    def _detect_once(self, bgr: np.ndarray, left: int, top: int, scale: float = 1.25) -> list[Line]:
        scale = max(1.0, min(float(scale), 2.0))
        image = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale > 1.01 else bgr
        if hasattr(self,'last_detect_inputs'):
            self.last_detect_inputs.append((int(image.shape[1]),int(image.shape[0])))
        result = self.ocr(image, use_det=True, use_cls=False, use_rec=True)
        boxes = getattr(result, 'boxes', None)
        texts = getattr(result, 'txts', None)
        scores = getattr(result, 'scores', None)
        if boxes is None or texts is None or len(texts) == 0:
            # The live Maple chat has bright/pastel text over saturated
            # colored strips. Try contrast normalization only when the
            # regular pass finds nothing, avoiding routine double OCR.
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray)
            if hasattr(self,'last_detect_inputs'):
                self.last_detect_inputs.append((int(image.shape[1]),int(image.shape[0])))
            result = self.ocr(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR), use_det=True, use_cls=False, use_rec=True)
            boxes = getattr(result, 'boxes', None)
            texts = getattr(result, 'txts', None)
            scores = getattr(result, 'scores', None)
            if boxes is None or texts is None or len(texts) == 0:
                return []
        output: list[Line] = []
        for box, text, confidence in zip(boxes, texts, scores if scores is not None else [1.] * len(texts)):
            points = np.asarray(box, dtype=np.float32) / scale
            x0 = int(np.min(points[:, 0])) + left
            y0 = int(np.min(points[:, 1])) + top
            x1 = int(np.max(points[:, 0])) + left
            y1 = int(np.max(points[:, 1])) + top
            if x1 - x0 < 8 or y1 - y0 < 6:
                continue
            output.append(Line(str(text).strip(), float(confidence), (x0, y0, x1 - x0, y1 - y0)))
        return output
