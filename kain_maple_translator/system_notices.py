"""Identify red system notices for exclusion, preserving player megaphones."""
from __future__ import annotations
import re

from .vision import red_announcement_regions
from .megaphone import detect_band

_OBTAINED = re.compile(
    r'^(?P<player>[\w.\-]{2,24})\s+(?:has\s+)?obtained\s+'
    r'\[(?P<item>[^]\n]{2,100})\]\s+from\s+(?:the\s+)?'
    r'(?P<source>[^!\n]{2,120})'
    r'(?P<congrats>!\s*Con\s*grats[!.]?|!|\.)?$', re.I)


def obtained_notice(text: str):
    return _OBTAINED.fullmatch(re.sub(r'\s+', ' ', str(text)).strip())


def merge_red_notices(lines, image, left: int, top: int):
    out = []
    for x, y, w, h in red_announcement_regions(image):
        inside = []
        for line in lines:
            lx, ly, lw, lh = line.rect
            overlap = max(0, min(ly+lh, top+y+h)-max(ly, top+y))
            if overlap >= lh*.55 and line.confidence >= .43:
                inside.append(line)
        inside.sort(key=lambda line: (line.rect[1], line.rect[0]))
        text = ' '.join(line.text.strip() for line in inside)
        if not obtained_notice(text):
            continue
        band = detect_band(image, (x, y, w, h))
        out.append({'nickname': '시스템', 'body': text,
                    'rect': (left+x, top+y, w, h),
                    'confidence': min(line.confidence for line in inside),
                    'kind': 'system', 'prefix': '[공지]', 'tone': 'red',
                    'band_color': band.background or '#a74530'})
    return out
