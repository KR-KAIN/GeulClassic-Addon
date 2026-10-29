"""Pre-Big Bang MapleStory UI drawn exactly the way the game draws it.

The game renders its UI at 1366x768 with Gulim 12px (no antialiasing) and
sprite fonts, then stretches the whole frame bilinearly to the window size
(1920x1080 here, x1.4056). Every piece in resources/classic_ui was recovered
from that stretched picture back to its native pixels, so composing at native
size and stretching the same way gives the same pixels as the game itself.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap

NATIVE_W, NATIVE_H = 1366, 768
# Game window 1920x1080 -> 1366x768 native UI. Updated from the real window.
SCALE = [1920 / 1366, 1080 / 768]


def set_game_size(width: int, height: int):
    """Match the stretch of the game window that is actually open."""
    if width > 0 and height > 0:
        SCALE[0] = width / NATIVE_W
        SCALE[1] = height / NATIVE_H


def _root() -> Path:
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return base / 'resources' / 'classic_ui'


@lru_cache(maxsize=None)
def piece(name: str) -> np.ndarray:
    """A native piece as BGRA."""
    # cv2.imread cannot open non-ASCII paths on Windows ("글클메 애드온").
    path = _root() / f'{name}.png'
    img = None
    if path.exists():
        img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(name)
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return img


@lru_cache(maxsize=None)
def digit(d: str) -> np.ndarray | None:
    """The game's quickslot count digit (ItemNo sprite), BGRA."""
    path = _root().parent / 'hunt' / 'digits' / f'{d}.png'
    if not path.exists():
        return None
    img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)
    if img is not None and img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return img


@lru_cache(maxsize=1)
def _minus_sprite() -> np.ndarray:
    """A minus sign in the quickslot digit style (white bar, dark rim)."""
    g = np.zeros((11, 6, 4), np.uint8)
    g[4:7, 0:6] = (20, 20, 20, 255)
    g[5, 1:5] = (255, 255, 255, 255)
    return g


@lru_cache(maxsize=1)
def _atlas() -> dict:
    return json.loads((_root() / 'classic_ui.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def _button_caps() -> dict:
    """Width of each game button sprite's drawn ends (scripts/fetch_button_ui.py)."""
    try:
        return json.loads((_root() / 'button' / 'caps.json').read_text(encoding='utf-8'))
    except Exception:
        return {}


# ClassicButton kinds -> the game's button sprites (resources/classic_ui/button)
BUTTON_KINDS = {'lime': 'lime', 'orange': 'orange', 'pink': 'pink', 'blue': 'blue',
                'confirm': 'blue', 'cancel': 'cancel', 'gray': 'lime'}


@lru_cache(maxsize=1)
def _shade_kernel() -> np.ndarray:
    k = np.array(json.loads((_root() / 'pill_shade_kernel.json').read_text())['kernel'], np.float32)
    return np.maximum(k, 0)


# 5x5 title glyphs (CHARACTER STAT font). Letters seen in the game are
# loaded from the atlas; the rest follow the same 5x5 strokes.
_TITLE_EXTRA = {
    'X': ['#...#', '.#.#.', '..#..', '.#.#.', '#...#'],
    'P': ['####.', '#...#', '####.', '#....', '#....'],
    'M': ['#...#', '##.##', '#.#.#', '#...#', '#...#'],
    'I': ['###', '.#.', '.#.', '.#.', '###'],
    'N': ['#...#', '##..#', '#.#.#', '#..##', '#...#'],
    'O': ['.###.', '#...#', '#...#', '#...#', '.###.'],
    'U': ['#...#', '#...#', '#...#', '#...#', '.###.'],
    'L': ['#....', '#....', '#....', '#....', '#####'],
    'G': ['.###.', '#....', '#..##', '#...#', '.###.'],
    'D': ['####.', '#...#', '#...#', '#...#', '####.'],
    'K': ['#...#', '#..#.', '###..', '#..#.', '#...#'],
    'B': ['####.', '#...#', '####.', '#...#', '####.'],
    'W': ['#...#', '#...#', '#.#.#', '##.##', '#...#'],
    'Y': ['#...#', '.#.#.', '..#..', '..#..', '..#..'],
    'F': ['#####', '#....', '####.', '#....', '#....'],
    'V': ['#...#', '#...#', '#...#', '.#.#.', '..#..'],
    '>': ['#..', '.#.', '..#', '.#.', '#..'],
}
# Pill font letters that never appear on the stat window, in its 7-row style.
_PILL_EXTRA = {
    'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '##.##', '#...#'],
    'Q': ['.##.', '#..#', '#..#', '#..#', '#.##', '#..#', '.###'],
    'Z': ['####', '...#', '..#.', '.#..', '#...', '#...', '####'],
    '0': ['.##.', '#..#', '#..#', '#..#', '#..#', '#..#', '.##.'],
    '1': ['.#.', '##.', '.#.', '.#.', '.#.', '.#.', '###'],
    '/': ['...#', '...#', '..#.', '.#..', '.#..', '#...', '#...'],
}


@lru_cache(maxsize=None)
def _title_glyph(ch: str) -> np.ndarray:
    if ch in _TITLE_EXTRA:
        return np.array([[c == '#' for c in row] for row in _TITLE_EXTRA[ch]], bool)
    m = np.array(_atlas()['title'][ch]['mask'], bool)
    ys = np.nonzero(m.any(axis=1))[0]
    return m[ys.min():ys.max() + 1]


@lru_cache(maxsize=None)
def _pill_glyph(ch: str) -> np.ndarray:
    """White mask of one pill-font letter (7 rows)."""
    if ch in _PILL_EXTRA:
        return np.array([[c == '#' for c in row] for row in _PILL_EXTRA[ch]], bool)
    g = _atlas()['pill'].get(ch)
    if g is None:
        return np.zeros((7, 3), bool)
    # Every letter sits on the same 7 rows (5..11) of the 16px pill, so
    # a period stays on the baseline.
    return np.array(g['white'], bool)[5:12, :g['w']]


@lru_cache(maxsize=512)
def _gulim(text: str, bold: bool = False, px: int = 12) -> np.ndarray:
    """Gulim 12px without antialiasing, as the game prints names and values."""
    font = QFont('Gulim')
    font.setPixelSize(px)
    font.setBold(bold)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    fm = QFontMetrics(font)
    w = max(1, fm.horizontalAdvance(text) + 2)
    # Baseline at row 12 of a 16-row mask: Hangul in Gulim rises above the
    # Latin cap height, so keep two spare rows on top (Canvas.text offsets).
    h = max(16, px + 4)
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(0, max(12, px), text)
    p.end()
    a = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w, 3]
    m = a > 0
    xs = np.nonzero(m.any(axis=0))[0]
    return m[:, :xs.max() + 1] if len(xs) else m[:, :1]


def text_width(text: str, bold: bool = False, px: int = 12) -> int:
    return _gulim(text, bold, px).shape[1] if text else 0


def fit_text(text: str, width: int, bold: bool = False, px: int = 12) -> str:
    if text_width(text, bold, px) <= width:
        return text
    while text and text_width(text + '…', bold, px) > width:
        text = text[:-1]
    return text + '…'


def wrap_text(text: str, width: int, lines: int) -> list[str]:
    out, cur = [], ''
    for ch in text:
        if text_width(cur + ch) > width:
            out.append(cur.rstrip())
            cur = ch.lstrip()
            if len(out) == lines - 1:
                rest = text[len(''.join(out)) + 0:]
                break
        else:
            cur += ch
    if len(out) < lines:
        out.append(cur)
    if len(out) == lines and ''.join(out).replace(' ', '') != text.replace(' ', ''):
        out[-1] = fit_text(text[len(''.join(out[:-1])):].strip(), width)
    return out[:lines]


class Canvas:
    """Native-resolution BGRA canvas."""

    def __init__(self, w: int, h: int):
        self.w, self.h = int(w), int(h)
        self.px = np.zeros((self.h, self.w, 4), np.uint8)

    # ---- raw pixels ----
    def blit(self, img: np.ndarray, x: int, y: int, alpha: float = 1.0):
        if img.shape[2] == 3:
            img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
        h, w = img.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        src = img[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
        dst = self.px[y0:y1, x0:x1].astype(np.float32)
        a = src[:, :, 3:4] / 255.0 * alpha
        out = src * a + dst * (1 - a)
        out[:, :, 3:4] = np.maximum(dst[:, :, 3:4], a * 255)
        self.px[y0:y1, x0:x1] = out.astype(np.uint8)

    def fill(self, x, y, w, h, bgr):
        self.px[y:y + h, x:x + w] = (*bgr, 255)

    def hslice(self, img: np.ndarray, x: int, y: int, w: int, left: int, right: int):
        """Horizontal 3-slice: fixed ends, middle columns stretched."""
        ih, iw = img.shape[:2]
        mid = img[:, left:iw - right]
        body = cv2.resize(mid, (max(1, w - left - right), ih), interpolation=cv2.INTER_NEAREST)
        self.blit(np.hstack([img[:, :left], body, img[:, iw - right:]]), x, y)

    def nine(self, img: np.ndarray, x, y, w, h, l, t, r, b):
        ih, iw = img.shape[:2]
        rows = [img[:t], img[t:ih - b], img[ih - b:]]
        hs = [t, max(1, h - t - b), b]
        parts = []
        for part, hh in zip(rows, hs):
            if part.shape[0] != hh:
                part = cv2.resize(part, (iw, hh), interpolation=cv2.INTER_NEAREST)
            parts.append(part)
        tall = np.vstack(parts)
        self.hslice(tall, x, y, w, l, r)

    # ---- stat window frame ----
    def frame(self, strip: bool = True):
        """Stat window frame; strip=False drops the ABILITY POINT strip."""
        f = piece('frame')
        top = f[:30]
        bottom = f[245:] if strip else f[275:]
        body = f[100:101]
        mid_h = self.h - top.shape[0] - bottom.shape[0]
        col = np.vstack([top, np.repeat(body, max(0, mid_h), axis=0), bottom])
        self.hslice(col, 0, 0, self.w, 6, 6)

    # ---- text ----
    def text(self, x, y, text, bgr=(0, 0, 0), bold=False, outline=None, px=12) -> int:
        """Gulim (12px by default); y is the top of the 13px line."""
        if not text:
            return 0
        m = _gulim(text, bold, px)
        y -= 2  # the mask has two spare rows above the 13px line
        if outline is not None:
            k = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            pad = np.zeros((m.shape[0] + 2, m.shape[1] + 2), bool)
            pad[1:-1, 1:-1] = m
            k = cv2.dilate(pad.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            self._mask(k & ~pad, x - 1, y - 1, outline)
        self._mask(m, x, y, bgr)
        return m.shape[1]

    def _mask(self, m, x, y, bgr):
        h, w = m.shape
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        sub = m[y0 - y:y1 - y, x0 - x:x1 - x]
        region = self.px[y0:y1, x0:x1]
        region[sub] = (*bgr, 255)

    def title(self, x, y, text, bgr=(0, 0, 0)) -> int:
        cx = x
        for ch in text.upper():
            if ch == ' ':
                cx += 3
                continue
            g = _title_glyph(ch)
            self._mask(g, cx, y, bgr)
            cx += g.shape[1] + 1
        return cx - x - 1

    def _white_text(self, m, x, y, strong=False, face=255):
        """Paint a white mask with the game's soft shade; strong adds a dark
        1px rim (like the minimap's map names) so light buttons stay readable.
        face < 255 greys the letters (a disabled button's label)."""
        k = _shade_kernel()
        pad = 2
        big = np.zeros((m.shape[0] + 2 * pad, m.shape[1] + 2 * pad), np.float32)
        big[pad:-pad, pad:-pad] = m
        dark = cv2.filter2D(big, -1, k[::-1, ::-1], borderType=cv2.BORDER_CONSTANT)
        dark = np.clip(dark, 0, 0.6)
        if strong:
            # strong=True: the dark rim; a number < 1 is a lighter rim in the
            # colour underneath (the game's ADD letters on lime)
            rim = cv2.dilate(big, np.ones((3, 3), np.uint8)) - big
            dark = np.maximum(dark, rim * (0.62 if strong is True else float(strong)))
        x0, y0 = x - pad, y - pad
        h, w = big.shape
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(self.w, x0 + w), min(self.h, y0 + h)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        reg = self.px[sy0:sy1, sx0:sx1, :3].astype(np.float32)
        reg *= (1 - dark[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0][:, :, None])
        reg[big[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] > 0] = face
        self.px[sy0:sy1, sx0:sx1, :3] = reg.astype(np.uint8)

    def pill_text(self, x, y, text, max_w=None, strong=False, face=255) -> int:
        """White sprite letters with the game's soft shade around them."""
        glyphs, widths = [], 0
        for ch in text.upper():
            if ch == ' ':
                glyphs.append(None)
                widths += 3
            else:
                g = _pill_glyph(ch)
                glyphs.append(g)
                widths += g.shape[1] + 1
        widths = max(0, widths - 1)
        m = np.zeros((7, widths + 1), bool)
        cx = 0
        for g in glyphs:
            if g is None:
                cx += 3
                continue
            m[:g.shape[0], cx:cx + g.shape[1]] = g
            cx += g.shape[1] + 1
        self._white_text(m, x, y, strong, face)
        return widths

    # ---- widgets ----
    def pill(self, kind, x, y, w, h, label):
        img = piece(f'pill_{kind}_clean')
        self.nine(img, x, y, w, h, 3, 4, 10, 4)
        # Letters sit on rows 5..11 of a 16px pill; tall pills (JOB) keep
        # the label on the top line. Lime is light, so give it a dark rim.
        ty = y + 5 if h <= 16 or h > 26 else y + (h - 7) // 2   # short rows: centred
        self.pill_text(x + 4, ty, label, strong=(kind == 'lime'))

    def key_pill(self, kind, x, y, w, h, key_label):
        """A stat-window pill whose label is the key name exactly as printed
        on the game's quickslot keys (Ctrl / Del / End / Pdn)."""
        self.nine(piece(f'pill_{kind}_clean'), x, y, w, h, 3, 4, 10, 4)
        # the crop's first column and last row are the label box's corner
        lab = piece(f'key_label_{key_label}')[:-1, 1:, :3].astype(np.float32).mean(axis=2)
        # Letters are a flat grey (~203); their white outline (255), the label
        # box edge (~212) and the cap (249) are left out.
        m = (lab >= 196) & (lab <= 207)
        ys, xs = np.nonzero(m)
        if len(ys):
            m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            self._white_text(m, x + max(3, (w - 4 - m.shape[1]) // 2), y + (h - m.shape[0]) // 2, strong=True)

    def count_digits(self, x, y, text, scale=1.0, tint=None) -> int:
        """Stack count in the game's quickslot digits (white with dark rim).
        scale < 1 shrinks them; tint recolours the white face (e.g. used)."""
        cx = x
        for ch in text:
            if ch == '-':
                g = _minus_sprite()
            else:
                g = digit(ch)
            if g is None:
                continue
            if scale != 1.0:
                g = cv2.resize(g, (max(1, round(g.shape[1] * scale)), max(1, round(g.shape[0] * scale))),
                               interpolation=cv2.INTER_AREA)
            if tint is not None:
                g = g.copy()
                face = g[:, :, :3].astype(np.float32).mean(axis=2) > 140
                g[face, :3] = tint
            self.blit(g, cx, y)
            cx += g.shape[1] - 1
        return cx - x

    def key_slot(self, x, y, key_label, icon=None, count=None):
        """One quickslot key exactly as the game draws it: cap, key name,
        item icon and the white-outlined stack count."""
        cap = piece('key_cap')
        self.blit(cap, x, y)
        self.blit(piece(f'key_label_{key_label}'), x + 3, y + 4)
        if icon is not None and not icon.isNull():
            # Like the game: the key name stays readable above the item,
            # which sits low and may hang past the cap's bottom edge.
            self.icon(icon, x + 1 + (32 - icon.width()) // 2, y + 8)
        if count and count.isdigit():
            cx = x + 2
            for ch in count:
                g = digit(ch)
                if g is None:
                    continue
                self.blit(g, cx, y + cap.shape[0] - g.shape[0] - 3)
                cx += g.shape[1] - 1
        return cap.shape[1], cap.shape[0]

    def cell(self, x, y, w, h):
        self.nine(piece('cell'), x, y, w, h, 2, 2, 2, 2)

    def button(self, kind, x, y, w, h, label, state='normal'):
        """kind: lime | orange.  state: normal | hover | pressed | disabled."""
        self.ui_button(x, y, w, h, label, state, kind)

    def close_button(self, x, y, state='normal'):
        """The game's blue X (Basic.img/BtClose), 12x12."""
        self.blit(piece(f'button/close_{state}'), x, y)

    def big_text(self, x, y, h, text, bgr=(0, 0, 0), px=16, bold=True) -> int:
        """Larger value text, vertically centred on its ink inside a row of height h."""
        if not text:
            return 0
        m = _gulim(text, bold, px)
        rows = np.nonzero(m.any(axis=1))[0]
        if not len(rows):
            return 0
        m2 = m[rows[0]:rows[-1] + 1]
        self._mask(m2, x, y + (h - m2.shape[0]) // 2, bgr)
        return m.shape[1]

    def icon_fit(self, qpix: QPixmap | None, x, y, size):
        """Item icon shrunk to fit a size x size box (small potion slots)."""
        if qpix is None or qpix.isNull():
            return
        img = qpix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()].copy()
        ys, xs = np.nonzero(a[:, :, 3] > 0)
        if len(ys):
            a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        k = size / max(a.shape[:2])
        if k < 1:
            a = cv2.resize(a, (max(1, round(a.shape[1] * k)), max(1, round(a.shape[0] * k))), interpolation=cv2.INTER_AREA)
        self.blit(a, x + (size - a.shape[1]) // 2, y + (size - a.shape[0]) // 2)

    def icon(self, qpix: QPixmap | None, x, y):
        if qpix is None or qpix.isNull():
            return
        img = qpix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
        self.blit(a[:, :img.width()].copy(), x, y)

    def hud(self, x, y, w, h):
        """The dark status-bar panel of the bottom HUD."""
        img = piece('hud_panel')
        ih = img.shape[0]
        # rows 0..4 are the silver top edge, the last 3 the bottom edge;
        # only the charcoal gradient between them stretches.
        mid = cv2.resize(img[5:ih - 3], (img.shape[1], max(1, h - 8)), interpolation=cv2.INTER_LINEAR)
        self.hslice(np.vstack([img[:5], mid, img[ih - 3:]]), x, y, w, 3, 3)

    def plain(self):
        """The stat window without its title band: frame, light body, edge."""
        f = piece('frame')
        top = f[:4]
        bottom = f[275:]
        body = f[100:101]
        mid_h = self.h - top.shape[0] - bottom.shape[0]
        col = np.vstack([top, np.repeat(body, max(0, mid_h), axis=0), bottom])
        self.hslice(col, 0, 0, self.w, 6, 6)

    def shaded_text(self, x, y, text, strong=True, px=12, face=255) -> int:
        """White Gulim with the pill letters' shade and a dark rim (button labels)."""
        m = _gulim(text, False, px)
        self._white_text(m, x, y - 2, strong, face)
        return m.shape[1]

    def ui_button(self, x, y, w, h, label, state='normal', kind='blue', px=12):
        """A game button from the game's own sprites (R19, MCW data):
        lime = ADD/DELETE, orange = MY STATUS, pink = WHISPER/TALK (buddy
        list), blue = CONFIRM, cancel = CANCEL (options), grey when disabled,
        and 'close' = the blue X. The sprite's label was removed by
        scripts/fetch_button_ui.py; ours is drawn in the same white letters."""
        state = state if state in ('normal', 'hover', 'pressed', 'disabled') else 'normal'
        tmp = Canvas(w, h)
        if kind == 'close':
            sprite = piece(f'button/close_{state}')
            tmp.blit(sprite, (w - sprite.shape[1]) // 2, (h - sprite.shape[0]) // 2)
            self.blit(tmp.px, x, y)
            return
        name = f'{BUTTON_KINDS.get(kind, "blue")}_{state}'
        if kind == 'gray':
            name = 'lime_disabled'
        img = piece(f'button/{name}')
        cap = _button_caps().get(name, 3)
        tmp.nine(img, 0, 0, w, h, cap, 3, cap, 3)
        off = 1 if state == 'pressed' else 0
        face = 214 if (state == 'disabled' or kind == 'gray') else 255
        # The game's labels are white with a soft shade in the button's own
        # darker colour (ADD, CONFIRM), never a black rim; on the light lime
        # the letters get a thin darker-lime edge like ADD / DELETE.
        rim = 0.34 if BUTTON_KINDS.get(kind) == 'lime' and kind != 'gray' and state != 'disabled' else False
        pill_ok = label and all(c == ' ' or c in _PILL_EXTRA or c in _atlas()['pill'] for c in label)
        if pill_ok:
            tw = sum(_pill_glyph(c).shape[1] + 1 if c != ' ' else 3 for c in label) - 1
            tmp.pill_text((w - tw) // 2 + off, (h - 7) // 2 + off, label, strong=rim, face=face)
        else:
            if text_width(label, False, px) > w - 4:
                label = fit_text(label, max(6, w - 4), False, px)
            tw = text_width(label, False, px)
            # Centre the actual ink (Hangul is taller than Latin) so short
            # buttons such as the 12px title-band one never clip it.
            rows = np.nonzero(_gulim(label, False, px).any(axis=1))[0]
            r0, r1 = (int(rows[0]), int(rows[-1])) if len(rows) else (2, 12)
            ty = (h - (r1 - r0 + 1) + 1) // 2 - r0 + 2
            tmp.shaded_text((w - tw) // 2 + off, ty + off, label, strong=rim, px=px, face=face)
        self.blit(tmp.px, x, y)

    def navy(self, x, y, w, h, label, state='normal', kind='navy'):
        """A HUD text button: the navy chat tab, lime when on, orange accent."""
        if kind != 'navy':
            self.ui_button(x, y, w, h, label, state, kind)    # the game's own lime / orange
            return
        base = 'navy_btn'
        tmp = Canvas(w, h)
        tmp.nine(piece(base), 0, 0, w, h, 4, 4, 4, 4)
        if state == 'hover':
            tmp.px[:, :, :3] = np.clip(tmp.px[:, :, :3].astype(np.int16) + 24, 0, 255).astype(np.uint8)
        elif state == 'disabled':
            gray = tmp.px[:, :, :3].mean(axis=2, keepdims=True)
            tmp.px[:, :, :3] = (gray * 0.5 + 70).astype(np.uint8)
        label = fit_text(label, max(6, w - 4))
        off = 1 if state == 'pressed' else 0
        tw = text_width(label)
        tmp.text((w - tw) // 2 + off, (h - 12) // 2 + off, label, (255, 255, 255))
        self.blit(tmp.px, x, y)

    # ---- output ----
    def pixmap(self, size=None, scale=None) -> QPixmap:
        """Stretch like the game; size=(w, h) forces an exact widget size,
        scale=(sx, sy) a different stretch (the compact EXP meter)."""
        sx, sy = scale or SCALE
        w, h = size or (round(self.w * sx), round(self.h * sy))
        up = cv2.resize(self.px, (max(1, w), max(1, h)), interpolation=cv2.INTER_LINEAR)
        up = np.ascontiguousarray(up)
        img = QImage(up.data, up.shape[1], up.shape[0], up.shape[1] * 4, QImage.Format.Format_ARGB32).copy()
        return QPixmap.fromImage(img)


def light_palette():
    """Stat-window colours for every unstyled Qt surface (dialogs, pages,
    check boxes, spin boxes, menus), regardless of Windows dark mode."""
    from PySide6.QtGui import QPalette
    pal = QPalette()
    body, text, white = QColor('#f5f6f7'), QColor('#2e3a46'), QColor('#ffffff')
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        pal.setColor(group, QPalette.ColorRole.Window, body)
        pal.setColor(group, QPalette.ColorRole.WindowText, text)
        pal.setColor(group, QPalette.ColorRole.Base, white)
        pal.setColor(group, QPalette.ColorRole.AlternateBase, QColor('#e4e2d8'))
        pal.setColor(group, QPalette.ColorRole.Text, text)
        pal.setColor(group, QPalette.ColorRole.Button, QColor('#e4e2d8'))
        pal.setColor(group, QPalette.ColorRole.ButtonText, text)
        pal.setColor(group, QPalette.ColorRole.ToolTipBase, white)
        pal.setColor(group, QPalette.ColorRole.ToolTipText, text)
        pal.setColor(group, QPalette.ColorRole.Highlight, QColor('#5a88b6'))
        pal.setColor(group, QPalette.ColorRole.HighlightedText, white)
        pal.setColor(group, QPalette.ColorRole.PlaceholderText, QColor('#8a939c'))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor('#9aa3ab'))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor('#9aa3ab'))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor('#9aa3ab'))
    return pal


def native_size(w: int, h: int) -> tuple[int, int]:
    return max(1, round(w / SCALE[0])), max(1, round(h / SCALE[1]))


from PySide6.QtWidgets import QPushButton, QLabel, QComboBox  # noqa: E402


class ClassicButton(QPushButton):
    """QPushButton drawn as a HUD button from the game's own pieces.

    Behaviour (clicked/toggled/checkable/enabled) is the normal Qt button;
    only painting changes. Set kind with setProperty('classic', 'orange').
    """

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(round((text_width(self.text()) + 8) * SCALE[0]), round(18 * SCALE[1]))

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(round((text_width(self.text()) + 6) * SCALE[0]), round(14 * SCALE[1]))

    def paintEvent(self, event):
        nw, nh = native_size(self.width(), self.height())
        kind = self.property('classic') or 'blue'
        if self.isCheckable() and self.isChecked():
            kind = 'lime'
        state = ('disabled' if not self.isEnabled() else 'pressed' if self.isDown()
                 else 'hover' if self.underMouse() else 'normal')
        c = Canvas(nw, nh)
        c.ui_button(0, 0, nw, nh, self.text(), state, kind)
        p = QPainter(self)
        p.drawPixmap(0, 0, c.pixmap((self.width(), self.height())))
        p.end()


class ClassicCombo(QComboBox):
    """The current choice shown as a HUD button; the list stays a Qt popup."""

    def paintEvent(self, event):
        nw, nh = native_size(self.width(), self.height())
        c = Canvas(nw, nh)
        c.cell(0, 0, nw, nh)
        label = fit_text(self.currentText(), max(6, nw - 16))
        c.text(4, (nh - 12) // 2 + 1, label, (0, 0, 0))
        c.text(nw - 11, (nh - 12) // 2 + 1, '▼', (102, 102, 153))
        p = QPainter(self)
        p.drawPixmap(0, 0, c.pixmap((self.width(), self.height())))
        p.end()


class ClassicText(QLabel):
    """White Gulim 12px status text, stretched like the game's HUD names."""

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(20, round(13 * SCALE[1]))

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(round((text_width(self.text()) + 4) * SCALE[0]), round(13 * SCALE[1]))

    def paintEvent(self, event):
        nw, nh = native_size(self.width(), self.height())
        nh = max(nh, 15)  # never clip the 12px line (Hangul rises 2px)
        c = Canvas(nw, nh)
        colour = (102, 102, 153) if self.objectName() in ('subtle', 'eyebrow') else (0, 0, 0)
        if self.objectName() == 'strip':
            # 11px leaves air above and below inside the 18-row strip
            px = 11
            label = fit_text(self.text(), nw - 8, False, px)
            y = nh - 19
            win = self.window()
            strip_px = getattr(self, 'strip_px', None)
            if strip_px and win is not None and self.height() > 0:
                # centre the ink between the strip's two dark lines, wherever
                # the label sits (it is taller than the strip itself)
                from PySide6.QtCore import QPoint
                centre = panel_strip_center(win.height(), strip_px) - self.mapTo(win, QPoint(0, 0)).y()
                centre *= nh / self.height()
                rows = np.nonzero(_gulim('가Ag' + label, False, px).any(axis=1))[0]   # steady line, any text
                r0, r1 = (int(rows[0]), int(rows[-1])) if len(rows) else (2, 12)
                y = round(centre + 2 - (r0 + r1) / 2)
            c.text(4, y, label, (255, 255, 255), outline=(140, 108, 76), px=px)
        else:
            c.text(2, (nh - 12) // 2 + 1, fit_text(self.text(), nw - 4), colour)
        p = QPainter(self)
        p.drawPixmap(0, 0, c.pixmap((self.width(), self.height())))
        p.end()


PANEL_TITLE_ROWS = 23      # frame rows 0..22: edge + white title band + its lower edge


def panel_title_px() -> int:
    return round(PANEL_TITLE_ROWS * SCALE[1])


def panel_strip_rows(strip_px: int) -> int:
    return max(16, round(strip_px / SCALE[1]))


def panel_strip_center(h: int, strip_px: int) -> float:
    """Screen y of the middle of panel_pixmap's steel strip: halfway between
    its top dark line (frame row 252) and its bottom one (frame row 276)."""
    nh = native_size(1, h)[1]
    rows = panel_strip_rows(strip_px)
    top, bottom = nh - rows + 1, nh - 3
    return ((top + bottom) / 2 + 0.5) * h / nh


def panel_close_rect(w: int, h: int) -> tuple[int, int, int, int]:
    """Screen rect of the title band's X (same place as the EXP meter's)."""
    nw, nh = native_size(w, h)
    x, y, s = nw - 18, 5, 12
    return (round(x * SCALE[0]), round(y * SCALE[1]), round(s * SCALE[0]), round(s * SCALE[1]))


def panel_pixmap(w: int, h: int, title: str, sub: str = '', strip_px: int = 0,
                 close: bool = True) -> QPixmap:
    """The control panel as a game window, like the EXP meter (R18): white
    title band (Gulim title, since the pixel font has no Hangul), light
    body and a steel-blue bottom strip ``strip_px`` screen pixels tall."""
    nw, nh = native_size(w, h)
    f = piece('frame')
    top = f[:30]
    strip_rows = panel_strip_rows(strip_px)
    # dark line + highlight (251..256), steel face, rounded bottom
    edge, steel, end = f[251:257], f[258:259], f[276:]
    face = max(0, strip_rows - edge.shape[0] - end.shape[0])
    bottom = np.vstack([edge, np.repeat(steel, face, axis=0), end])
    body = f[100:101]
    mid = max(0, nh - top.shape[0] - bottom.shape[0])
    col = np.vstack([top, np.repeat(body, mid, axis=0), bottom])
    c = Canvas(nw, nh)
    c.hslice(col, 0, 0, nw, 6, 6)
    x = 7 + c.text(7, 5, title, (51, 38, 30), bold=True)
    if sub:
        c.text(x + 6, 5, sub, (153, 102, 102))
    if close:
        # the game's blue X (Basic.img/BtClose), like the EXP meter's title band
        c.close_button(nw - 18, 5)
    return c.pixmap((w, h))


def hud_pixmap(w: int, h: int) -> QPixmap:
    """Panel background: the stat window body and frame (no title band)."""
    nw, nh = native_size(w, h)
    c = Canvas(nw, nh)
    c.plain()
    return c.pixmap((w, h))


def chat_tab_pixmap(label: str, width: int = 80) -> QPixmap:
    """The game's navy chat tab ('전체') with any label."""
    img = piece('chat_tab')
    c = Canvas(width, img.shape[0])
    c.hslice(img, 0, 0, width, 6, 6)
    tw = text_width(label)
    c.text((width - tw) // 2, (img.shape[0] - 12) // 2, label, (255, 255, 255))
    return c.pixmap()


class TrackedLabel(QLabel):
    """A hidden text holder: changing it repaints the parent's skin."""

    def setText(self, text):
        super().setText(text)
        parent = self.parentWidget()
        if parent is not None:
            parent.update()


def titled_pixmap(w: int, h: int, title: str, state: str = '') -> QPixmap:
    """A panel with the stat window's white title band (title + state in the
    game's pixel font) over the light body."""
    nw, nh = native_size(w, h)
    c = Canvas(nw, nh)
    c.frame(strip=False)
    c.title(7, 9, title)
    if state:
        width = sum((_title_glyph(ch).shape[1] + 1) if ch != ' ' else 3 for ch in state.upper()) - 1
        c.title(nw - 8 - width, 9, state, (70, 70, 170))
    return c.pixmap((w, h))


from PySide6.QtWidgets import QWidget  # noqa: E402


class ClassicTitleBar(QWidget):
    """The game's window title band (like CHARACTER STAT): title in the pixel
    font, the blue X button, and drag-to-move for frameless windows."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._drag = None
        self._close_state = 'normal'
        self.setFixedHeight(round(20 * SCALE[1]))
        self.setMouseTracking(True)

    def _close_rect(self):
        nw, nh = native_size(self.width(), self.height())
        return nw - 18, 5, 12, 12

    def _on_close(self, event) -> bool:
        nx = event.position().x() / SCALE[0]
        ny = event.position().y() / SCALE[1]
        x, y, w, h = self._close_rect()
        return x <= nx < x + w and y <= ny < y + h

    def paintEvent(self, event):
        nw, nh = native_size(self.width(), self.height())
        c = Canvas(nw, 20)
        f = piece('frame')
        c.hslice(f[:20], 0, 0, nw, 6, 6)
        c.title(7, 9, self._title)
        x, y, w, h = self._close_rect()
        c.close_button(x, y, self._close_state)
        p = QPainter(self)
        p.drawPixmap(0, 0, c.pixmap((self.width(), self.height())))
        p.end()

    def _set_close_state(self, state):
        if state != self._close_state:
            self._close_state = state
            self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._on_close(event):
            self._set_close_state('pressed')
            return
        self._drag = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag)
            return
        if self._close_state != 'pressed':
            self._set_close_state('hover' if self._on_close(event) else 'normal')

    def mouseReleaseEvent(self, event):
        self._drag = None
        if self._close_state == 'pressed':
            self._set_close_state('normal')
            if self._on_close(event):
                self.window().close()

    def leaveEvent(self, event):
        if self._close_state != 'pressed':
            self._set_close_state('normal')
        super().leaveEvent(event)


from PySide6.QtWidgets import QTabBar  # noqa: E402

# Inventory tabs (Equip / Use / Set Up / Etc / Cash): pink-red when chosen,
# grey otherwise; 1px dark outline, 1px light inner edge, round top corners.
_TAB_COLOURS = {
    True: ((0x7a, 0x1f, 0x33), (0xff, 0x9a, 0xb0), (0xf3, 0x5d, 0x80), (0xd9, 0x2f, 0x58)),
    False: ((0x5e, 0x5e, 0x5e), (0xe2, 0xe2, 0xe2), (0xbd, 0xbd, 0xbd), (0x95, 0x95, 0x95)),
}


def _tab_canvas(w, h, label, selected, hover=False) -> 'Canvas':
    outline, light, top, bottom = _TAB_COLOURS[bool(selected)]
    c = Canvas(w, h)
    for y in range(h):
        t = y / max(1, h - 1)
        rgb = [round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)]
        if hover and not selected:
            rgb = [min(255, v + 14) for v in rgb]
        c.px[y, :] = (rgb[2], rgb[1], rgb[0], 255)
    bgr = lambda col: (col[2], col[1], col[0], 255)
    c.px[0, 2:w - 2] = bgr(outline)
    c.px[:, 0] = bgr(outline); c.px[:, w - 1] = bgr(outline)
    c.px[1, 1] = bgr(outline); c.px[1, w - 2] = bgr(outline)
    c.px[1, 2:w - 2] = bgr(light)
    c.px[2:, 1] = bgr(light)
    for (y, x) in ((0, 0), (0, 1), (1, 0), (0, w - 1), (0, w - 2), (1, w - 1)):
        c.px[y, x] = (0, 0, 0, 0)
    tw = text_width(label)
    rows = np.nonzero(_gulim(label).any(axis=1))[0]
    r0, r1 = (int(rows[0]), int(rows[-1])) if len(rows) else (2, 12)
    c.shaded_text((w - tw) // 2, (h - (r1 - r0 + 1) + 1) // 2 - r0 + 2, label)
    return c


class ClassicTabBar(QTabBar):
    """QTabBar painted like the game's inventory tabs."""

    def tabSizeHint(self, index):
        from PySide6.QtCore import QSize
        return QSize(round((text_width(self.tabText(index)) + 14) * SCALE[0]), round(16 * SCALE[1]))

    def minimumTabSizeHint(self, index):
        return self.tabSizeHint(index)

    def paintEvent(self, event):
        p = QPainter(self)
        under = self.tabAt(self.mapFromGlobal(self.cursor().pos())) if self.underMouse() else -1
        for i in range(self.count()):
            r = self.tabRect(i)
            selected = i == self.currentIndex()
            # the chosen tab stands 2px taller, like the game
            rr = r if selected else r.adjusted(0, 2, 0, 0)
            nw, nh = native_size(rr.width() - 1, rr.height())
            c = _tab_canvas(nw, nh, self.tabText(i), selected, i == under)
            p.drawPixmap(rr.x(), rr.y(), c.pixmap((rr.width() - 1, rr.height())))
        p.end()


class ClassicSectionTitle(QLabel):
    """A page header like the buddy window's 'BUDDY LIST' bar: the game's
    blue pill stretched wide, English in the pixel font, Korean in Gulim."""

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(200, round(18 * SCALE[1]))

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(60, round(18 * SCALE[1]))

    def paintEvent(self, event):
        nw, nh = native_size(self.width(), self.height())
        c = Canvas(nw, nh)
        c.nine(piece('pill_blue_clean'), 0, 0, nw, nh, 3, 4, 10, 4)
        text = self.text().lstrip('• ').strip()
        eng, _, kor = text.partition('/')
        eng, kor = eng.strip(), kor.strip()
        x = 7
        if eng and all(ch == ' ' or ch in _PILL_EXTRA or ch in _atlas()['pill'] for ch in eng.upper()):
            x += c.pill_text(x, (nh - 7) // 2, eng.upper(), strong=True) + 8
        elif eng:
            x += c.shaded_text(x, (nh - 12) // 2 + 1, eng) + 8
        if kor:
            rows = np.nonzero(_gulim(kor).any(axis=1))[0]
            r0, r1 = (int(rows[0]), int(rows[-1])) if len(rows) else (2, 12)
            c.shaded_text(x, (nh - (r1 - r0 + 1) + 1) // 2 - r0 + 2, kor)
        p = QPainter(self)
        p.drawPixmap(0, 0, c.pixmap((self.width(), self.height())))
        p.end()


def window_pixmap(w: int, h: int) -> QPixmap:
    """A whole game window like MAPLE USER LIST: white title band on top,
    steel-blue body, rounded bottom, and the white outer line all round."""
    nw, nh = native_size(w, h)
    f = piece('frame')
    top, mid, bottom = f[:20], f[262:263], f[275:]
    col = np.vstack([top, np.repeat(mid, max(0, nh - top.shape[0] - bottom.shape[0]), axis=0), bottom])
    c = Canvas(nw, nh)
    c.hslice(col, 0, 0, nw, 6, 6)
    return c.pixmap((w, h))


# ---------------------------------------------------------------- chat window
# Cut from the user's game screenshot (resources/classic_ui/ref_chat_window.png,
# 412x573) by scripts/build_chat_skin.py and drawn 1:1, stretched only through
# plain columns/rows. 확성기 and 일반 are two such windows stacked; the outer
# edge is redrawn like the EXP meter: white line, steel-blue line, round corners.
CHAT_SKIN = {
    'w': 412, 'h': 573, 'left': 30, 'right': 47, 'col': 200, 'row': 300,
    'top': 55,          # rows 0..54: frame, title box, list top border
    'bottom': 33,       # list bottom border + a shortened bottom bar
    'gap': 4,           # transparent gap between the two windows
    'list_x': 12, 'list_r': 40,  # white list area: x 12 .. width-40
    'scroll_x': 30,     # scroll column starts at width-30 and is 22 wide
    'title_x': 28,
}
CHAT_SKIN['header'] = CHAT_SKIN['bottom'] + CHAT_SKIN['gap'] + CHAT_SKIN['top']
_EDGE_DARK = np.array([158, 123, 91, 255], np.uint8)   # #5b7b9e (BGRA), as the meter
_WHITE = np.array([255, 255, 255, 255], np.uint8)


@lru_cache(maxsize=1)
def _chat_parts():
    skin = piece('chat_skin')
    k = CHAT_SKIN
    bottom = np.vstack([skin[521:543], skin[562:573]])     # bar cut to ~14px
    return {'top': skin[:k['top']], 'mid': skin[k['row']:k['row'] + 1], 'bottom': bottom,
            'up': piece('chat_up'), 'down': piece('chat_down'), 'thumb': piece('chat_thumb')}


def _chat_hslice(rows: np.ndarray, w: int) -> np.ndarray:
    k = CHAT_SKIN
    left, right = rows[:, :k['left']], rows[:, k['w'] - k['right']:]
    mid = np.repeat(rows[:, k['col']:k['col'] + 1], max(0, w - k['left'] - k['right']), axis=1)
    return np.hstack([left, mid, right])[:, :w]


def _clean_edge(img: np.ndarray) -> None:
    """Meter-style outline: transparent outside, white line, steel-blue line,
    rounded corners. Replaces the screenshot's captured background pixels."""
    h, w = img.shape[:2]
    L, T, R, B = 2, 1, w - 1, h - 2          # where the white line runs
    img[:, :L] = 0
    img[:T] = 0
    img[B + 1:] = 0
    img[T, L:R + 1] = _WHITE
    img[B, L:R + 1] = _WHITE
    img[T:B + 1, L] = _WHITE
    img[T:B + 1, R] = _WHITE
    img[T + 1, L + 1:R] = _EDGE_DARK
    img[B - 1, L + 1:R] = _EDGE_DARK
    img[T + 1:B, L + 1] = _EDGE_DARK
    img[T + 1:B, R - 1] = _EDGE_DARK
    # round the four corners (same 3px rounding as the meter)
    for cx, cy, sx, sy in ((L, T, 1, 1), (R, T, -1, 1), (L, B, 1, -1), (R, B, -1, -1)):
        for dy in range(5):
            for dx in range(5):
                x, y = cx + sx * dx, cy + sy * dy
                d = dx + dy
                if d <= 2:
                    img[y, x] = 0
                elif d == 3:
                    img[y, x] = _WHITE
                elif d == 4 and dx and dy:
                    img[y, x] = _EDGE_DARK


def _chat_window(w: int, h: int) -> np.ndarray:
    k = CHAT_SKIN
    p = _chat_parts()
    h = max(h, k['top'] + k['bottom'] + 1)
    img = np.repeat(_chat_hslice(p['mid'], w), h, axis=0)
    img[:k['top']] = _chat_hslice(p['top'], w)
    img[h - k['bottom']:] = _chat_hslice(p['bottom'], w)
    _clean_edge(img)
    return img


def chat_window_pixmap(w: int, h: int, headers=(), panes=()) -> QPixmap:
    """Two stacked game windows (확성기 / 일반) at w x h.

    headers: y positions where the splitter handle starts (the first window
    ends there + its bottom bar, the next begins after the gap).
    panes: (y0, y1, value, maximum, page) for each white list area; draws its
    scroll buttons and a thumb at the feed's scroll position.
    """
    k = CHAT_SKIN
    p = _chat_parts()
    w = max(w, k['left'] + k['right'] + 1)
    h = max(h, k['top'] + k['bottom'] + 1)
    img = np.zeros((h, w, 4), np.uint8)
    starts = [0] + [int(y) + k['bottom'] + k['gap'] for y in headers]
    ends = [int(y) + k['bottom'] for y in headers] + [h]
    for a, b in zip(starts, ends):
        a, b = max(0, a), min(h, b)
        if b - a > k['top'] + k['bottom']:
            img[a:b] = _chat_window(w, b - a)
    sx = w - k['scroll_x']
    up, down, thumb = p['up'], p['down'], p['thumb']
    for y0, y1, value, maximum, page in panes:
        y0, y1 = int(y0), int(y1)
        top, bot = y0 - 4, y1 - 15          # as in the screenshot
        if bot - top < up.shape[0] + down.shape[0] or top < 0 or bot + down.shape[0] > h:
            continue
        img[top:top + up.shape[0], sx:sx + up.shape[1]] = up
        img[bot:bot + down.shape[0], sx:sx + down.shape[1]] = down
        track0, track1 = top + up.shape[0], bot
        room = track1 - track0 - thumb.shape[0]
        if room >= 0:
            frac = (value / maximum) if maximum and maximum > 0 else 1.0
            ty = track0 + round(room * max(0.0, min(1.0, frac)))
            img[ty:ty + thumb.shape[0], sx:sx + thumb.shape[1]] = thumb
    img = np.ascontiguousarray(img)
    q = QImage(img.data, img.shape[1], img.shape[0], img.shape[1] * 4, QImage.Format.Format_ARGB32).copy()
    return QPixmap.fromImage(q)


@lru_cache(maxsize=8)
def close_pixmap(state: str = 'normal', sx: float = 0.0, sy: float = 0.0) -> QPixmap:
    """The game's blue X at the game window's stretch (chat window title)."""
    img = piece(f'button/close_{state}')
    sx, sy = sx or SCALE[0], sy or SCALE[1]
    big = cv2.resize(img, (round(img.shape[1] * sx), round(img.shape[0] * sy)), interpolation=cv2.INTER_LINEAR)
    big = np.ascontiguousarray(big)
    return QPixmap.fromImage(QImage(big.data, big.shape[1], big.shape[0], big.shape[1] * 4,
                                    QImage.Format.Format_ARGB32).copy())


def chat_title_font() -> QFont:
    """The title box text ('equips' in the screenshot): plain 12px Dotum."""
    font = QFont('Dotum')
    font.setFamilies(['Dotum', '돋움', 'Gulim', 'Malgun Gothic'])
    font.setPixelSize(15)
    return font
