"""Line-first OCR: reuse stationary/scrolled ink, batch only unseen text lines.

No game process access. Geometry is always relative to the selected chat crop.
The existing detector remains the recovery path for uncertain segmentation.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
import hashlib
import re
import time

import cv2
import numpy as np

from .glyph_features import GlyphDebugRecorder, row_category, separate_glyphs, dominant_ink_color
from .glyph_dictionary import GlyphDictionary, row_profile
from .core import merge_chat_ocr, parse_chat_line
from .vision import Line
from .badge_split import BadgeSplitter
from .timings import LatencyBook
from .megaphone import detect_band
from .ink_background import row_background, neutral_ink
from .linked_ocr import LinkedItemOCR, link_regions, character_centres
from .ocr_validation import needs_critical_retry,prefer_critical_read,same_numeric_fields,loses_known_terms,price_read_resolves
from .ocr_recall import same_read, merge_recovery_lines, cache_ttl


@dataclass
class InkRow:
    rect: tuple[int, int, int, int]
    original: np.ndarray
    neutral: np.ndarray
    key: bytes
    # True for the bright-glyph rescue (white outlined chat over scenery):
    # ``neutral`` is then a clean binary glyph mask while ``original`` still
    # contains the moving map behind the letters.
    bright: bool = False

    @property
    def isolated_white(self) -> bool:
        # R12-VIDEO-RECALL name for the same bright-glyph rows.
        return self.bright


def ink_rows(bgr: np.ndarray, height_hint=None) -> tuple[list[InkRow], bool]:
    """Separate horizontal ink by row projection, without a neural detector.

    A row-wise median models solid/translucent chat backgrounds; broad UI
    borders and textured/noisy backgrounds are rejected rather than guessed.
    Return an explicit uncertainty bit so rejected crops get detector recovery.
    """
    h, w = bgr.shape[:2]
    if h < 6 or w < 25:
        return [], True
    bg = row_background(bgr).astype(np.int16)
    delta = np.max(np.abs(bgr[:, :, :3].astype(np.int16)-bg[:, None, :]), axis=2)
    # Textured red system strips have dark decorative patterns. They are
    # background, not ink. Isolate the actual light foreground on those rows.
    red_rows = ((bg[:,2] >= 110) & (bg[:,2]-bg[:,1] >= 48) &
                (bg[:,2]-bg[:,0] >= 42) & (bg[:,2] >= bg[:,1]*1.35) &
                (bg[:,2] >= bg[:,0]*1.28))
    channels = bgr[:, :, :3].astype(np.int16)-bg[:, None, :]
    light = np.minimum(channels[:, :, 0], channels[:, :, 1])
    light_pixels = (light > 30) & (channels[:, :, 2] > 8)
    if np.count_nonzero(light_pixels[red_rows]) >= max(12, int(w*.025)):
        delta[red_rows] = np.where(light_pixels[red_rows], np.maximum(0, light[red_rows]), 0)
    # Preserve the strong projection. A globally lowered threshold can join
    # two genuine lines through background texture between their baselines.
    thresholds = np.full(h,32)
    ink = delta>32
    # A 1px panel edge used to connect all baselines into one rejected block.
    # Strip only nearly continuous *outer* columns, never a player's letters.
    edges = np.zeros(w, dtype=bool)
    for x in list(range(min(3,w)))+list(range(max(0,w-3),w)):
        edges[x] = np.mean(ink[:,x]) > .95
    ink[:,edges] = False
    counts=ink[:,4:max(5,w-4)].sum(axis=1)
    occupied=np.flatnonzero((counts>=max(3,int(w*.002))) & (counts<w*.70))
    near=np.zeros(h,dtype=bool)
    for y in occupied:near[max(0,y-2):min(h,y+3)]=True
    weak=(delta>12) & (np.mean(delta<10,axis=1)>.75)[:,None] & (~near[:,None])
    n,labels,components,_=cv2.connectedComponentsWithStats(weak.astype('uint8'),8)
    kept=np.zeros_like(weak)
    for label,(cx,cy,cw,ch,area) in enumerate(components[1:],1):
        if 5<=ch<=40 and area>=10 and cw>=2:
            kept[labels==label]=True
    weak_counts=kept.sum(axis=1)
    weak_y=np.flatnonzero(weak_counts>=max(3,int(w*.002)))
    weak_runs=[]
    for y in weak_y:
        if not weak_runs or y-weak_runs[-1][-1]>2:weak_runs.append([int(y)])
        else:weak_runs[-1].append(int(y))
    for run in weak_runs:
        if run[-1]-run[0]>=4:
            yy=slice(run[0],run[-1]+1)
            xs=np.flatnonzero(kept[yy].any(axis=0))
            if xs.size and xs[-1]-xs[0]>=max(30,int(w*.05)):
                thresholds[yy]=12
                ink[yy] |= kept[yy]
    counts=ink[:,4:max(5,w-4)].sum(axis=1)
    occupied=np.flatnonzero((counts>=max(3,int(w*.002))) & (counts<w*.70))
    runs: list[list[int]] = []
    for y in occupied:
        if not runs or int(y)-runs[-1][-1] > 2:
            runs.append([int(y)])
        else:
            runs[-1].append(int(y))
    heights = sorted(run[-1]-run[0]+1 for run in runs if run[-1]-run[0]>=4)
    typical = float(height_hint or (np.percentile(heights, 30) if len(heights)>1 else 30))
    max_height = min(48, max(10, typical*1.55+2))
    out = []
    uncertain = False
    for ys in runs:
        y0, y1 = ys[0], ys[-1]+1
        if y1-y0 < 5:
            continue  # underlines, dots and borders are not complete text
        if y1-y0 > max_height or np.mean(ink[y0:y1]) > .48:
            uncertain = True
            continue
        xs = np.flatnonzero(ink[y0:y1].any(axis=0))
        if not xs.size or xs[-1]-xs[0] < 10:
            continue
        x0, x1 = max(0, int(xs[0])-8), min(w, int(xs[-1])+9)
        a, b = max(0, y0-3), min(h, y1+3)
        if b-a<11 and x1-x0>=w*.80:
            continue  # incomplete top/bottom panel rule, not a whole glyph
        original = bgr[a:b, x0:x1, :3].copy()
        local_edges = edges[x0:x1]
        original[:,local_edges] = bg[a:b,None,:].astype(np.uint8)
        # Keep soft edges instead of hard thresholding away small punctuation.
        crop_delta = delta[a:b, x0:x1].astype(np.float32).copy()
        crop_delta[:,local_edges] = 0
        foreground = crop_delta[ink[a:b, x0:x1]]
        peak = float(np.percentile(foreground,90)) if foreground.size else 100
        gain,offset = (min(16.,240/max(12.,peak-4)),4) if peak<55 else (3.4,8)
        neutral = 255-np.clip((crop_delta-offset)*gain,0,255).astype(np.uint8)
        neutral[crop_delta < thresholds[a:b,None]*.6] = 255
        neutral = cv2.cvtColor(neutral, cv2.COLOR_GRAY2BGR)
        # Ink identity is independent of screen Y: scrolling old lines costs
        # no recognition. Exact pixels/shape, never fuzzy matching item prices.
        key = hashlib.blake2b(neutral.tobytes()+str(neutral.shape).encode(), digest_size=16).digest()
        out.append(InkRow((x0, a, x1-x0, b-a), original, neutral, key))
    return out, uncertain


def supplement_white_rows(bgr, rows):
    """Fill uncovered white baselines beside successfully segmented banners.

    A successful coloured row is not evidence that every other baseline was
    read. Only source-anchored left-aligned white rows can fill a gap. Never
    replace existing geometry or admit a badge-only fragment as a new row.
    """
    added=[]
    for row in _bright_glyph_rows(bgr):
        x,y,w,h=row.rect
        if x > max(12, bgr.shape[1]*.025):
            continue
        if detect_band(bgr,row.rect).tone != 'none':
            continue
        mid=y+h/2
        if any(abs(mid-(r.rect[1]+r.rect[3]/2)) <= max(6,min(h,r.rect[3])*.5) for r in rows):
            continue
        added.append(row)
    return sorted(rows+added,key=lambda r:r.rect[1]),len(added)


def _bright_glyph_rows(bgr: np.ndarray) -> list[InkRow]:
    """Bounded rescue for light chat glyphs over moving/textured scenery.

    The source ROI remains unchanged. When the row-median segmentation cannot
    separate text from translucent map scenery, strong nearly-neutral light
    glyph cores can anchor individual line bounds. Avoid HUD scrollbar, solid
    horizontal UI rules, and graphic edges; never manufacture OCR text.
    """
    if bgr is None or bgr.ndim != 3 or bgr.shape[2] < 3:
        return []
    h, w = bgr.shape[:2]
    if h < 35 or w < 160:
        return []
    b, g, r = [bgr[:, :, channel].astype(np.int16) for channel in range(3)]
    maximum = np.maximum(np.maximum(b, g), r)
    minimum = np.minimum(np.minimum(b, g), r)
    # Bright foreground cores, not red/brown game scenery. This is ONLY an
    # emergency fallback and must never replace the normal colored-chat path.
    ink = ((b >= 130) & (g >= 135) & (r >= 130) & (maximum - minimum < 100))
    ink[:, :max(4, round(w * .006))] = False
    ink[:, w - max(20, round(w * .035)):] = False  # scrollbar/chrome
    ink[h - min(6, h // 9):, :] = False             # bottom UI rule
    projected = ink.sum(axis=1)
    occupied = np.flatnonzero((projected >= max(5, round(w * .010))) &
                              (projected <= w * .47))
    # Scanlines that are mostly 'bright' belong to a pale megaphone band or
    # UI strip, not to glyphs; keep them out of neighbouring white rows'
    # extents and masks (they widened a 270px line to 756px at 1080p).
    ink[projected > w * .47] = False
    runs: list[list[int]] = []
    for y in occupied:
        if not runs or int(y) - runs[-1][-1] > 3:
            runs.append([int(y)])
        else:
            runs[-1].append(int(y))
    found = []
    for run in runs:
        y0, y1 = run[0], run[-1] + 1
        if not (7 <= y1-y0 <= 24):
            continue
        # Glyph columns hold ink on 2+ scanlines; a 1px dotted strip edge
        # just below the text must not stretch the row across the ROI.
        xs = np.flatnonzero(ink[y0:y1].sum(axis=0) >= 2)
        if not xs.size or xs[-1] - xs[0] < 35:
            continue
        # A white sprite/speech balloon far to the right of the text joined
        # the row's extent (609px -> 742px on real 1080p footage) and fed
        # junk glyphs to OCR. Word gaps are a few px; split only at gaps
        # wider than 4 line heights. Chat lines start at the box's left edge
        # (wrapped lines are indented ~40px), so keep the leftmost part.
        gap = max(60, 4*(y1-y0))
        cuts = np.flatnonzero(np.diff(xs) > gap)
        if cuts.size:
            parts = [part for part in np.split(xs, cuts+1) if part[-1]-part[0] >= 12]
            if not parts:
                continue
            xs = parts[0]
            if xs[-1] - xs[0] < 35:
                continue
        # Re-attach 1-scanline glyph parts (a 'T' bar, '-') at either end.
        thin = np.flatnonzero(ink[y0:y1].any(axis=0))
        thin = thin[(thin >= xs[0]-4) & (thin <= xs[-1]+4)]
        x0, x1 = max(0, int(thin[0])-5), min(w, int(thin[-1])+6)
        top, bottom = max(0, y0-2), min(h, y1+2)
        local_ink = ink[top:bottom, x0:x1]
        if int(local_ink.sum()) < max(32, (x1-x0)*.16):
            continue
        original = bgr[top:bottom, x0:x1, :3].copy()
        # PP-OCR recognizer input is dark-on-light. The original color crop is
        # still retained for badge detection and Korean/item rereads.
        neutral = np.full_like(original, 255)
        neutral[local_ink] = 0
        key = hashlib.blake2b(neutral.tobytes() + str(neutral.shape).encode(),
                              digest_size=16).digest()
        found.append(InkRow((x0, top, x1-x0, bottom-top), original, neutral, key, True))
    return found


def _uncovered_band_rows(bgr, rows, height_hint=None):
    """Megaphone bands the bright-glyph rescue cannot see (dark text on a
    pink/yellow/cyan/slate strip). Segment just that strip with the normal
    row-median pass; on real 1080p footage a pink megaphone between white
    chat lines was otherwise never read.
    """
    from .vision import colorful_chat_regions, gray_blue_announcement_regions
    def covered(y0, y1):
        return any(y0 <= r.rect[1]+r.rect[3]/2 <= y1 or
                   r.rect[1] <= (y0+y1)/2 <= r.rect[1]+r.rect[3] for r in rows)
    found = []
    for x, y, bw, bh in list(colorful_chat_regions(bgr)) + list(gray_blue_announcement_regions(bgr)):
        if covered(y, y+bh):
            continue
        strip, _ = ink_rows(bgr[y:y+bh], height_hint)
        for row in strip:
            rx, ry, rw, rh = row.rect
            moved = InkRow((rx, ry+y, rw, rh), row.original, row.neutral, row.key)
            if not covered(moved.rect[1], moved.rect[1]+rh) and not any(
                    f.rect[1] <= moved.rect[1]+rh/2 <= f.rect[1]+f.rect[3] for f in found):
                found.append(moved)
    return found


def _upgrade_white_rows(bgr, rows, bright):
    """Swap a scenery-polluted white chat row for its clean glyph mask.

    The row-median pass can 'succeed' on white text over a busy map while
    its neutral image carries the bricks and sprites behind the letters
    (4-5x the glyph ink on real 1080p footage; clean white-on-dark chat is
    ~1.35x). Only rows without a megaphone band are eligible; band rows
    (whose white CH badge also looks 'bright') are never touched.
    """
    from .megaphone import detect_band
    if not bright:
        return rows, False
    out, changed = [], False
    for row in rows:
        cy = row.rect[1]+row.rect[3]/2
        inside = [b for b in bright if row.rect[1] <= b.rect[1]+b.rect[3]/2 <= row.rect[1]+row.rect[3]]
        # Never collapse a row that spans two text lines into one bright line.
        if (len(inside) == 1 and row.rect[3] <= inside[0].rect[3]*1.6
                and abs(inside[0].rect[1]+inside[0].rect[3]/2-cy) <= row.rect[3]*.35):
            glyphs = int(np.count_nonzero(inside[0].neutral[:, :, 0] < 128))
            ink = int(np.count_nonzero(row.neutral[:, :, 0] < 128))
            if glyphs >= 40 and ink > glyphs*2.5 and detect_band(bgr, row.rect).tone == 'none':
                out.append(inside[0])
                changed = True
                continue
        out.append(row)
    return out, changed


def ink_rows_border_retry(bgr: np.ndarray, height_hint=None, first=None) -> tuple[list[InkRow], bool, int]:
    """Retry line segmentation after removing OCR-ROI border/gutter pixels.

    Used ONLY when the regular segmentation is empty and uncertain. A player
    may select a rectangle a few pixels wider than the actual Maple message
    pane; including scrollbar chrome can turn 4 visible rows into 0. Do not
    discard/alter successful first-pass crops, and do not run extra model OCR.
    Every returned rectangle remains relative to the ORIGINAL frame.
    """
    original, uncertain = first if first is not None else ink_rows(bgr, height_hint)
    if bgr is None or bgr.size == 0:
        return original, uncertain, 0
    h, w = bgr.shape[:2]
    # A single full-width 8px border is not evidence of a readable message.
    # Do not retry a legitimate single chat line with normal text dimensions.
    only_border = (bool(original) and all(
        row.rect[2] >= w*.90 and row.rect[3] <= 14 for row in original))
    if original and not only_border and uncertain and w >= 160 and h >= 36:
        # Mixed frame: the row-median pass found some rows (e.g. a megaphone
        # band) but not white chat drawn over scenery between them. Add the
        # bright-glyph rows that no existing row covers; never replace one.
        def covers(a, b):
            return a.rect[1] <= b.rect[1]+b.rect[3]/2 <= a.rect[1]+a.rect[3]
        bright = _bright_glyph_rows(bgr)
        original, _ = _upgrade_white_rows(bgr, original, bright)
        # The chat input bar's bright top edge sits in the last ROI pixels
        # at 1080p; a row glued to it spans the whole width. Such a row is
        # replaced by the bright-glyph rows it covers, never kept over them.
        def tainted(row):
            x, y, rw, rh = row.rect
            return rw >= w*.90 and y+rh >= h-2 and any(covers(row, b) or covers(b, row) for b in bright)
        kept = [row for row in original if not tainted(row)]
        extra = [row for row in bright
                 if not any(covers(o, row) or covers(row, o) for o in kept)]
        if extra:
            merged = kept+extra
            merged += _uncovered_band_rows(bgr, merged, height_hint)
            return sorted(merged, key=lambda row: row.rect[1]), True, 1
    if original and not only_border and not uncertain and w >= 160 and h >= 36:
        upgraded, changed = _upgrade_white_rows(bgr, original, _bright_glyph_rows(bgr))
        if changed:
            return upgraded, uncertain, 1
    if (original and not only_border) or not uncertain:
        return original, uncertain, 0
    if w < 160 or h < 36:
        return original, uncertain, 0
    # A real chat may be readable to a human yet vanish from row-median ink
    # segmentation when the map background shows through the chat pane.
    # Reconstruct only line geometry from bright glyph cores, then pass each
    # actual source-color crop through exactly the existing recognizer path.
    bright = _bright_glyph_rows(bgr)
    if bright:
        bright += _uncovered_band_rows(bgr, bright, height_hint)
        return sorted(bright, key=lambda row: row.rect[1]), True, 1
    # Strictly bounded attempt count. No repeated expensive full-detector calls.
    attempts = (
        (max(3, round(w * .005)), max(22, round(w * .05)), 0),
        (max(5, round(w * .009)), max(22, round(w * .05)), min(10, h // 8)),
        (max(3, round(w * .005)), max(28, round(w * .07)), min(12, h // 8)),
    )
    best=None
    for left, right, bottom in attempts:
        if w-left-right < 120 or h-bottom < 28:
            continue
        crop=bgr[:h-bottom if bottom else h, left:w-right]
        lines, caution = ink_rows(crop, height_hint)
        # Only accept evidence of multiple plausible text rows, not a single
        # horizontal HUD border or isolated game ornament.
        credible=[r for r in lines if 11 <= r.rect[3] <= 45
                  and 10 <= r.rect[2] <= round(crop.shape[1]*.94)]
        if len(credible) < 2:
            continue
        score=(len(credible), not caution, len(lines))
        if best is None or score > best[0]:
            best=(score,left,lines,caution)
    if best is None:
        return original, uncertain, 0
    _, left, chosen, caution=best
    # The fallback is accepted only for visible text rows; huge full-width
    # strips are panel borders. Keep legitimate near-full-width lines if they
    # are at least a normal line high and do not look like an 8px rule.
    result=[]
    for r in chosen:
        if r.rect[3] < 11:
            continue
        x,y,rw,rh=r.rect
        result.append(InkRow((x+left,y,rw,rh),r.original,r.neutral,r.key))
    return (result, caution, 1) if len(result)>=2 else (original, uncertain, 0)


def _padded(image: np.ndarray, neutral: bool) -> np.ndarray:
    color = (255, 255, 255) if neutral else tuple(int(x) for x in np.median(image, axis=(0, 1)))
    return cv2.copyMakeBorder(image, 5, 5, 5, 5, cv2.BORDER_CONSTANT, value=color)


def _trim_piece(neutral, original):
    ys,xs=np.where(neutral[:,:,0]<235)
    if not xs.size:
        return neutral,original
    # Body descenders must not change a name-prefix cache's image height.
    box=(slice(int(ys.min()),int(ys.max())+1),slice(int(xs.min()),int(xs.max())+1))
    neutral=neutral[box].copy();original=original[box].copy()
    color=tuple(int(v) for v in np.median(original,axis=(0,1)))
    return (cv2.copyMakeBorder(neutral,2,2,2,2,cv2.BORDER_CONSTANT,value=(255,255,255)),
            cv2.copyMakeBorder(original,2,2,2,2,cv2.BORDER_CONSTANT,value=color))


def _stable_piece(original, with_offset=False, neutral=None):
    if neutral is None:
        neutral=neutral_ink(original)
    _,xs=np.where(neutral[:,:,0]<235)
    offset=int(xs.min())-2 if xs.size else 0
    pair=_trim_piece(neutral,original)
    return (pair,offset) if with_offset else pair


def _mask_piece(neutral, original):
    """Name/body piece of a bright-glyph row from its clean binary mask.

    Re-neutralizing the colour crop (``_stable_piece``) would bring back the
    scenery that the bright-glyph mask already removed.
    """
    _,xs=np.where(neutral[:,:,0]<235)
    offset=int(xs.min())-2 if xs.size else 0
    return _trim_piece(neutral.copy(),original.copy()),offset


class RecoveryGate:
    """Bound costly full-detector calls, including unsuccessful recoveries.

    Cache keys use foreground line masks rather than raw semi-transparent BGR.
    Every detector invocation, even when it finds nothing, consumes budget.
    """
    def __init__(self, max_items=256, backoff=(0.5, 2.0, 8.0),
                 duty=2.0, no_ink_interval=5.0):
        self.items = OrderedDict()
        self.max_items = int(max_items)
        self.backoff = tuple(float(n) for n in backoff)
        self.duty = float(duty)
        self.no_ink_interval = float(no_ink_interval)
        self.next_global_ok = float('-inf')
        self.last_no_ink = float('-inf')

    def lookup(self, key):
        entry = self.items.get(key)
        if entry is not None:
            self.items.move_to_end(key)
        return entry

    def block_reason(self, key, now, has_ink):
        if now < self.next_global_ok:
            return 'global_duty'
        entry = self.items.get(key)
        if entry is not None and now < entry['next_ok']:
            return 'failed_backoff'
        if not has_ink and now - self.last_no_ink < self.no_ink_interval:
            return 'no_ink_interval'
        return ''

    def record(self, key, rows, started, finished, has_ink):
        # Absolute ready time is computed from detector completion, not its
        # start. Slow calls must cause a proportionally longer cooldown.
        finished = max(float(started), float(finished))
        wall = finished-float(started)
        self.next_global_ok = finished + max(0.3, self.duty * wall)
        if not has_ink:
            self.last_no_ink = finished
        entry = self.items.setdefault(key, {'rows': None, 'fails': 0,
                                             'next_ok': float('-inf')})
        if rows:
            # Never replay a recovered sentence on a screen whose segmentation
            # found no ink. A real message can be recovered in that frame, but
            # replaying it on later blank frames would create ghost chat.
            entry['rows'] = rows if has_ink else None
            entry['fails'] = 0
            entry['next_ok'] = finished
        else:
            entry['rows'] = None
            entry['fails'] += 1
            index = min(entry['fails']-1, len(self.backoff)-1)
            entry['next_ok'] = finished + self.backoff[index]
        self.items.move_to_end(key)
        while len(self.items) > self.max_items:
            self.items.popitem(last=False)


def _recovery_mask_digest(row):
    # Character mask, not raw BGR.
    ink = row.neutral[:, :, 0] < 205
    h, w = row.neutral.shape[:2]
    return hashlib.blake2b(f'{w}x{h}:'.encode('ascii')+np.packbits(ink).tobytes(),
                           digest_size=16).digest()


def ink_recovery_key(frame, rows, digests=None):
    """Foreground-only hash; ignore animated, translucent game background.

    Preserve row positions to avoid replaying success at a scrolled-out
    location. The actual OCR row neutralization is already background-aware;
    quantizing its grayscale channel avoids low-amplitude background jitter.
    ``digests`` maps a row proven identical to an earlier OCR'd row onto that
    row's mask digest, so 1-2px edge flicker does not force a detector run.
    """
    size = frame.shape[:2]
    digest = hashlib.blake2b(digest_size=16)
    digest.update(f'{size[0]}x{size[1]}:'.encode('ascii'))
    if not rows:
        digest.update(b'no-segmented-ink')
    else:
        for row in rows:
            # Keep exact vertical position: never replay a recovered line
            # after the chat scrolls. Horizontal extents follow the glyphs.
            digest.update(f'{row.rect[1]}:{row.rect[3]}:'.encode('ascii'))
            digest.update((digests or {}).get(row.key) or _recovery_mask_digest(row))
    return digest.digest()


def ink_signature(neutral):
    """Glyph mask trimmed to its own box, independent of crop margins."""
    mask = neutral[:, :, 0] < 128 if neutral.ndim == 3 else neutral < 128
    ys, xs = np.nonzero(mask)
    if xs.size < 12:
        return None
    y0, y1, x0, x1 = int(ys.min()), int(ys.max())+1, int(xs.min()), int(xs.max())+1
    return mask[y0:y1, x0:x1].copy(), x0, int(xs.size)


def aligned_masks(first, second, slack=1):
    """Best top-left alignment (within ``slack`` px) of two trimmed masks.

    One flickering pixel on the outermost column/row moves a trimmed box by
    1px; compare in a shared canvas instead of requiring identical boxes.
    Returns (a, b, dx) with dx = second's x offset relative to first, or None.
    """
    a, b = first[0], second[0]
    if abs(a.shape[0]-b.shape[0]) > 2*slack or abs(a.shape[1]-b.shape[1]) > 2*slack:
        return None
    height = max(a.shape[0], b.shape[0]) + 2*slack
    width = max(a.shape[1], b.shape[1]) + 2*slack
    canvas_a = np.zeros((height, width), bool)
    canvas_a[slack:slack+a.shape[0], slack:slack+a.shape[1]] = a
    best = None
    for dy in range(0, 2*slack+1):
        for dx in range(0, 2*slack+1):
            if dy+b.shape[0] > height or dx+b.shape[1] > width:
                continue
            canvas_b = np.zeros((height, width), bool)
            canvas_b[dy:dy+b.shape[0], dx:dx+b.shape[1]] = b
            changed = int(np.count_nonzero(canvas_a ^ canvas_b))
            if best is None or changed < best[0]:
                best = (changed, canvas_b, dx-slack)
    if best is None:
        return None
    return canvas_a, best[1], best[2]


_EDGE = np.ones((3, 3), np.uint8)


def near_identical_ink(first, second):
    """True only for edge flicker on identical glyphs, never a text change.

    Moving scenery behind translucent/outlined chat and lossy capture flip a
    few pixels on stroke edges, which changes the exact hash every frame and
    re-runs every model on unchanged text. Accept a difference only when it is
    small (<=3% of the ink), every differing pixel touches ink that BOTH
    images share, and no differing blob exceeds 2px. A period, colon dot,
    digit stroke or extra letter is a separate blob or >2px and therefore
    always rejected; scattered 1-2px edge flips are not a text change.
    """
    if first is None or second is None:
        return False
    pair = aligned_masks(first, second)
    if pair is None:
        return False
    a, b, _ = pair
    diff = a ^ b
    changed = int(np.count_nonzero(diff))
    if changed == 0:
        return True
    if changed > max(3, int(min(first[2], second[2]) * .03)):
        return False
    common = cv2.dilate((a & b).astype(np.uint8), _EDGE).astype(bool)
    if np.any(diff & ~common):
        return False
    _, _, stats, _ = cv2.connectedComponentsWithStats(diff.astype(np.uint8), 8)
    return int(stats[1:, cv2.CC_STAT_AREA].max()) <= 2


def shift_prep(neutral):
    """Blurred ink intensity, trimmed: tolerant to the game's sub-pixel
    resampling when a line scrolls by a non-integer number of pixels."""
    g = 255-cv2.cvtColor(neutral, cv2.COLOR_BGR2GRAY).astype(np.float32) if neutral.ndim == 3         else 255-neutral.astype(np.float32)
    ys, xs = np.nonzero(g > 90)
    if xs.size < 20:
        return None
    g = g[max(0, ys.min()-2):ys.max()+3, max(0, xs.min()-2):xs.max()+3]
    return cv2.GaussianBlur(g, (0, 0), 1.0)


def shift_difference(a, b):
    """Mean blurred-ink difference (0..1) at the best small alignment.

    Same line after a scroll: <= .06 on the R17 recording (p99 .09);
    different lines: >= .07 (p1). Callers require agreement of several rows.
    """
    if a is None or b is None or abs(a.shape[0]-b.shape[0]) > 4 or abs(a.shape[1]-b.shape[1]) > 6:
        return None
    best = None
    for dy in range(-2, 3):
        for dx in range(-3, 4):
            ay, by = max(0, dy), max(0, -dy)
            ax, bx = max(0, dx), max(0, -dx)
            h = min(a.shape[0]-ay, b.shape[0]-by)
            w = min(a.shape[1]-ax, b.shape[1]-bx)
            if h < 8 or w < 20:
                continue
            d = float(np.abs(a[ay:ay+h, ax:ax+w]-b[by:by+h, bx:bx+w]).mean())/255
            if best is None or d < best:
                best = d
    return best


_SPAM_GLYPHS = set('@~#②③①④⑤⑥©∂Φσ')


def spam_dominated(text):
    """'Nick : J>PQ @@@@@@@@@@@@': the decoration is dropped before
    translation anyway, so a second/Korean read of it is wasted time."""
    chars = [c for c in str(text) if not c.isspace()]
    return len(chars) >= 8 and sum(c in _SPAM_GLYPHS for c in chars) >= len(chars)*.5


class RowGrid:
    """Maple chat lines sit on a fixed pitch (22px at 1080p). Learn it.

    R17 live recording: the projection cut the same line as y=52 h=15 on one
    frame and y=48 h=21 on the next, chopping ascenders, so an unchanged line
    looked new (and read differently) frame after frame.
    """
    def __init__(self):
        self.pitch = None
        self.phase = None

    def observe(self, rows):
        centres = [r.rect[1]+r.rect[3]/2 for r in rows if not r.bright]
        gaps = [b-a for a, b in zip(centres, centres[1:]) if 14 <= b-a <= 34]
        if gaps:
            p = float(np.median(gaps))
            self.pitch = p if self.pitch is None else .9*self.pitch+.1*p
        if not self.pitch or not centres:
            return
        P = self.pitch
        ang = np.array([(c % P)/P*2*np.pi for c in centres])
        mean = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2*np.pi)
        phase = mean/(2*np.pi)*P
        if self.phase is None:
            self.phase = phase
        else:
            # circular EMA
            d = (phase-self.phase+P/2) % P-P/2
            self.phase = (self.phase+.2*d) % P

    def bands(self, row):
        """Fixed (top, bottom) bands covering the row, or None if unknown."""
        if not self.pitch or self.phase is None:
            return None
        P, O = self.pitch, self.phase
        y0, y1 = row.rect[1], row.rect[1]+row.rect[3]
        first = int(np.floor((y0+3-O)/P+.5))
        last = int(np.floor((y1-3-O)/P+.5))
        out = []
        for k in range(first, max(first, last)+1):
            g = O+k*P
            out.append((int(round(g-P/2))-2, int(round(g+P/2))+2))
        return out


def grid_row(bgr, row, band):
    """Re-cut ``row`` inside a fixed band: same line -> same pixels."""
    h = bgr.shape[0]
    a, b = max(0, band[0]), min(h, band[1])
    if b-a < 10:
        return None
    inner, _ = ink_rows(bgr[a:b])
    if not inner:
        return None
    best = max(inner, key=lambda r: int(np.count_nonzero(r.neutral[:, :, 0] < 128)))
    x0, iy, iw, ih = best.rect
    neutral = np.full((b-a, iw, 3), 255, np.uint8)
    neutral[iy:iy+ih] = best.neutral
    original = bgr[a:b, x0:x0+iw, :3].copy()
    key = hashlib.blake2b(neutral.tobytes()+str(neutral.shape).encode(), digest_size=16).digest()
    return InkRow((x0, a, iw, b-a), original, neutral, key)


def snap_rows(bgr, rows, grid):
    """Rows re-cut on the learned line grid; rows it cannot place stay."""
    if not rows or grid is None:
        return rows
    out = []
    for row in rows:
        bands = None if row.bright else grid.bands(row)
        if not bands or len(bands) > 3:
            out.append(row)
            continue
        cut = [grid_row(bgr, row, band) for band in bands]
        cut = [c for c in cut if c is not None]
        if not cut:
            out.append(row)
            continue
        out.extend(cut)
    seen, unique = set(), []
    for r in sorted(out, key=lambda r: r.rect[1]):
        if r.rect[1] in seen:
            continue
        seen.add(r.rect[1])
        unique.append(r)
    return unique


_NEAR3 = np.ones((3, 3), np.uint8)
_NEAR5 = np.ones((5, 5), np.uint8)


def stable_signature(neutral):
    """Glyph mask without isolated scenery specks, trimmed to its box.

    Moving map pixels behind the translucent chat leave 1-2px specks in the
    ink mask that are far from any letter; they changed the trimmed box and
    made the same chat line look new on every frame (R17 live recording:
    ~2.4 of 4 rows re-read per frame). Specks that touch letters - a decimal
    point beside a digit, a period after a word - are kept.
    """
    mask = (neutral[:, :, 0] < 128 if neutral.ndim == 3 else neutral < 128).astype(np.uint8)
    if np.count_nonzero(mask) < 12:
        return None
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return None
    area = stats[:, cv2.CC_STAT_AREA]
    big_labels = np.flatnonzero(area >= 3)
    big = np.isin(labels, big_labels[big_labels > 0])
    reach = cv2.dilate(big.astype(np.uint8), _NEAR5).astype(bool)
    keep = mask.astype(bool) & (big | reach)
    ys, xs = np.nonzero(keep)
    if xs.size < 12:
        return None
    y0, y1, x0, x1 = int(ys.min()), int(ys.max())+1, int(xs.min()), int(xs.max())+1
    return keep[y0:y1, x0:x1].copy(), x0, int(xs.size)


def same_line_ink(first, second):
    """Same chat line under flicker: edge noise allowed, new marks rejected.

    Differences hugging letters both images share (anti-aliased stroke edges)
    may reach 8% of the ink. Any difference away from shared letters must be
    a 1-2px speck; a new period, decimal point, digit or letter is larger and
    always means a different line.
    """
    if first is None or second is None:
        return False
    pair = aligned_masks(first, second, slack=2)
    if pair is None:
        return False
    a, b, _ = pair
    diff = a ^ b
    changed = int(np.count_nonzero(diff))
    if changed == 0:
        return True
    if changed > max(4, int(min(first[2], second[2]) * .08)):
        return False
    common = cv2.dilate((a & b).astype(np.uint8), _NEAR3).astype(bool)
    off = (diff & ~common).astype(np.uint8)
    if not off.any():
        return True
    _, _, stats, _ = cv2.connectedComponentsWithStats(off, 8)
    return int(stats[1:, cv2.CC_STAT_AREA].max()) <= 2


class IncrementalChatOCR:
    def __init__(self, recognizer, clock=time.monotonic):
        self.recognizer = recognizer
        self.clock = clock
        self.cache: OrderedDict[bytes, tuple[str, float, float]] = OrderedDict()
        self.stable_reads = {}
        self.piece_paired = {}
        self._candidate_paired = []
        # R16: live 1080p trace showed the detector (~2.5 s) running on 20% of
        # frames for 'uncertain' rows while finding no more new lines than an
        # ordinary frame. Rest 4x its own duration (was 2x) between probes.
        # R17: live detector calls took 1.26 s each and found no more new
        # rows than ordinary frames; rest 12x the last call instead of 4x.
        self.recovery_gate = RecoveryGate(duty=12.0)
        # ...and probe at 1.5x instead of the OCR scale (2.0): ~44% fewer pixels.
        self.recovery_scale_cap = 1.5
        self.glyph_debug = GlyphDebugRecorder(enabled=False)
        self.glyph_dictionary_enabled = False
        self.glyph_dictionary = GlyphDictionary()
        self.glyph_resolution = 'unknown'
        self.glyph_dpi = 'unknown'
        self._glyph_profile = None
        self._glyph_colors_by_kind = {}
        self.stats: dict = {}
        self.book = LatencyBook()
        self.badges = BadgeSplitter()
        self.piece_cache = OrderedDict()
        self.height_hint = None
        self.stage = {}
        self._char_confidences=[]
        self._recognition_infos=[]
        self._candidate_regions=[]
        self._candidate_ends=[]
        self.linked_items=LinkedItemOCR(getattr(recognizer,'korean_link_ocr',getattr(recognizer,'korean_ocr',None)))
        self.row_meta={}
        self.piece_links={}
        self.piece_ends={}
        self._last_frame=None
        self._last_output=[]
        self._last_origin=(0,0)
        self._last_at=-100.
        self.totals = {'rows':0,'recognition_inputs':0,'retry_rows':0,'korean_rows':0,'frames':0,'recoveries':0}
        self.split_keys = set()
        # Glyph masks of rows that were actually OCR'd, for edge-flicker reuse.
        self.near_index = OrderedDict()
        # Speck-free glyph masks for re-identifying a line under scenery (R17)
        self.stable_index = OrderedDict()
        self.stable_line_reuse = False
        self.row_grid = RowGrid()
        self.grid_rows_enabled = False
        # R17: reuse reads of lines that merely scrolled (see _scroll_reuse)
        self.scroll_reuse = True
        self._prev_rows = []
        self.canonical = {}
        self.mask_digest = {}
        # White outlined chat over scenery (bright-glyph rows): cut name/body
        # pieces from the clean binary mask, and use the full-frame detector
        # only as a periodic add-only probe. Measured on a real 1080p
        # recording; set these two back to False/True to restore R11.
        self.bright_mask_pieces = True
        self.bright_detector_recovery = False
        self.bright_probe_interval = 1.0
        self.bright_keep_confidence = .80
        self._last_bright_probe = float('-inf')

    def _scroll_reuse(self, segments, missing, values):
        """Lines that only scrolled keep their earlier read.

        Maple never edits a chat line in place: new text pushes old lines up
        by whole line pitches. Find the pitch shift (0-4 lines) under which
        at least two rows match the previous frame's rows and none disagree,
        then reuse those rows' reads instead of running the line model again
        (R17: 2-3 re-reads per frame, ~170 ms each, and each re-read could
        spell the same line differently -> duplicate translations).
        """
        prev = self._prev_rows
        if not prev:
            return []
        current = [(row.rect[1]+row.rect[3]/2, row, shift_prep(row.neutral)) for row in segments]
        # Candidate scroll distances come from rows that look alike; lines
        # only move up (old y >= new y). No assumed pitch: the learned one
        # was wrong (28 vs 22.4 px) on mixed megaphone/white frames.
        diffs = {}
        offsets = []
        for ci, (cy, row, prep) in enumerate(current):
            for pi, (oy, old_key, old_prep) in enumerate(prev):
                if oy < cy-3:
                    continue
                d = shift_difference(prep, old_prep)
                diffs[ci, pi] = d
                if d is not None and d <= .07:
                    offsets.append(oy-cy)
        best = None
        for offset in sorted(set(round(o) for o in offsets)):
            matches, bad = [], 0
            for ci, (cy, row, prep) in enumerate(current):
                if prep is None:
                    continue
                target = cy+offset
                near = [(abs(p[0]-target), pi) for pi, p in enumerate(prev) if abs(p[0]-target) <= 4]
                if not near:
                    continue
                pi = min(near)[1]
                d = diffs.get((ci, pi))
                if d is None or d > .15:
                    bad += 1            # clearly another line: wrong shift
                elif d <= .07:
                    matches.append((row, prev[pi][1]))
                # .07-.15: unsure; neither evidence nor reuse
            if bad == 0 and len(matches) >= 2 and (best is None or len(matches) > len(best)):
                best = matches
        if not best:
            return []
        reused = []
        for row, old_key in best:
            if row.key not in missing:
                continue
            entry = self.cache.get(old_key)
            if not entry or not entry[0]:
                continue
            # A weak first read gets another chance now and then instead of
            # being carried along for the whole time the line is visible.
            if entry[1] < .80 and self.clock()-entry[2] > 1.5:
                continue
            self.cache[row.key] = entry
            self.cache.move_to_end(row.key)
            self.stable_reads[row.key] = self.stable_reads.get(old_key, 1)
            self.canonical[row.key] = self.canonical.get(old_key, old_key)
            if old_key in self.split_keys:
                self.split_keys.add(row.key)
            meta = self.row_meta.get(old_key)
            if meta is not None:
                self.row_meta[row.key] = dict(meta)
            values[row.key] = entry[:2]
            reused.append(row.key)
        return reused

    def _near_match(self, row, now):
        """Reuse a read when only stroke edges / scenery specks changed."""
        signature = ink_signature(row.neutral)
        if signature is None:
            return None
        stable = stable_signature(row.neutral) if self.stable_line_reuse else None
        for key in reversed(self.near_index):
            other = self.near_index[key]
            entry = self.cache.get(key)
            if entry is None or not entry[0]:
                continue
            strict = (other is not None and abs(other[0].shape[0]-signature[0].shape[0]) <= 2
                      and abs(other[0].shape[1]-signature[0].shape[1]) <= 2
                      and entry[1] >= .85
                      and now-entry[2] < cache_ttl(entry[0], entry[1], self.stable_reads.get(key, 0))
                      and near_identical_ink(signature, other))
            if not strict:
                # R17: the same physical line seen again under moving scenery.
                # Weak reads are reused too: re-reading identical ink gives
                # the same weak text and cost 170 ms per line on fast chat.
                if stable is None or entry[1] < .60:
                    continue
                if now-entry[2] >= max(4., cache_ttl(entry[0], entry[1], self.stable_reads.get(key, 0))):
                    continue
                if not same_line_ink(stable, self.stable_index.get(key)):
                    continue
            # Keep the ORIGINAL read time: the periodic re-read policy still
            # applies to the physical text, not to each noisy copy of it.
            if stable is not None:
                self.stable_index[row.key] = stable
                self.stable_index.move_to_end(row.key)
            self.cache[row.key] = entry
            self.cache.move_to_end(row.key)
            self.stable_reads[row.key] = self.stable_reads.get(key, 1)
            self.canonical[row.key] = self.canonical.get(key, key)
            if key in self.split_keys:
                self.split_keys.add(row.key)
            meta = self.row_meta.get(key)
            if meta is not None:
                pair = aligned_masks(other, signature)
                shift = signature[1]-other[1]-(pair[2] if pair else 0)
                moved = dict(meta)
                for name in ('name_end', 'body_start'):
                    if isinstance(moved.get(name), (int, float)) and moved[name]:
                        moved[name] = moved[name]+shift
                moved['item_ranges'] = [(a+shift, b+shift) for a, b in meta.get('item_ranges', [])]
                self.row_meta[row.key] = moved
            return entry[:2]
        return None

    def _recognize(self, images: list[np.ndarray]):
        # RapidOCR 3.10's public recognition stage accepts already-cut lines.
        # This skips BOTH text detection and 0/180-degree classification.
        # Explicit cubic interpolation was compared against internal linear
        # resizing on labelled crops; the primary model always expects H=48.
        images = [cv2.resize(im,(max(1,round(im.shape[1]*48/im.shape[0])),48),
                            interpolation=cv2.INTER_CUBIC) for im in images]
        recognize=getattr(self.recognizer,'recognize_lines',self.recognizer.ocr.recognize_txt)
        result=recognize(images)
        self._last_recognition_batches=int(getattr(result,'batches',1))
        # Model input dimensions AFTER fixed-height (48px) preprocessing.
        if images:
            self.stage['rec_input_max_width_px']=max(self.stage['rec_input_max_width_px'],max(im.shape[1] for im in images))
            self.stage['rec_input_max_height_px']=max(self.stage['rec_input_max_height_px'],max(im.shape[0] for im in images))
            self.stage['rec_input_total_pixels']+=sum(im.shape[0]*im.shape[1] for im in images)
        texts = list(getattr(result, 'txts', None) or [])
        scores = list(getattr(result, 'scores', None) or [])
        words=list(getattr(result,'word_results',None) or [])
        self._recognition_infos=[words[i] if i<len(words) else None for i in range(len(texts))]
        self._char_confidences=[]
        for i,text in enumerate(texts):
            raw=str(text)
            conf=list(getattr(words[i],'confs',[]) or []) if i<len(words) else []
            offset=len(raw)-len(raw.lstrip())
            self._char_confidences.append(conf[offset:offset+len(raw.strip())] if len(conf)==len(raw) else [])
        return [(str(t).strip(), float(s)) for t, s in zip(texts, scores)]

    def _candidates(self, tasks, confirm_indices=(), source_indices=()):
        if not tasks:
            return []
        self.stage['recognition_inputs']+=len(tasks)
        started = self.clock()
        # White text over scenery retains its anti-aliased strokes in the
        # actual source crop. Binary rescue masks locate rows, but erase
        # punctuation/descenders when used as the primary recognizer input.
        source_indices=set(source_indices)
        primary = self._recognize([_padded(t[1] if i in source_indices else t[0],
                                          i not in source_indices)
                                   for i,t in enumerate(tasks)])
        primary_chars=list(self._char_confidences)
        primary_infos=list(self._recognition_infos)
        initial = list(primary)
        paired = [False]*len(tasks)
        self.stage['primary_ms'] += (self.clock()-started)*1000
        self.stage['recognition_batches'] += getattr(self,'_last_recognition_batches',1)
        if len(primary) != len(tasks):
            raise RuntimeError('OCR recognition result count mismatch')
        critical={i for i,(text,score) in enumerate(primary) if needs_critical_retry(text,primary_chars[i])}
        self.stage['critical_retry_rows']+=len(critical)
        confirm = set(confirm_indices)
        retry = [i for i,(text,score) in enumerate(primary)
                 if (not text or score < (.94 if i in confirm else .88) or i in critical)
                 and not (i not in critical and spam_dominated(text))]
        if retry:
            started = self.clock()
            alt = self._recognize([_padded(tasks[i][0] if i in source_indices else tasks[i][1],
                                          i in source_indices) for i in retry])
            alt_chars=list(self._char_confidences)
            alt_infos=list(self._recognition_infos)
            self.stage['retry_ms'] += (self.clock()-started)*1000
            self.stage['recognition_batches'] += getattr(self,'_last_recognition_batches',1)
            self.stage['retry_rows'] += len(retry)
            for n,(i,other) in enumerate(zip(retry,alt)):
                text,score=primary[i]
                paired[i] = (min(score,other[1]) >= .82 and same_read(text,other[0])
                             and not np.array_equal(tasks[i][0],tasks[i][1]))
                if price_read_resolves(primary[i],other):
                    primary[i]=other
                    primary_infos[i]=alt_infos[n]
                    continue
                if (i in critical or re.search(r'(?i)\b(?:att|atk|scroll|gfa|gma)\b|\d\s*%|\+\s*\d',text)) and not same_numeric_fields(text,other[0]):
                    self.stage['numeric_retry_disagreements']+=1
                    primary[i]=(text,min(score,.87))
                    continue
                if i in critical and loses_known_terms(text,other[0]):
                    self.stage['term_retry_rejections']+=1
                    continue
                better=prefer_critical_read(primary[i],other,primary_chars[i],alt_chars[n]) if i in critical else False
                if better or other[1]>score+.025 or (parse_chat_line(other[0]) and not parse_chat_line(text) and other[1]>=score-.03):
                    primary[i]=other
                    primary_infos[i]=alt_infos[n]
        korean=getattr(self.recognizer,'korean_ocr',None)
        # A recognized [item] must not suppress Korean recognition for its
        # trailing ordinary Korean text (e.g. [아이템] 팝니다). The Korean full-
        # line OCR is only accepted when it repairs a missing Hangul suffix
        # without replacing already-known brackets, prices or English terms.
        mixed=[i for i,(text,score) in enumerate(primary) if
               (score < .83 or re.search(r'[\u3400-\u9fff가-힣]',text))
               and not spam_dominated(text)
               and not link_regions(text,primary_infos[i],tasks[i][0])]
        # A false CJK glyph inside a linked item must not be excluded merely
        # because the English OCR detector found [ ... ] boundaries.
        damaged_links = [i for i,(text,score) in enumerate(primary) if
                         re.search(r'\[[^\]\n]*[\u3400-\u9fff\u3040-\u30ff][^\]\n]*\]', text)
                         or re.search(r'\[\s*\]', text)]
        mixed.extend(i for i in damaged_links if i not in mixed)
        linked_suffix=[i for i,(text,score) in enumerate(primary) if
                       re.search(r'\[[^\]\n]+\]',text)
                       and not re.search(r'[가-힣]',re.sub(r'\[[^\]\n]*\]','',text))
                       and (text.rstrip().endswith(']') or score < .94)]
        mixed.extend(i for i in linked_suffix if i not in mixed)
        if korean is not None and mixed:
            started=self.clock()
            korean_images=[_padded(tasks[i][1],False) for i in mixed]
            self.stage['korean_input_max_width_px']=max(self.stage['korean_input_max_width_px'],max(im.shape[1] for im in korean_images))
            self.stage['korean_input_max_height_px']=max(self.stage['korean_input_max_height_px'],max(im.shape[0] for im in korean_images))
            self.stage['korean_input_total_pixels']+=sum(im.shape[0]*im.shape[1] for im in korean_images)
            alt=korean.recognize_txt(korean_images)
            self.stage['korean_ms']+=(self.clock()-started)*1000
            self.stage['recognition_batches']+=1
            self.stage['korean_rows']+=len(mixed)
            for i,text,score in zip(mixed,alt.txts or [],alt.scores or []):
                base,confidence=primary[i]
                # Bracket labels with foreign CJK OCR artifacts get a second
                # chance via the Korean recognizer. Accept only a bracketed
                # Hangul result with exactly preserved NON-ITEM numeric fields.
                from .linked_ocr import repair_corrupt_bracket
                repaired=repair_corrupt_bracket(base, str(text), float(score))
                if repaired is not None:
                    primary[i]=(repaired, min(float(score), confidence))
                    continue
                same=same_numeric_fields(base,text)
                cjk=bool(re.search(r'[\u3400-\u9fff]',base))
                if same and re.search('[가-힣]',text) and float(score)>=.80 and (float(score)>confidence+.025 or (cjk and float(score)>=confidence-.02)):
                    # Replacing the whole line can corrupt correct English
                    # item names. Only do so when no source link is present.
                    if not re.search(r'\[[^\]\n]+\]',base):
                        primary[i]=(str(text).strip(),float(score))
                if i in linked_suffix and float(score) >= .84:
                    current=re.search(r'\[[^\]\n]+\]\s*$',base)
                    recovered=re.search(r'\[[^\]\n]+\]\s*([가-힣][가-힣\s.,!?]{1,30})\s*$',str(text))
                    if current and recovered:
                        suffix=recovered.group(1).strip()
                        # Restrict to recognizable trading sentences or chat
                        # words; do not insert fabricated OCR-only fragments.
                        if re.search(r'(?:팝니다|삽니다|판매|구매|구해요|합니다|있어요|주세요)',suffix):
                            primary[i]=(base.rstrip()+' '+suffix,min(float(score),confidence))
        self._candidate_regions=[link_regions(text,info,tasks[i][0]) for i,((text,_),info) in enumerate(zip(primary,primary_infos))]
        self._candidate_ends=[]
        for (text,_),info,(neutral,_) in zip(primary,primary_infos,tasks):
            centres=character_centres(text,info,neutral.shape[1]+10)
            last=next((c for c in reversed(centres) if c is not None),None) if centres else None
            self._candidate_ends.append(min(neutral.shape[1],round(last-5+neutral.shape[0]*.25)) if last else None)
        started=self.clock()
        primary=self.linked_items.correct(primary,tasks,primary_infos)
        self._candidate_paired = [agree and same_read(before[0],after[0])
                                  for agree,before,after in zip(paired,initial,primary)]
        self.stage['item_ocr_ms']+=(self.clock()-started)*1000
        for key,value in self.linked_items.stats.items():self.stage[key]+=value
        self.stage['recognition_batches']+=self.linked_items.stats.get('item_ocr_batches',0)
        return primary

    def _read_rows(self, rows):
        now=self.clock()
        tasks=OrderedDict()
        confirm_keys=set()
        source_keys=set()
        plans=[]
        for row in rows:
            ordinary = detect_band(row.original,(0,0,row.original.shape[1],row.original.shape[0])).tone == 'none'
            # A wide rescue span can include a background sign beside the
            # chat. Restrict the source-first path to compact text lines;
            # long spans retain the mask/split path and its body geometry.
            if row.isolated_white and ordinary and row.rect[2] <= row.rect[3]*15:
                key=('full',row.key)
                tasks.setdefault(key,(row.neutral,row.original))
                confirm_keys.add(key)
                source_keys.add(key)
                plans.append((row,None,key,False,0,0,0,0))
                self.stage['source_first_rows']=self.stage.get('source_first_rows',0)+1
                continue
            badge_started=self.clock()
            split=self.badges.split(row.original,row.neutral)
            via_badge = split is not None
            if split is None:
                split = self.badges.split_plain(row.original, row.neutral)
            self.stage['badge_ms']+=(self.clock()-badge_started)*1000
            if split is None:
                key=('full',row.key)
                tasks.setdefault(key,(row.neutral,row.original))
                if ordinary:
                    confirm_keys.add(key)
                plans.append((row,None,key,False,0,0,0,0))
                continue
            end,start,quality=split
            if getattr(row,'bright',False) and getattr(self,'bright_mask_pieces',True):
                head,head_offset=_mask_piece(row.neutral[:,:end],row.original[:,:end])
                body,body_offset=_mask_piece(row.neutral[:,start:],row.original[:,start:])
            else:
                head,head_offset=_stable_piece(row.original[:,:end],with_offset=True)
                body,body_offset=_stable_piece(row.original[:,start:],with_offset=True)
            keys=[]
            for role,pair in (('head',head),('body',body)):
                im=pair[0]
                key=(role,hashlib.blake2b(im.tobytes()+str(im.shape).encode(),digest_size=16).digest())
                keys.append(key)
                if ordinary:
                    confirm_keys.add(key)
                cached=self.piece_cache.get(key)
                ttl=4.0 if cached and cached[1]>=.92 else .25
                if cached is None or now-cached[2]>=ttl:
                    tasks.setdefault(key,pair)
                elif role=='head':
                    self.stage['prefix_cache_hits']+=1
            plans.append((row,keys[0],keys[1],via_badge,end,start,body_offset,head_offset))
        values={}
        if tasks:
            confirmed=[i for i,k in enumerate(tasks) if k in confirm_keys]
            if source_keys:
                read=self._candidates(list(tasks.values()),confirmed,
                                      [i for i,k in enumerate(tasks) if k in source_keys])
            else:
                read=self._candidates(list(tasks.values()),confirmed)
            for key,value,regions,span_end,paired in zip(tasks,read,self._candidate_regions,self._candidate_ends,self._candidate_paired):
                values[key]=value
                self.piece_paired[key]=paired or value[1]>=.94
                self.piece_links[key]=regions
                self.piece_ends[key]=span_end
                if key[0]!='full':self.piece_cache[key]=(*value,self.clock())
        result=[];recover=[]
        for index,(row,headkey,bodykey,via_badge,end,start,body_offset,head_offset) in enumerate(plans):
            if headkey and self.piece_ends.get(headkey):end=min(end,self.piece_ends[headkey]+head_offset)
            self.row_meta[row.key]={"name_end":end,"body_start":start,
                "paired_read": (self.piece_paired.get(bodykey,False) and
                                (headkey is None or self.piece_paired.get(headkey,False))),
                "item_ranges":[(x0+start+body_offset,x1+start+body_offset) for _,_,x0,x1 in self.piece_links.get(bodykey,[])]}
            if headkey is None:
                result.append(values[bodykey]);continue
            head=values.get(headkey,self.piece_cache.get(headkey,('',0)))
            body=values.get(bodykey,self.piece_cache.get(bodykey,('',0)))
            nickname=head[0].strip(' :：')
            parsed=parse_chat_line(nickname+' : '+body[0])
            if (parsed is None or head[1]<.70 or body[1]<.65
                    or not re.fullmatch(r'[\w.\-]{2,24}',nickname)
                    or re.match(r'^[\w.\-]{1,24}\s*[:：;；]',body[0])):
                result.append(('',0));recover.append(index)
            else:
                result.append((nickname+' : '+body[0].lstrip(' :：'),min(head[1],body[1])))
                if via_badge:
                    self.split_keys.add(row.key)
                self.stage['delimiter_split_rows']+=1
                self.stage['badge_split_rows']+=int(via_badge)
        if recover:
            full=self._candidates([(rows[i].neutral,rows[i].original) for i in recover],range(len(recover)))
            for i,value,regions,paired in zip(recover,full,self._candidate_regions,self._candidate_paired):
                result[i]=value
                # This retry sees the complete row, so its item coordinates
                # replace the failed body-only split without an extra offset.
                self.row_meta[rows[i].key]['item_ranges']=[(x0,x1) for _,_,x0,x1 in regions]
                self.row_meta[rows[i].key]['paired_read']=paired
        while len(self.piece_cache)>2048:
            expired,_=self.piece_cache.popitem(last=False)
            self.piece_links.pop(expired,None)
            self.piece_ends.pop(expired,None)
            self.piece_paired.pop(expired,None)
        return result

    def detect(self, bgr: np.ndarray, left: int, top: int, scale=1.8) -> list[Line]:
        start = self.clock()
        self.stage = {key:0 for key in ('primary_ms','retry_ms','korean_ms','badge_ms','recognition_batches','recognition_inputs',
                      'source_first_rows','retry_rows','korean_rows','badge_split_rows','delimiter_split_rows','prefix_cache_hits',
                      'critical_retry_rows','numeric_retry_disagreements','term_retry_rejections',
                      'item_ocr_ms','item_ocr_inputs','item_ocr_cache_hits','item_ocr_confirmed','item_ocr_unresolved','item_ocr_batches','item_english_skips',
                      'rec_input_max_width_px','rec_input_max_height_px','rec_input_total_pixels',
                      'korean_input_max_width_px','korean_input_max_height_px','korean_input_total_pixels',
                      'item_input_max_width_px','item_input_max_height_px','item_input_total_pixels',
                      'detector_input_max_width_px','detector_input_max_height_px','detector_input_total_pixels','detector_calls')}
        frame_key=hashlib.blake2b(bgr.tobytes()+str(bgr.shape).encode(),digest_size=16).digest()
        # Identical pixels never contain a *new* visible row. However,
        # periodically revisit the same pixels so a previously weak read can
        # be corrected. No long-lived confidence-only skip.
        if frame_key==self._last_frame and self.clock()-self._last_at < .04:
            dx,dy=left-self._last_origin[0],top-self._last_origin[1]
            self.stats.update(self.stage)
            self.stats.update(cache_hits=self.stats.get('ink_rows',0),new_rows=0,
                              detector_recoveries=0,recognition_errors=0,unchanged_frame=1,
                              ocr_ms=round((self.clock()-start)*1000,2),
                              stage_pre_ms=0.0,stage_ocr_ms=0.0,
                              stage_post_ms=round((self.clock()-start)*1000,2),
                              stage_recovery_detector_ms=0.0,stage_total_ms=round((self.clock()-start)*1000,2),
                              recovery_reasons='',recovery_rows_found=0,
                              recovery_gate_blocked=0,recovery_cache_hit=0,
                              recovery_gate_block_reason='',
                              glyph_hit_rate=0.0,glyph_lines_resolved=0,glyph_lines_fallback=0,
                              glyph_unknown_chars=0,glyph_at_only_skipped=0,
                              ocr_cached_frame=1,
                              input_width_px=int(bgr.shape[1]),input_height_px=int(bgr.shape[0]),
                              input_bytes=int(bgr.nbytes))
            return [replace(line,rect=(line.rect[0]+dx,line.rect[1]+dy,*line.rect[2:])) for line in self._last_output]
        seg_start=self.clock()
        segments, uncertain, border_retry = ink_rows_border_retry(bgr,self.height_hint)
        segments, supplemental = supplement_white_rows(bgr,segments)
        badge_rescues=0
        # Test doubles and older badge helpers may not offer row anchors.
        locate_rows=getattr(self.badges,'locate_rows',None)
        for y,th in (locate_rows(bgr) if locate_rows else ()):
            mid=y+th/2
            if any(abs(mid-(r.rect[1]+r.rect[3]/2))<=max(6,th*.55) for r in segments):
                continue
            a=max(0,y-3);b=min(bgr.shape[0],y+th+3)
            original=bgr[a:b,:,:3].copy()
            neutral=neutral_ink(original)
            # The selection's vertical panel edge is not an initial I in
            # the sender name. Apply the same continuous-edge exclusion as
            # normal row segmentation, to both actual OCR input variants.
            edge=np.mean(neutral[:,:,0]<192,axis=0)>.95
            edge[3:-3]=False
            if edge.any():
                background=row_background(original).astype(np.uint8)
                original[:,edge]=background[:,None,:]
                neutral[:,edge]=255
            key=hashlib.blake2b(neutral.tobytes()+str(neutral.shape).encode(),digest_size=16).digest()
            segments.append(InkRow((0,a,bgr.shape[1],b-a),original,neutral,key))
            badge_rescues+=1
        segments.sort(key=lambda r:r.rect[1])
        self.row_grid.observe(segments)
        if self.grid_rows_enabled:
            # R17 experiment: fixed line bands (off: no measurable gain)
            segments = snap_rows(bgr, segments, self.row_grid)
        if self.glyph_debug.enabled:
            for r in segments:
                self.glyph_debug.capture(r,row_category(r.original,r.rect))
        segmentation_ms=(self.clock()-seg_start)*1000
        if segments:
            observed=float(np.percentile([row.rect[3]-4 for row in segments],30))
            self.height_hint=observed if self.height_hint is None else .85*self.height_hint+.15*observed
        # Pixel background classification precedes text inference; red alone
        # is NOT a reason to discard a player megaphone as a system notice.
        preclass_started=self.clock()
        tones=[detect_band(bgr,row.rect).tone for row in segments]
        if self.glyph_dictionary_enabled:
            for row,tone in zip(segments,tones):
                category=tone if tone!='none' else 'normal'
                self._glyph_colors_by_kind[category]=dominant_ink_color(row.original,row.neutral)
        preclass_ms=(self.clock()-preclass_started)*1000
        now = self.clock()
        values = {}
        missing = OrderedDict()
        hits = 0
        near_hits = 0
        for row in segments:
            entry = self.cache.get(row.key)
            # Identical ink is reusable even after an expensive first read.
            # Expire from inference completion, not from when that read began.
            # Changed characters/prices always have a different pixel key.
            ttl=cache_ttl(entry[0],entry[1],self.stable_reads.get(row.key,0)) if entry else 0.
            if entry and now-entry[2] < ttl:
                values[row.key] = entry[:2]
                self.cache.move_to_end(row.key)
                hits += 1
            elif entry is None and (alias := self._near_match(row, now)) is not None:
                values[row.key] = alias
                hits += 1
                near_hits += 1
            else:
                missing.setdefault(row.key, row)
        scroll_hits = 0
        if self.scroll_reuse and missing:
            for key in self._scroll_reuse(segments, missing, values):
                missing.pop(key, None)
                scroll_hits += 1
            hits += scroll_hits
        rows = list(missing.values())
        # Opt-in glyph gate is intentionally *narrow*: only complete @-only
        # lines may skip OCR. All other rows follow the identical R5 path.
        glyph_at_skipped = set()
        glyph_fallback = 0
        glyph_unknown = 0
        glyph_lookup_chars = 0
        glyph_hit_chars = 0
        if self.glyph_dictionary_enabled:
            retained=[]
            for row in rows:
                profile=row_profile(row,self.glyph_resolution,self.glyph_dpi)
                pieces=separate_glyphs(row.neutral)
                self._glyph_profile=profile
                if not pieces:
                    glyph_fallback+=1
                    retained.append(row)
                    continue
                known=[self.glyph_dictionary.lookup(profile,key) for key,_ in pieces]
                glyph_lookup_chars+=len(known)
                glyph_hit_chars+=sum(v is not None for v in known)
                glyph_unknown+=sum(v is None for v in known)
                if self.glyph_dictionary.resolved_at_only(profile,pieces):
                    glyph_at_skipped.add(row.key)
                else:
                    glyph_fallback+=1
                    retained.append(row)
            rows=retained
        errors = 0
        rec_calls = 0
        pre_ms=(self.clock()-start)*1000
        read_rows_ms=0.0
        if rows:
            read_started=self.clock()
            try:
                primary = self._read_rows(rows)
                rec_calls = self.stage['recognition_batches']
                for row, value in zip(rows, primary):
                    if self.glyph_debug.enabled:
                        self.glyph_debug.observe(row.neutral,value[0])
                    if self.glyph_dictionary_enabled:
                        profile=row_profile(row,self.glyph_resolution,self.glyph_dpi)
                        self.glyph_dictionary.compare_and_train(
                            profile,separate_glyphs(row.neutral),value[0],value[1])
                        self._glyph_profile=profile
                    values[row.key] = value
                    previous=self.cache.get(row.key)
                    self.stable_reads[row.key] = (min(3,self.stable_reads.get(row.key,1)+1)
                                                  if previous and same_read(previous[0],value[0]) else 1)
                    self.cache[row.key] = (*value, self.clock())
                    self.cache.move_to_end(row.key)
                    self.near_index[row.key] = ink_signature(row.neutral)
                    self.near_index.move_to_end(row.key)
                    if self.stable_line_reuse:
                        self.stable_index[row.key] = stable_signature(row.neutral)
                        self.stable_index.move_to_end(row.key)
                    self.canonical[row.key] = row.key
                    self.mask_digest[row.key] = _recovery_mask_digest(row)
            except Exception:
                # Full detector below is deliberately retained as a fallback.
                errors = 1
                uncertain = True
            finally:
                read_rows_ms=(self.clock()-read_started)*1000
        while len(self.cache) > 512:
            oldkey,_=self.cache.popitem(last=False)
            self.split_keys.discard(oldkey)
            self.row_meta.pop(oldkey,None)
            self.stable_reads.pop(oldkey,None)
            self.piece_paired.pop(('full',oldkey),None)
            self.piece_links.pop(('full',oldkey),None)
            self.piece_ends.pop(('full',oldkey),None)
            self.near_index.pop(oldkey,None)
            self.canonical.pop(oldkey,None)
            self.mask_digest.pop(oldkey,None)
        while len(self.near_index) > 256:
            self.near_index.popitem(last=False)
        while len(self.stable_index) > 512:
            self.stable_index.popitem(last=False)
        if self.scroll_reuse:
            self._prev_rows = [(row.rect[1]+row.rect[3]/2, row.key, shift_prep(row.neutral))
                               for row in segments if values.get(row.key, ('', 0.))[0]]
        output = []
        for row in segments:
            text, score = values.get(row.key, ('', 0.0))
            if text and score >= .30:
                x, y, w, h = row.rect
                output.append(Line(text, score, (left+x, top+y, w, h), channel_hint=row.key in self.split_keys,
                                   ink_key=self.canonical.get(row.key,row.key).hex(),
                                   source_meta=self.row_meta.get(row.key,{})))
        parsed = merge_chat_ocr(output)
        from .system_notices import merge_red_notices
        notices = merge_red_notices(output, bgr, left, top)
        # Bright-core border rescue intentionally marks its geometry uncertain.
        # Once EVERY segmented baseline is confidently read and covered by a
        # parsed message/notice, a full-frame detector adds latency without
        # new evidence. An unread/weak row still invokes the recovery gate.
        covered = parsed + notices
        # Bright-glyph rows (white outlined chat): on a real 1080p recording
        # the full-frame detector read numbers WORSE than the clean glyph
        # mask (61 vs 69 of 78 rows with correct digits) and cost ~150ms per
        # frame, so digits alone no longer force it for those rows.
        bright_frame = bool(segments) and all(getattr(row, 'bright', False) for row in segments)
        allow_digits = bright_frame and not self.bright_detector_recovery
        # Any frame where bright-glyph rows were needed (alone or added to a
        # partial row-median result) gets the periodic, add-only probe.
        rescued_frame = bool(border_retry) and any(getattr(row, 'bright', False) for row in segments)
        resolved_border = bool(border_retry and segments and not errors and
            not self.stage['numeric_retry_disagreements'] and all(
                values.get(row.key,('',0))[1] >= .85 and any(
                    r['rect'][1] <= top+row.rect[1]+row.rect[3]/2 <= r['rect'][1]+r['rect'][3]
                    for r in covered) and not re.search(r'[:：]' if allow_digits else r'\d|[:：]',
                                                       (parse_chat_line(values.get(row.key,('',0))[0]) or ('',''))[1])
                for row in segments))
        # Periodically recover unparsed regions, but do not repeatedly OCR a
        # perfectly good banner simply because it is red/grey/yellow.
        # A bright-glyph frame is 'uncertain' by construction. Its rows are
        # already read from clean masks; the detector is only a periodic probe
        # for rows the mask cannot see (coloured text), never every frame.
        bright_probe = bool(rescued_frame and not self.bright_detector_recovery)
        reasons = [reason for reason, hit in (
            ('uncertain', uncertain and not resolved_border and
             (not bright_probe or self.clock()-self._last_bright_probe >= self.bright_probe_interval)),
            ('empty', not (parsed or notices) and not (self.glyph_dictionary_enabled and glyph_at_skipped and len(glyph_at_skipped)==len(segments))),
            ('lowconf', any(v[1] < .65 for v in values.values())),
        ) if hit]
        needs_recovery = bool(reasons)
        if self.glyph_dictionary_enabled and glyph_at_skipped and len(glyph_at_skipped)==len(segments) and not uncertain:
            needs_recovery = False
            reasons=[]
        recovery = 0
        recovery_ms = 0.0
        rows_found = []
        used_cache = False
        gate_block_reason = ''
        # Critical: a BGR frame hash changes with the transparent game
        # background even when the foreground text is unchanged.
        recovery_key = ink_recovery_key(bgr, segments, {
            row.key: self.mask_digest.get(self.canonical.get(row.key)) for row in segments})
        entry = self.recovery_gate.lookup(recovery_key) if needs_recovery else None
        has_ink = bool(segments)
        def keep_read_rows(found):
            # On bright frames the detector may ADD rows the glyph mask missed
            # or repair weak ones, but never overwrite a confidently read row
            # (it read digits worse than the mask on real 1080p footage).
            if not bright_probe:
                return found
            strong = [line for line in output if line.confidence >= self.bright_keep_confidence]
            return [line for line in found if not any(
                s.rect[1] <= line.rect[1]+line.rect[3]/2 <= s.rect[1]+s.rect[3] for s in strong)]
        if needs_recovery and has_ink and entry and entry['rows']:
            # Cache stores local coordinates; adjust for chat window movement.
            recovered = [Line(t, c, (left+x, top+y, w, h))
                         for t, c, (x, y, w, h) in entry['rows']]
            output = merge_recovery_lines(output,keep_read_rows(recovered))
            used_cache = True
        elif needs_recovery:
            attempt_now = self.clock()   # after primary OCR, not a stale timestamp
            gate_block_reason = self.recovery_gate.block_reason(
                recovery_key, attempt_now, has_ink)
            if not gate_block_reason:
                recovery_start = self.clock()
                try:
                    fallback = self.recognizer.detect(bgr, left, top, min(scale, self.recovery_scale_cap))
                    detect_inputs=getattr(self.recognizer,'last_detect_inputs',None)
                    if detect_inputs:
                        self.stage['detector_calls']=len(detect_inputs)
                        self.stage['detector_input_max_width_px']=max(x for x,y in detect_inputs)
                        self.stage['detector_input_max_height_px']=max(y for x,y in detect_inputs)
                        self.stage['detector_input_total_pixels']=sum(x*y for x,y in detect_inputs)
                    else:
                        self.stage['detector_calls']=1  # synthetic/mock fallback
                        self.stage['detector_input_max_width_px']=round(bgr.shape[1]*scale)
                        self.stage['detector_input_max_height_px']=round(bgr.shape[0]*scale)
                        self.stage['detector_input_total_pixels']=(round(bgr.shape[1]*scale)*round(bgr.shape[0]*scale))
                    if bright_probe:
                        self._last_bright_probe = self.clock()
                    if fallback:
                        # Ambiguous segmentation is replaced, never concatenated
                        # with a recovered copy of the same chat line.
                        output = merge_recovery_lines(output,keep_read_rows(fallback))
                        rows_found = [(line.text, line.confidence,
                            (line.rect[0]-left,line.rect[1]-top,*line.rect[2:]))
                            for line in fallback]
                except Exception:
                    errors = 1
                    # Recovery is optional; keep the primary result on failure.
                finally:
                    finished = self.clock()
                    recovery_ms = max(0.,(finished-recovery_start)*1000)
                    # Failed detector calls count too, so empty/@@@@ frames
                    # cannot monopolize the OCR worker.
                    self.recovery_gate.record(recovery_key, rows_found,
                                              recovery_start, finished, has_ink)
                    recovery = 1
        self.totals['frames']+=1
        self.totals['rows']+=len(rows)
        self.totals['recognition_inputs']+=self.stage['recognition_inputs']
        self.totals['retry_rows']+=self.stage['retry_rows']
        self.totals['korean_rows']+=self.stage['korean_rows']
        self.totals['recoveries']+=recovery
        total=(self.clock()-start)*1000
        model_wall_ms=read_rows_ms+recovery_ms
        post_ms=max(0.,total-pre_ms-model_wall_ms)
        if rows or recovery:
            self.book.observe('ocr_active',total)
        for label,value in [('ocr',total),('segmentation',segmentation_ms),('primary',self.stage['primary_ms']),
                            ('retry',self.stage['retry_ms']),('korean',self.stage['korean_ms']),('recovery',recovery_ms),
                            ('badge',self.stage['badge_ms']),('preclassification',preclass_ms)]:
            if value>0 or label in ('ocr','segmentation','preclassification'):
                self.book.observe(label,value)
        self.stats = {**self.book.snapshot(), **self.stage,
                      'stage_pre_ms':round(pre_ms,2),'stage_ocr_ms':round(model_wall_ms,2),
                      'stage_post_ms':round(post_ms,2),'stage_total_ms':round(total,2),
                      'stage_recovery_detector_ms':round(recovery_ms,2),
                      'ocr_cached_frame':0,
                      'input_width_px':int(bgr.shape[1]),'input_height_px':int(bgr.shape[0]),
                      'input_bytes':int(bgr.nbytes),
                      'segmentation_ms':round(segmentation_ms,2),'recovery_ms':round(recovery_ms,2),
                      'retry_input_pct':round(100*self.totals['retry_rows']/max(1,self.totals['recognition_inputs']),1),
                      'korean_input_pct':round(100*self.totals['korean_rows']/max(1,self.totals['recognition_inputs']),1),
                      'recovery_frame_pct':round(100*self.totals['recoveries']/max(1,self.totals['frames']),1),
                      'recovery_reasons': '+'.join(reasons),
                      'recovery_rows_found': len(rows_found),
                      'recovery_gate_blocked': int(bool(needs_recovery and not recovery and not used_cache)),
                      'recovery_cache_hit': int(used_cache),
                      'recovery_gate_block_reason': gate_block_reason,
                      'preclassified_megaphone_rows':sum(tone!='none' for tone in tones),
                      'ocr_ms': round((self.clock()-start)*1000, 1),
                      'ink_rows': len(segments), 'supplemental_white_rows': supplemental, 'badge_rescue_rows':badge_rescues, 'border_retry_used': border_retry, 'cache_hits': hits,
                      'near_cache_hits': near_hits, 'scroll_reuse_hits': scroll_hits,
                      'border_rows_confirmed':int(resolved_border),
                      'new_rows': len(rows), 'recognition_batches': rec_calls,
                      'detector_recoveries': recovery, 'recognition_errors': errors}
        if self.glyph_debug.enabled:self.stats.update(self.glyph_debug.stats())
        if self.glyph_dictionary_enabled:
            self.stats.update(self.glyph_dictionary.stats(self._glyph_profile))
            self.stats.update(glyph_profile_resolution=self._glyph_profile[0] if self._glyph_profile else 'unknown',
                              glyph_profile_dpi=self._glyph_profile[1] if self._glyph_profile else 'unknown',
                              glyph_profile_row_height=self._glyph_profile[2] if self._glyph_profile else 0,
                              glyph_profile_ink_color=self._glyph_profile[3] if self._glyph_profile else 'unknown',
                              glyph_profile_colors_by_kind=dict(self._glyph_colors_by_kind),
                              glyph_lines_resolved=len(glyph_at_skipped),
                              glyph_hit_rate=round(glyph_hit_chars/max(1,glyph_lookup_chars),4),
                              glyph_lines_fallback=glyph_fallback,
                              glyph_unknown_chars=glyph_unknown,
                              glyph_at_only_skipped=len(glyph_at_skipped))
        else:
            self.stats.update(glyph_hit_rate=0.0,glyph_lines_resolved=0,
                              glyph_lines_fallback=0,glyph_unknown_chars=0,
                              glyph_at_only_skipped=0,glyph_dict_size=0,
                              glyph_shadow_compared=0,glyph_shadow_mismatch=0,
                              glyph_shadow_pairs=[],glyph_shadow_mismatch_rate=0.0)
        self._last_frame=frame_key
        self._last_output=output
        self._last_origin=(left,top)
        self._last_at=self.clock()
        return output
