"""R18 windows in the game's own UI: HUNTING LOG, PRICE LOG, KEYWORD ALERT.

Same construction as the settings window: the game's title band (pixel font
+ blue X), the window frame pieces (white outer line, steel body, rounded
bottom), BUDDY LIST style section bars, game buttons and the game scrollbar.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QFont, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit,
                               QApplication)

from . import classic_ui as CU
from . import visual_theme as T
from .visual_theme import settings_stylesheet

# Table in the stat window's palette: blue header bar like 'BUDDY LIST',
# white rows on the light body, beige alternate rows like value cells.
TABLE_QSS = f"""
QTableWidget{{background:#ffffff;alternate-background-color:#f4f2ea;color:{T.TEXT};
  gridline-color:{T.VALUE_EDGE};border:1px solid {T.FRAME};font-family:'Dotum','Gulim','Malgun Gothic';
  font-size:12px;selection-background-color:#dfe8c0;selection-color:{T.TEXT};}}
QHeaderView::section{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #6f9ac4,stop:1 {T.BLUE_DARK});
  color:#ffffff;font-weight:bold;font-size:11px;border:0px;border-right:1px solid {T.BLUE_DARK};padding:3px 4px;}}
QTableCornerButton::section{{background:{T.BLUE_DARK};border:0px;}}
QLabel#logSummary{{color:{T.TEXT};font-size:12px;}}
"""


class ClassicWindow(QWidget):
    """Frameless window painted from the game's frame pieces."""

    def __init__(self, title: str, parent=None, size=(560, 420)):
        # On top like the addon's other windows: opened from the panel (which
        # never takes focus) Windows otherwise leaves it behind the game.
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(settings_stylesheet('square')+TABLE_QSS)
        self.setWindowTitle('글클메 애드온 · '+title)
        self.resize(*size)
        area = QApplication.primaryScreen().availableGeometry()
        self.move(area.left()+(area.width()-size[0])//2, area.top()+(area.height()-size[1])//2)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(CU.ClassicTitleBar(title, self))
        body = QWidget(self)
        shell.addWidget(body, 1)
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(10, 8, 10, 14)
        self.body.setSpacing(7)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(0, 0, CU.window_pixmap(self.width(), self.height()))
        p.end()

    @staticmethod
    def section(title: str):
        label = CU.ClassicSectionTitle(title)
        label.setFixedHeight(round(18*CU.SCALE[1]))
        return label

    @staticmethod
    def button(text: str, kind='blue'):
        b = CU.ClassicButton(text)
        b.setProperty('classic', kind)
        # never narrower than the game's own OK / CANCEL (47 px)
        b.setMinimumWidth(round(47 * CU.SCALE[0]))
        return b

    def bottom_row(self, action, slot):
        """The game's window bottom row (KEY CONFIG): the green action on the
        left like DEFAULT / CLEAR ALL, the orange CANCEL-style close right."""
        row = QHBoxLayout()
        action.clicked.connect(slot)
        row.addWidget(action)
        row.addStretch(1)
        close = self.button('닫기', 'cancel')
        close.clicked.connect(self.close)
        row.addWidget(close)
        return row

    @staticmethod
    def table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setAlternatingRowColors(True)
        t.verticalHeader().hide()
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        t.setWordWrap(False)
        return t


def _cell(text, editable=False, align=Qt.AlignmentFlag.AlignLeft):
    item = QTableWidgetItem(str(text))
    flags = item.flags()
    item.setFlags(flags | Qt.ItemFlag.ItemIsEditable if editable else flags & ~Qt.ItemFlag.ItemIsEditable)
    item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
    return item


# --------------------------------------------------------------- hunting
class HuntLogWindow(ClassicWindow):
    """Every finished EXP-meter session; the place column is editable."""

    def __init__(self, parent=None, path=None):
        super().__init__('HUNTING LOG', None, (640, 430))
        from .hunt_extras import load_hunt_log
        self.path = path
        self.rows = load_hunt_log(path)
        self.body.addWidget(self.section('HUNTING LOG  /  사냥 기록'))
        self.summary = QLabel()
        self.summary.setObjectName('logSummary')
        self.body.addWidget(self.summary)
        self.view = self.table(['날짜', '사냥터 (직접 입력)', '시간', '레벨', '획득 경험치', '시간당', '물약'])
        self.view.itemChanged.connect(self._renamed)
        self.body.addWidget(self.view, 1)
        self.body.addLayout(self.bottom_row(self.button('선택 기록 삭제', 'lime'), self._delete))
        self._fill()

    def _fill(self):
        from .hunt_extras import format_duration, format_amount
        self.view.blockSignals(True)
        self.view.setRowCount(0)
        for r in reversed(self.rows):   # newest first
            n = self.view.rowCount()
            self.view.insertRow(n)
            lv = (f"{r.get('start_level') or '?'} → {r.get('end_level') or '?'}"
                  if r.get('start_level') != r.get('end_level') else f"{r.get('end_level') or '?'}")
            values = [r.get('started', ''), r.get('place', ''), format_duration(r.get('seconds', 0)), lv,
                      f"{int(r.get('gained_exp', 0)):,}" + (f" ({r.get('gained_percent', 0):.2f}%)" if r.get('gained_percent') else ''),
                      format_amount(r.get('exp_per_hour') or None), f"{int(r.get('potions_total', 0)):,}개"]
            for col, value in enumerate(values):
                right = col in (4, 5, 6)
                self.view.setItem(n, col, _cell(value, editable=(col == 1),
                                                align=Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft))
        self.view.blockSignals(False)
        rates = [r.get('exp_per_hour') or 0 for r in self.rows if r.get('exp_per_hour')]
        best = max(self.rows, key=lambda r: r.get('exp_per_hour') or 0, default=None)
        text = f'총 {len(self.rows)}회'
        if rates:
            text += f'  ·  평균 시간당 경험치 {format_amount(int(sum(rates)/len(rates)))}'
        if best and best.get('exp_per_hour'):
            text += f"  ·  최고 {format_amount(best['exp_per_hour'])} ({best.get('place') or best.get('started')})"
        self.summary.setText(text if self.rows else '아직 기록이 없습니다 · 측정기에서 시작 → 종료하면 저장됩니다')

    def _index(self, view_row):
        return len(self.rows)-1-view_row

    def _renamed(self, item):
        if item.column() != 1:
            return
        from .hunt_extras import save_hunt_log
        self.rows[self._index(item.row())]['place'] = item.text().strip()
        save_hunt_log(self.rows, self.path)
        self._fill()

    def _delete(self):
        from .hunt_extras import save_hunt_log
        picked = sorted({i.row() for i in self.view.selectedItems()}, reverse=True)
        for view_row in picked:
            del self.rows[self._index(view_row)]
        if picked:
            save_hunt_log(self.rows, self.path)
            self._fill()


# --------------------------------------------------------------- prices
class PriceLogWindow(ClassicWindow):
    """Recent Free Market prices gathered from trade megaphones/chat."""

    def __init__(self, log, parent=None):
        super().__init__('PRICE LOG', None, (860, 520))
        self.log = log
        self.body.addWidget(self.section('PRICE LOG  /  자유시장 시세 기록 (최근 7일)'))
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('아이템 검색 (영어 또는 한글)')
        self.search.textChanged.connect(lambda _t: self._timer.start(250))
        top.addWidget(self.search, 1)
        refresh = self.button('새로고침')
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        self.body.addLayout(top)
        self.summary = QLabel()
        self.summary.setObjectName('logSummary')
        self.body.addWidget(self.summary)
        self.view = self.table(['아이템', '한글명', '팝니다 (최저 / 중간 / 최고)', '삽니다 (최저 / 중간 / 최고)', '최근', '언제'])
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate((150, 130, 205, 205, 85, 60)):
            self.view.setColumnWidth(col, width)
        self.body.addWidget(self.view, 1)
        self.body.addLayout(self.bottom_row(self.button('기록 전부 지우기', 'lime'), self._clear))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def refresh(self):
        from .price_log import money
        rows = self.log.summary(self.search.text())
        self.view.setRowCount(0)
        now = time.time()

        def band(s):
            if not s:
                return '—'
            lo, mid, hi, n = s
            return f'{money(lo)} / {money(mid)} / {money(hi)}  ({n}건)'

        def ago(ts):
            m = int((now-ts)//60)
            return '방금' if m < 1 else f'{m}분 전' if m < 60 else f'{m//60}시간 전' if m < 1440 else f'{m//1440}일 전'
        for r in rows:
            n = self.view.rowCount()
            self.view.insertRow(n)
            side = '팜' if r['last_side'] == 'S' else '삼'
            for col, value in enumerate([r['item'], r['korean'] or '', band(r['sell']), band(r['buy']),
                                         f"{money(r['last_price'])} ({side})", ago(r['last'])]):
                self.view.setItem(n, col, _cell(value))
        total = sum(r['count'] for r in rows)
        self.summary.setText(f'{len(rows)}개 아이템 · 거래 글 {total}건' if rows
                             else '아직 기록이 없습니다 · 번역을 켜 두면 S>/B> 거래 글의 가격이 자동으로 쌓입니다')

    def _clear(self):
        self.log.clear()
        self.refresh()


# --------------------------------------------------------------- help
def help_image_path():
    """The features & usage poster (docs/how-to-use.html rendered to PNG)."""
    import sys
    from pathlib import Path
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return base / 'resources' / 'help' / 'how-to-use.png'


class HelpWindow(ClassicWindow):
    """HOW TO USE: the poster of every feature and how to use them."""

    def __init__(self, parent=None):
        super().__init__('HOW TO USE', None, (900, 780))
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QScrollArea, QFrame
        self.body.addWidget(self.section('HOW TO USE  /  기능 · 사용법'))
        area = QScrollArea()
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setStyleSheet('QScrollArea{background:transparent;}')
        self.poster = QLabel()
        pix = QPixmap(str(help_image_path()))
        if pix.isNull():
            self.poster.setText('사용법 이미지를 찾지 못했습니다 (resources/help/how-to-use.png)')
        else:
            self.poster.setPixmap(pix.scaledToWidth(850, Qt.TransformationMode.SmoothTransformation))
        area.setWidget(self.poster)
        self.body.addWidget(area, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = self.button('닫기', 'cancel')
        close.clicked.connect(self.close)
        row.addWidget(close)
        self.body.addLayout(row)


# --------------------------------------------------------------- alerts
class KeywordToast(QWidget):
    """Small KEYWORD ALERT window; closes itself after a few seconds."""
    _open: list = []

    def __init__(self, keyword: str, nickname: str, text: str, anchor: QRect | None = None, seconds=7):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.keyword = keyword
        w = 360
        lay = QVBoxLayout(self)
        top = round(20*CU.SCALE[1])+6
        lay.setContentsMargins(12, top, 12, 12)
        lay.setSpacing(4)
        head = QLabel(f'「{keyword}」 발견')
        head.setStyleSheet(f'color:{T.PINK_DARK};font-weight:bold;font-size:12px;background:transparent;')
        body = QLabel(f'<b>{_esc(nickname)}</b> : {_esc(text)}')
        body.setWordWrap(True)
        body.setStyleSheet(f'color:{T.TEXT};font-size:12px;background:transparent;')
        body.setFont(QFont('Malgun Gothic', 10))
        lay.addWidget(head)
        lay.addWidget(body)
        self.setFixedWidth(w)
        self.adjustSize()
        self._place(anchor)
        QTimer.singleShot(int(seconds*1000), self.close)

    def _place(self, anchor):
        screen = QApplication.primaryScreen().availableGeometry()
        stacked = sum(t.height()+6 for t in KeywordToast._open if t.isVisible())
        if anchor is not None and anchor.isValid():
            x = anchor.left()
            y = anchor.top()-self.height()-6-stacked
            if y < screen.top():
                y = anchor.bottom()+6+stacked
        else:
            x = screen.right()-self.width()-16
            y = screen.bottom()-self.height()-16-stacked
        self.move(max(screen.left(), min(x, screen.right()-self.width())), max(screen.top(), y))
        KeywordToast._open.append(self)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(0, 0, CU.titled_pixmap(self.width(), self.height(), 'KEYWORD ALERT'))
        p.end()

    def mousePressEvent(self, event):
        self.close()

    def closeEvent(self, event):
        if self in KeywordToast._open:
            KeywordToast._open.remove(self)
        super().closeEvent(event)


def _esc(text: str) -> str:
    import html
    return html.escape(str(text or ''))[:240]
