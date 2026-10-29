"""The game's item tooltip for [item] links in the translated chat (R19).

Drawn at the game's native size (1366x768 UI) from MapleStory Classic World's
own tooltip pieces (resources/classic_ui/tooltip, scripts/fetch_tooltip_ui.py),
then stretched like the game window, exactly like the other classic windows.
Layout measured from the game's own tooltip (Iron Ball / Bronze Cap / Orange):

  - Frame2 9-slice (navy 12,16,82 at 71%, outer line + see-through gap)
  - blue dot + bold name, icon cell (base + shade + 2x icon + cover)
  - REQ LEV/STR/DEX/INT/LUK/FAM with the game's digits (0 requirements dimmed)
  - BEGINNER..THIEF (orange = can wear, gray = cannot), white rule
  - orange-dot lines: 분류, 공격 속도, stats, 업그레이드 가능 횟수
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

EQUIP_W = 236
OTHER_W = 286
WHITE = QColor(255, 255, 255)
GRAY = QColor(160, 164, 190)
ORANGE = QColor(255, 170, 0)

CATEGORY_KO = {
    'Hat': '모자', 'Face Accessory': '얼굴장식', 'Eye Decoration': '눈장식', 'Eye Accessory': '눈장식',
    'Earrings': '귀고리', 'Top': '상의', 'Overall': '한벌옷', 'Bottom': '하의', 'Shoes': '신발',
    'Glove': '장갑', 'Shield': '방패', 'Cape': '망토', 'Ring': '반지', 'Pendant': '펜던트',
    'Belt': '벨트', 'Medal': '훈장', 'Mount': '라이딩', 'One-Handed Sword': '한손검',
    'One-Handed Axe': '한손도끼', 'One-Handed Blunt Weapon': '한손둔기', 'Dagger': '단검',
    'Wand': '완드', 'Staff': '스태프', 'Two-Handed Sword': '두손검', 'Two-Handed Axe': '두손도끼',
    'Two-Handed Blunt': '두손둔기', 'Spear': '창', 'Pole Arm': '폴암', 'Bow': '활',
    'Crossbow': '석궁', 'Claw': '아대', 'Knuckle': '너클', 'Gun': '총',
}
# attackSpeed -> the Korean client's wording (Iron Ball, speed 8: '슬로우')
SPEED_KO = {2: '패스터', 3: '패스터', 4: '패스트', 5: '패스트', 6: '노멀', 7: '슬로우', 8: '슬로우', 9: '슬로워'}
# the game's stat order and labels (the Korean Classic client shows these in English)
STAT_LINES = [
    ('incSTR', 'STR', ''), ('incDEX', 'DEX', ''), ('incINT', 'INT', ''), ('incLUK', 'LUK', ''),
    ('incMHP', 'MaxHP', ''), ('incMMP', 'MaxMP', ''),
    ('incWAT', 'Weapon Attack', ''), ('incPAD', 'Weapon Attack', ''),
    ('incMAT', 'Magic Attack', ''), ('incMAD', 'Magic Attack', ''),
    ('incPDD', 'Weapon Def.', ''), ('incMDD', 'Magic Def.', ''),
    ('incACC', 'Accuracy', ''), ('incEVA', 'Avoidability', ''),
    ('incSpeed', 'Speed', ''), ('incJump', 'Jump', ''),
    ('incCRT', 'Critical Rate', '%'), ('incCRD', 'Critical Damage', '%'),
]
# UIToolTip.img/Item/Equip/Job/{enable,disable}/N, placed by their own origins
# from (11, 100): BEGINNER 12, WARRIOR 61, MAGICIAN 106, BOWMAN 153, THIEF 198
JOBS = [(0, 0, 1), (1, 1, 50), (2, 2, 95), (3, 4, 142), (4, 8, 187)]


def _dir() -> Path:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'resources' / 'classic_ui' / 'tooltip'


@lru_cache(maxsize=None)
def part(name: str) -> QImage:
    img = QImage(str(_dir() / f'{name}.png'))
    return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied) if not img.isNull() else img


def _font(px: int = 12, bold: bool = False) -> QFont:
    f = QFont('Gulim')
    f.setFamilies(['Gulim', '굴림', 'Dotum', 'Malgun Gothic'])
    f.setPixelSize(px)
    f.setBold(bold)
    f.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    return f


def _frame(p: QPainter, w: int, h: int):
    """Frame2 9-slice around the whole tooltip, plus the gloss cover."""
    c = 13
    p.drawImage(QRect(c, c, w - 2 * c, h - 2 * c), part('Frame2_c'))
    p.drawImage(QRect(c, 0, w - 2 * c, c), part('Frame2_n'))
    p.drawImage(QRect(c, h - c, w - 2 * c, c), part('Frame2_s'))
    p.drawImage(QRect(0, c, c, h - 2 * c), part('Frame2_w'))
    p.drawImage(QRect(w - c, c, c, h - 2 * c), part('Frame2_e'))
    p.drawImage(0, 0, part('Frame2_nw'))
    p.drawImage(w - c, 0, part('Frame2_ne'))
    p.drawImage(0, h - c, part('Frame2_sw'))
    p.drawImage(w - c, h - c, part('Frame2_se'))
    p.drawImage(3, 3, part('Frame2_cover'))


def _icon(p: QPainter, info, x: int = 3, y: int = 26):
    """Icon cell: base (68px square), shade, the icon at 2x, cover."""
    p.drawImage(x, y, part('ItemIcon_base'))
    icon = QImage.fromData(info.icon) if info.icon else QImage()
    if not icon.isNull():
        p.drawImage(x + 17, y + 64, part('ItemIcon_shade'))
        big = icon.scaled(icon.width() * 2, icon.height() * 2, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.FastTransformation)
        cx, cy = x + 41, y + 41
        p.drawImage(cx - big.width() // 2, cy - big.height() // 2, big)
    p.drawImage(x + 4, y + 4, part('ItemIcon_cover'))


def _digits(p: QPainter, x: int, y: int, value: int, kind: str = 'Can', opacity: float = 1.0) -> int:
    p.setOpacity(opacity)
    for ch in str(max(0, int(value))):
        img = part(f'{kind}_{ch}')
        p.drawImage(x, y, img)
        x += img.width() + 1
    p.setOpacity(1.0)
    return x


def _text(p: QPainter, x: int, top: int, text: str, color=WHITE, bold=False, px=12) -> int:
    f = _font(px, bold)
    p.setFont(f)
    p.setPen(color)
    fm = QFontMetrics(f)
    p.drawText(x, top + fm.ascent(), text)
    return x + fm.horizontalAdvance(text)


def _wrap(text: str, width: int, px: int = 12) -> list[str]:
    fm = QFontMetrics(_font(px))
    lines = []
    for para in text.split('\n'):
        line = ''
        for ch in para:
            if fm.horizontalAdvance((line + ch).replace('#c', '').replace('#', '')) > width and line:
                cut = line.rfind(' ')
                if cut > len(line) // 2:
                    lines.append(line[:cut])
                    line = line[cut + 1:] + ch
                else:
                    lines.append(line)
                    line = ch
            else:
                line += ch
        lines.append(line)
    return lines


def _rich(p: QPainter, x: int, top: int, line: str, state: dict):
    """'#c...#' runs are orange, as in the game's descriptions."""
    for piece in re.split(r'(#c|#)', line):
        if piece == '#c':
            state['orange'] = True
        elif piece == '#':
            state['orange'] = False
        elif piece:
            x = _text(p, x, top, piece, ORANGE if state.get('orange') else WHITE)


def stat_lines(info, options: dict | None = None) -> tuple[list[tuple[str, str]], str]:
    """(label, value) lines under the rule, and the footnote."""
    options = options or {}
    lines: list[tuple[str, str]] = []
    category = CATEGORY_KO.get(info.sub, info.sub)
    if category:
        lines.append(('분류', category))
    if info.is_weapon and info.attack_speed in SPEED_KO:
        lines.append(('공격 속도', SPEED_KO[info.attack_speed]))
    stats = dict(info.stats)
    claimed = {k: v for k, v in options.items() if k.startswith('inc')}
    if claimed and not options.get('clean'):
        # the seller's totals; attack written as incWAT also covers incPAD data
        if 'incWAT' in claimed and 'incPAD' in stats:
            claimed['incPAD'] = claimed.pop('incWAT')
        if 'incMAT' in claimed and 'incMAD' in stats:
            claimed['incMAD'] = claimed.pop('incMAT')
        stats.update(claimed)
    seen = set()
    for key, label, unit in STAT_LINES:
        value = stats.get(key)
        if value and label not in seen:
            seen.add(label)
            lines.append((label, f'+{value}{unit}'))
    footnote = ''
    if info.is_equip and not info.cash:
        if 'slots' in options:
            slots = str(options['slots'])
        elif claimed and not options.get('clean'):
            slots = '?'
        else:
            slots = str(info.tuc)
        if info.tuc or 'slots' in options:
            lines.append(('업그레이드 가능 횟수', slots))
        footnote = '판매자가 적은 옵션 반영' if (claimed or 'slots' in options) and not options.get('clean') \
            else '노작 기준 (판매자 옵션 표기 없음)'
    return lines, footnote


def render(info, label: str = '', options: dict | None = None) -> QImage:
    """The tooltip at native game size (premultiplied ARGB)."""
    name = info.display_name(label)
    equip = info.is_equip
    title_w = QFontMetrics(_font(14, True)).horizontalAdvance(name) + 17 + 12
    if equip:
        lines, footnote = stat_lines(info, options)
        desc = _wrap(info.description(), EQUIP_W - 27) if info.description() else []
        fm = QFontMetrics(_font(12))
        bold = QFontMetrics(_font(12, True))
        need = max([fm.horizontalAdvance(f'{a}: ') + bold.horizontalAdvance(b) + 27 for a, b in lines] + [0])
        w = max(EQUIP_W, title_w, need)
        h = 138 + 16 * len(lines) + 16 * len(desc) + (16 if footnote else 0) + 4
        h = max(h, 150)
    else:
        lines, footnote = [], ''
        desc = _wrap(info.description(), OTHER_W - 98)
        w = max(OTHER_W, title_w)
        h = max(110, 36 + 16 * len(desc) + 10)
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    _frame(p, w, h)
    p.drawImage(9, 16, part('Dot_0'))
    _text(p, 17, 11, name, WHITE, bold=True, px=14)
    _icon(p, info)
    if equip:
        reqs = [('reqLEV', info.req_level), ('reqSTR', info.req_str), ('reqDEX', info.req_dex),
                ('reqINT', info.req_int), ('reqLUK', info.req_luk), ('reqPOP', info.req_pop)]
        for i, (key, value) in enumerate(reqs):
            y = 33 + 12 * i
            dim = 1.0 if value or key == 'reqLEV' else 0.35
            p.setOpacity(dim)
            p.drawImage(94, y, part(f'Can_{key}'))
            p.setOpacity(1.0)
            _digits(p, 148, y, value, 'Can', dim)
        for index, bit, dx in JOBS:
            can = info.req_job == 0 or bool(bit and info.req_job & bit)
            p.drawImage(11 + dx, 110, part(f'Job_{"enable" if can else "disable"}_{index}'))
        p.fillRect(7, 128, w - 14, 1, WHITE)
        top = 138
        for label_text, value in lines:
            p.drawImage(10, top + 4, part('Dot_1'))
            x = _text(p, 17, top, f'{label_text}: ')
            _text(p, x, top, value, WHITE, bold=True)
            top += 16
        state: dict = {}
        for line in desc:
            _rich(p, 17, top, line, state)
            top += 16
        if footnote:
            _text(p, 17, top + 1, footnote, GRAY, px=11)
    else:
        state = {}
        top = 36
        for line in desc:
            _rich(p, 88, top, line, state)
            top += 16
    p.end()
    return img


def scaled_pixmap(img: QImage) -> QPixmap:
    from . import classic_ui as CU
    w = max(1, round(img.width() * CU.SCALE[0]))
    h = max(1, round(img.height() * CU.SCALE[1]))
    return QPixmap.fromImage(img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))


def label_at(row, pos, head_len: int = 0):
    """(label, index) of the [item] under ``pos`` in a rich-text chat row,
    or None. ``index`` counts links after the first ``head_len`` characters
    (the '[아확] nickname : ' head is not an item)."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QTextDocument
    text_html = row.text()
    if '[' not in text_html:
        return None
    cr = row.contentsRect()
    # mouse moves arrive many times a second: lay the row out once per size
    cached = getattr(row, '_tip_doc', None)
    if cached and cached[0] == (text_html, cr.width()):
        doc = cached[1]
    else:
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(row.font())
        doc.setHtml(text_html)
        doc.setTextWidth(max(1, cr.width()))
        try:
            row._tip_doc = ((text_html, cr.width()), doc)
        except Exception:
            pass
    local = QPointF(pos.x() - cr.x(), pos.y() - cr.y())
    if local.y() < 0 or local.y() > doc.size().height() or local.x() < 0:
        return None
    at = doc.documentLayout().hitTest(local, Qt.HitTestAccuracy.ExactHit)
    if at < 0:
        return None
    plain = doc.toPlainText()
    index = 0
    for m in re.finditer(r'\[[^\[\]\n]+\]', plain):
        if m.start() < head_len:
            continue
        if m.start() <= at < m.end():
            return m.group()[1:-1].strip(), index
        index += 1
    return None


class ItemToolTip(QWidget):
    """Click-through, never-focused popup that follows the mouse."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pix = QPixmap()
        self._key = None

    def show_item(self, info, label: str, options: dict, global_pos: QPoint):
        key = (info.id, label, tuple(sorted(options.items())))
        if key != self._key:
            self._key = key
            self._pix = scaled_pixmap(render(info, label, options))
            self.resize(self._pix.size())
        # like the game: below-right of the cursor, kept on screen
        x, y = global_pos.x() + 14, global_pos.y() + 18
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen is not None:
            g = screen.availableGeometry()
            if x + self.width() > g.right():
                x = global_pos.x() - self.width() - 6
            if y + self.height() > g.bottom():
                y = max(g.top(), g.bottom() - self.height())
            x = max(g.left(), x)
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def hide_item(self):
        self._key = None
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pix)
        p.end()
