"""Compact, screen-only Maple chat translator.

The capture source uses an automatically detected bottom chat ROI. No DLL
injection, memory access, packet inspection or automatic game chat sending.
"""
from __future__ import annotations
import re

import ctypes
import html
import logging
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal, QEvent, QUrl
from PySide6.QtGui import QGuiApplication, QFont, QFontMetrics, QPainter, QColor, QPen, QTextCursor, QFontDatabase, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QComboBox, QTextEdit, QVBoxLayout, QHBoxLayout, QDialog,
    QDoubleSpinBox, QSpinBox, QCheckBox, QMessageBox, QFileDialog, QSizeGrip,
    QColorDialog, QScrollArea, QSizePolicy, QTabWidget, QSplitter,
)

from .core import load_config, save_config, is_valid_region, config_path
from .chat_history import ChatHistoryStore
from .history_dialog import HistoryDialog
from .hunt_widget import HuntWindow
from .worker import LiveWorker
from .timings import LatencyBook
from .translation import Translator, prepare_models
from .item_catalog import CatalogError, install_catalog, current_catalog
from .noonnu_fonts import cached_font_from_noonnu, FontUrlError
from .layout import (GAME_RESOLUTIONS, estimate_chat_area, dock_to_side, resolution_size,
                     hud_panel_geometry, game_ui_scale, hud_relative_region)
from .game_window import find_maple_window, region_to_relative, relative_to_region
from .obs_source import OBSChatSource
from .chat_style import normalize_style, text_css, rgba_color, qt_rgba_color, effective_font_color
from .visual_theme import normalize_variant, radius_px, panel_stylesheet, strip_stylesheet, settings_stylesheet
from . import visual_theme as T
from . import classic_ui as CU
from .chat_render import soft_break_long_tokens, colored_item_html
from .megaphone import tinted_rgba
from .window_behavior import (capture_allowed, foreground_context, is_topmost,
                              set_native_stack, restore_below_foreground, Z_ORDER_MODES)

LOG = logging.getLogger(__name__)

PANEL_STYLE = panel_stylesheet('rounded')



def virtual_desktop() -> QRect:
    rect = QRect()
    for screen in QGuiApplication.screens():
        rect = rect.united(screen.geometry())
    return rect


def monitor_for(region: dict | None) -> QRect:
    if is_valid_region(region):
        p = QPoint(region['left'] + region['width']//2, region['top'] + region['height']//2)
        screen = QGuiApplication.screenAt(p)
        if screen:
            return screen.geometry()
    return QGuiApplication.primaryScreen().geometry()


def game_client_rect(keyword: str, region: dict | None) -> QRect | None:
    # Win32 PID/executable validated handle (no title-only browser matching).
    game=find_maple_window(keyword=keyword)
    if not game:
        return None
    x,y,w,h=game.rect
    return QRect(x,y,w,h)


def enable_obs_window_capture(widget: QWidget) -> bool:
    """Clear v0.3.5 exclusion: native OBS window capture can see the chat."""
    return capture_allowed(int(widget.winId()))


class RegionSelector(QWidget):
    """Non-dimming, mouse-active ROI picker with guaranteed cancel/restore.

    On Windows, a fully zero-alpha layered QWidget can be click-through.
    Paint an almost invisible alpha-2 hit-test layer so Maple stays visible
    while Qt can reliably receive the selection drag and Escape key.
    """
    selected = Signal(object)
    def __init__(self):
        super().__init__(None)
        self.start: QPoint | None = None
        self.end: QPoint | None = None
        self._completed = False
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(virtual_desktop())

    def finish(self, region):
        if self._completed:
            return
        self._completed = True
        self.selected.emit(region)
        self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.finish(None)  # Right click cancels, same as ESC.
        elif event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self.end = event.position().toPoint()
        rect = QRect(self.start,self.end).normalized()
        origin = self.geometry().topLeft()
        if rect.width() >= 100 and rect.height() >= 25:
            self.finish({'left':rect.left()+origin.x(), 'top':rect.top()+origin.y(),
                         'width':rect.width(), 'height':rect.height()})
        else:
            self.finish(None)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.finish(None)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # A window-manager close is also a cancel: do not leave the app hidden.
        if not self._completed:
            self._completed = True
            self.selected.emit(None)
        super().closeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        # Alpha 2/255: visually undimmed, but not click-through on layered
        # Windows surfaces. The old black alpha-135 wash must not return.
        p.fillRect(self.rect(), QColor(0, 0, 0, 2))
        hint = QRect(12, 12, min(self.width()-24, 660), 42)
        if hint.width() > 10:
            p.fillRect(hint, QColor(15, 30, 44, 190))
            p.setPen(QColor(255,255,255))
            p.setFont(QFont('Malgun Gothic',11,QFont.Weight.Bold))
            p.drawText(hint.adjusted(9,0,-6,0), Qt.AlignmentFlag.AlignVCenter,
                       '하단 채팅을 드래그 | ESC/우클릭: 취소 | 60초 후 자동 복원')
        if self.start is not None and self.end is not None:
            rect = QRect(self.start,self.end).normalized()
            p.setPen(QPen(QColor(120,218,217), 2))
            p.drawRect(rect)


# Usual megaphone band colours measured on the game (R14/R18 recordings)
TONE_BANDS={'yellow':'#e6b505','pink':'#dbaab9','cyan':'#5cdac6','green':'#8fd18a',
            'blue':'#8fb1dd','red':'#e88c8c','gray':'#c8ccd1'}


def _luminance(color: str) -> float:
    value=color.lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}',value):
        return -1.
    def channel(c):
        c=int(c,16)/255
        return c/12.92 if c<=.03928 else ((c+.055)/1.055)**2.4
    r,g,b=(channel(value[i:i+2]) for i in (0,2,4))
    return .2126*r+.7152*g+.0722*b


def readable_on(color: str, background: str) -> str:
    """Keep a colour unless its contrast with the band is below 2.5:1."""
    fg,bg=_luminance(color),_luminance(background)
    if fg<0 or bg<0:
        return color
    contrast=(max(fg,bg)+.05)/(min(fg,bg)+.05)
    if contrast>=2.5:
        return color
    return '#000000' if bg>.18 else '#ffffff'


def _tool_windows(self):
    """R18: windows the user works in (EXP meter, price log, hunting log,
    keyword alerts). They must sit ABOVE the chat feed, never under it."""
    out=[]
    meter=getattr(self,'hunt_widget',None)
    if meter is not None and meter.isVisible() and not getattr(meter,'_pinned',False):
        out.append(meter)
    for w in (getattr(self,'_price_window',None),getattr(meter,'_log_window',None)):
        try:
            if w is not None and w.isVisible():
                out.append(w)
        except RuntimeError:   # already deleted (closed with WA_DeleteOnClose)
            pass
    try:
        from .classic_windows import KeywordToast
        out.extend(t for t in list(KeywordToast._open) if t.isVisible())
    except Exception:
        pass
    return out

def _stack_tools(self, mode, force):
    """Put tool windows into the same group as the chat, above it."""
    for w in _tool_windows(self):
        hwnd=int(w.winId())
        if force or not is_topmost(hwnd):
            if mode=='always':
                set_native_stack(hwnd,'always')
            else:
                set_native_stack(hwnd,'game',game_foreground=True,
                                 game_topmost=is_topmost(self.game_hwnd))


class Glass(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.theme_variant='rounded'
        self.setStyleSheet(panel_stylesheet(self.theme_variant))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        self.card = QFrame()
        self.card.setObjectName('glass')
        outer.addWidget(self.card)

    def set_theme_variant(self, variant: str):
        self.theme_variant=normalize_variant(variant)
        self.setStyleSheet(panel_stylesheet(self.theme_variant))
        if self.card.objectName() == 'glass':
            self.card.setProperty('theme_variant',self.theme_variant)
            self.card.style().unpolish(self.card)
            self.card.style().polish(self.card)


class FloatingChat(Glass):
    """Movable/resizable chat only, with a temporary edit affordance."""
    geometry_edited = Signal()
    ratio_changed = Signal(int)

    history_error = Signal(str)

    def __init__(self, history_store=None):
        super().__init__()
        self.setWindowTitle('글클메 애드온 - 채팅')
        self.history_store=history_store
        self.top_mode = 'game'
        self.mode = ''
        self.editing = False
        self._drag_origin = None
        self._feed_drag = None
        self._allow_resize_signal = False
        self._messages: list[tuple[str,str]] = []
        self._records: list[dict] = []
        # Keep Qt widgets alive between messages: repainting the complete feed
        # for each OCR result made the small, translucent overlay flicker.
        self._live_rows: list[tuple[QLabel, QVBoxLayout]] = []
        self._row_sequence = 0
        self._scroll_pending = False
        # Auto-follow until the reader uses the wheel to inspect older chat.
        self._auto_follow = {}
        self._feeds_by_viewport = {}
        self.scroll_interactive = False
        self._ratio_general = 70
        self._restoring_split = True
        self._family = 'Malgun Gothic'
        self._size_pt = 13
        self._band_opacity = 92
        self._style = normalize_style({})
        self.setMinimumSize(180, 92)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.edit_tip = QLabel('이동: 창 안을 드래그  |  크기: 우하단 모서리')
        self.edit_tip.setStyleSheet('color:#ffffff; font-size:10px; font-weight:bold;'
                                    f'background:{T.BLUE}; padding:1px 4px;')
        self.edit_tip.hide()
        self.edit_tip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self.edit_tip)
        # Vertical splitter: megaphones TOP (30%), general chat BOTTOM (70%).
        # QSplitter preserves the user's manually dragged divider as height changes.
        self.splitter = QSplitter(Qt.Orientation.Vertical, self.card)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(2)
        # Hairline spanning the full pane width (no left/right margins).
        self.splitter.setStyleSheet(f'QSplitter::handle:vertical{{background:{T.FRAME};border:0;margin:0;padding:0;}}')
        self.feed = QScrollArea()  # retained for compatibility with display diagnostics
        self.feed_rows = None
        self.general_feed, self.general_rows = self._new_feed(self.feed)
        self.mega_feed, self.mega_rows = self._new_feed()
        # Each pane gets a classic-UI tab on top: 확성기 채팅 / 일반 채팅.
        self.mega_tab = self._tabbed(self.mega_feed, '확성기 채팅', T.PINK, T.PINK_DARK)
        self.general_tab = self._tabbed(self.general_feed, '일반 채팅', T.BLUE, T.BLUE_DARK)
        self.splitter.addWidget(self.mega_tab)
        self.splitter.addWidget(self.general_tab)
        self.splitter.setStretchFactor(0,3)
        self.splitter.setStretchFactor(1,7)
        self.splitter.splitterMoved.connect(self._splitter_moved)
        lay.addWidget(self.splitter,1)
        self.feed_rows=self.general_rows
        self.feed_container=self.general_feed.widget()
        self.grip = QSizeGrip(self)
        self.grip.setFixedSize(20, 20)
        self.grip.setStyleSheet(f'background:{T.BLUE}; border:1px solid {T.BLUE_DARK}; border-radius:3px;')
        self.grip.hide()
        self.card.installEventFilter(self)
        self._skin=None   # classic chat-window skin (screenshot), set by size
        self._thumb_drag=None;self._scroll_hold=None
        self._card_layout=lay
        for feed in (self.mega_feed,self.general_feed):
            bar=feed.verticalScrollBar()
            bar.valueChanged.connect(self._skin_repaint)
            bar.rangeChanged.connect(self._skin_repaint)
        self.splitter.splitterMoved.connect(self._skin_repaint)
        self.resize(470, 140)
        self.set_mode('overlay')
        self._update_skin()

    def apply_font(self, family: str, pt: int):
        self._family = family or 'Malgun Gothic'
        self._size_pt = max(8, min(38, int(pt)))
        self.setMinimumHeight(max(92, self._size_pt*3))
        self._render_messages()

    def apply_theme(self, variant: str):
        self.set_theme_variant(variant)
        self.apply_style(self._style,self._opacity if hasattr(self,'_opacity') else 86)

    def apply_style(self, value: dict, opacity: int, band_opacity: int | None = None):
        self._style = normalize_style(value)
        self._opacity = max(0,min(100,int(opacity)))
        if band_opacity is not None:
            self._band_opacity = max(0,min(100,int(band_opacity)))
        bg = qt_rgba_color(self._style['background_color'], self._opacity)
        corner=radius_px(self.theme_variant)
        if getattr(self,'_skin',None):
            self.card.setStyleSheet('QFrame#glass {background:transparent;border:0;}')
        else:
            self.card.setStyleSheet(
                'QFrame#glass {background-color:' + bg + '; border:2px solid ' + T.FRAME + ';'
                f'border-radius:{corner}px;}}')
        self._render_messages()

    # ------------------------------------------------ classic window skin
    SKIN_MIN_HEIGHT = 200

    def _update_skin(self):
        """Use the game's chat-window skin when the window is tall enough."""
        want=self.height()>=self.SKIN_MIN_HEIGHT
        if want==self._skin:
            return
        self._skin=want
        k=CU.CHAT_SKIN
        if want:
            self._card_layout.setContentsMargins(k['list_x'],k['top'],k['list_r'],k['bottom'])
            self.splitter.setHandleWidth(k['header'])
            self.splitter.setStyleSheet('QSplitter::handle:vertical{background:transparent;border:0;margin:0;padding:0;}')
        else:
            self._card_layout.setContentsMargins(0,0,0,0)
            self.splitter.setHandleWidth(2)
            self.splitter.setStyleSheet(f'QSplitter::handle:vertical{{background:{T.FRAME};border:0;margin:0;padding:0;}}')
        for pane in (self.mega_tab,self.general_tab):
            pane._tab_bar.setVisible(not want)
        if hasattr(self,'_opacity'):
            self.apply_style(self._style,self._opacity)
        self.update()

    def _scroll_parts(self):
        """Scroll buttons/track/thumb of each pane, in window pixels
        (the same geometry chat_window_pixmap draws)."""
        k=CU.CHAT_SKIN
        sx=self.width()-k['scroll_x']
        parts=[]
        for feed in (self.mega_feed,self.general_feed):
            y0=feed.mapTo(self,feed.rect().topLeft()).y()
            y1=y0+feed.height()
            top,bot=y0-4,y1-15
            if bot-top<37:
                continue
            bar=feed.verticalScrollBar()
            track0,track1=top+18,bot
            room=max(0,track1-track0-38)
            frac=(bar.value()/bar.maximum()) if bar.maximum()>0 else 1.0
            ty=track0+round(room*frac)
            parts.append({'feed':feed,'up':QRect(sx,top,22,18),'down':QRect(sx,bot,22,19),
                          'track':QRect(sx,track0,22,track1-track0),'thumb':QRect(sx,ty,22,38),'room':room})
        return parts

    def _scroll_step(self, feed, amount):
        bar=feed.verticalScrollBar()
        bar.setValue(bar.value()+amount)
        self._auto_follow[feed]=(bar.value()>=bar.maximum()-2)

    def _scroll_repeat_tick(self):
        if self._scroll_hold is None:
            return
        feed,amount=self._scroll_hold
        self._scroll_step(feed,amount)
        self._scroll_timer.start(55)

    def _scroll_event(self, event):
        kind=event.type()
        # a quick second click arrives as a double-click: treat it as a press
        if kind in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonDblClick) and event.button()==Qt.MouseButton.LeftButton:
            pos=event.position().toPoint()
            for part in self._scroll_parts():
                feed=part['feed'];bar=feed.verticalScrollBar()
                line=max(18,QFontMetrics(QFont(self._family,self._size_pt)).height())
                amount=None
                if part['up'].contains(pos):amount=-line
                elif part['down'].contains(pos):amount=line
                elif part['thumb'].contains(pos):
                    self._thumb_drag=(feed,pos.y(),bar.value(),part['room'])
                    return True
                elif part['track'].contains(pos):
                    page=max(line,bar.pageStep())
                    amount=-page if pos.y()<part['thumb'].top() else page
                if amount is not None:
                    self._scroll_step(feed,amount)
                    self._scroll_hold=(feed,amount)
                    if not hasattr(self,'_scroll_timer'):
                        self._scroll_timer=QTimer(self)
                        self._scroll_timer.setSingleShot(True)
                        self._scroll_timer.timeout.connect(self._scroll_repeat_tick)
                    self._scroll_timer.start(320)   # hold to keep scrolling
                    return True
            return False
        if kind==QEvent.Type.MouseMove and getattr(self,'_thumb_drag',None):
            feed,start_y,start_value,room=self._thumb_drag
            bar=feed.verticalScrollBar()
            if room>0:
                bar.setValue(round(start_value+(event.position().y()-start_y)*bar.maximum()/room))
                self._auto_follow[feed]=(bar.value()>=bar.maximum()-2)
            return True
        if kind==QEvent.Type.MouseButtonRelease and (getattr(self,'_thumb_drag',None) or getattr(self,'_scroll_hold',None)):
            self._thumb_drag=None;self._scroll_hold=None
            if hasattr(self,'_scroll_timer'):self._scroll_timer.stop()
            return True
        return False

    def _skin_repaint(self,*_):
        if self._skin:
            self.update()

    def paintEvent(self, event):
        if not self._skin:
            return super().paintEvent(event)
        k=CU.CHAT_SKIN
        handle=self.splitter.handle(1)
        header_y=self.splitter.mapTo(self,handle.pos()).y()
        panes=[]
        for feed in (self.mega_feed,self.general_feed):
            top=feed.mapTo(self,feed.rect().topLeft()).y()
            bar=feed.verticalScrollBar()
            panes.append((top,top+feed.height(),bar.value(),bar.maximum(),bar.pageStep()))
        p=QPainter(self)
        p.setOpacity(max(.35,min(1.0,getattr(self,'_opacity',100)/100)))
        p.drawPixmap(0,0,CU.chat_window_pixmap(self.width(),self.height(),[header_y],panes))
        # title boxes: 확성기 채팅 (top) and 일반 채팅 (between the panes)
        p.setOpacity(1.0)
        p.setFont(CU.chat_title_font())
        p.setPen(QColor(0,0,0))
        p.drawText(QRect(k['title_x'],9,self.width()-k['title_x']-40,32),
                   Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.mega_tab._title)
        p.drawText(QRect(k['title_x'],header_y+k['bottom']+k['gap']+9,self.width()-k['title_x']-40,32),
                   Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.general_tab._title)
        # the game's blue X at the right of each title box (decoration, like
        # every game window's title; the window itself is closed from the panel)
        x_pix=CU.close_pixmap('normal',*CU.CHAT_SKIN_SCALE)
        for top in (9,header_y+k['bottom']+k['gap']+9):
            p.drawPixmap(self.width()-33,top+(32-x_pix.height())//2,x_pix)
        p.end()

    def _tabbed(self, feed, title, colour, dark):
        """Wrap a chat feed with a small tab like the game's chat tab."""
        pane=QWidget()
        pane.setObjectName('chatPane')
        pane.setStyleSheet('QWidget#chatPane{background:transparent;border:0}')
        pane.setMinimumHeight(0)
        box=QVBoxLayout(pane)
        box.setContentsMargins(0,0,0,0)
        box.setSpacing(0)
        bar=QWidget()
        bar.setObjectName('chatTabBar')
        bar.setStyleSheet('QWidget#chatTabBar{background:transparent;border:0;}')
        bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        row=QHBoxLayout(bar)
        row.setContentsMargins(2,2,0,1)
        row.setSpacing(0)
        # The game's own navy chat tab ('전체') with our label, drawn at the
        # game's native size and stretched like the game.
        tab=QLabel()
        tab.setAccessibleName(title)
        tab.setToolTip(title)
        tab.setPixmap(CU.chat_tab_pixmap(title))
        tab.setStyleSheet('background:transparent;border:0;padding:0;')
        row.addWidget(tab)
        row.addStretch(1)
        # decorative blue X, like the game window titles
        x_mark=QLabel()
        x_mark.setPixmap(CU.close_pixmap('normal',*CU.CHAT_SKIN_SCALE))
        x_mark.setStyleSheet('background:transparent;border:0;padding:0;')
        row.addWidget(x_mark,0,Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(4)
        box.addWidget(bar)
        box.addWidget(feed,1)
        pane._tab_bar=bar
        pane._title=title
        return pane

    def _new_feed(self, scroll=None):
        scroll=scroll or QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizeAdjustPolicy(QScrollArea.SizeAdjustPolicy.AdjustIgnored)
        scroll.setMinimumWidth(0)
        scroll.setMinimumHeight(28)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet('QScrollArea{background:transparent;border:0}QScrollBar{width:0;height:0}')
        # The old input-transparent QScrollArea never received mouse-wheel
        # events. Transparent *children* leave the viewport in charge.
        scroll.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,False)
        scroll.viewport().installEventFilter(self)
        scroll.viewport().setMouseTracking(True)   # R19: [item] tooltips on hover
        self._feeds_by_viewport[scroll.viewport()] = scroll
        self._auto_follow[scroll] = True
        content=QWidget()
        content.setStyleSheet('background:transparent;border:0')
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        content.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        rows=QVBoxLayout(content)
        rows.setContentsMargins(0,0,0,7)
        rows.setSpacing(1)
        rows.addStretch(1)
        scroll.setWidget(content)
        return scroll,rows

    def set_split_ratio(self, general_ratio: int):
        self._ratio_general=max(15,min(85,int(general_ratio)))
        self._restoring_split=True
        total=max(100,self.splitter.height())
        self.splitter.setSizes([max(20,int(total*(100-self._ratio_general)/100)),
                                max(20,int(total*self._ratio_general/100))])
        self._restoring_split=False

    def _splitter_moved(self, pos, _index):
        if self._restoring_split:return
        sizes=self.splitter.sizes()
        total=sum(sizes)
        if total>0:
            self._ratio_general=max(15,min(85,round(100*sizes[1]/total)))
            self.ratio_changed.emit(self._ratio_general)

    def _make_row(self, nick: str, translated: str, record: dict | None=None) -> QLabel:
        record=record or {}
        row=QLabel()
        row.setObjectName('chatRow')
        row.setTextFormat(Qt.TextFormat.RichText)
        row.setWordWrap(True)
        row.setMinimumWidth(0)
        row.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        row.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        row.setMargin(0)
        row.setContentsMargins(0,2,0,3)  # keep Korean descenders visible
        row.setFont(QFont(self._family,self._size_pt))
        safe_family=html.escape(self._family,quote=True)
        prefix=str(record.get('prefix',''))
        if prefix:
            nick=prefix+' '+nick
        is_announcement = record.get('kind','normal') not in ('normal', '')
        # The captured pixel is ALREADY a composited Maple colour. Use high
        # opacity rather than darkening it to the old fixed 28%.
        source_colors=getattr(self,'_source_colors',True)
        band=str(record.get('band_color',''))
        if is_announcement and not re.fullmatch(r'#[0-9a-fA-F]{6}',band):
            # R18: the tone was recognised but its pixel colour was not kept
            # (a yellow [아확] row drew no band): use that tone's usual band.
            band=TONE_BANDS.get(str(record.get('tone','')),'#d9dee4')
        background=qt_rgba_color(band,100 if source_colors else self._band_opacity) if is_announcement and re.fullmatch(r'#[0-9a-fA-F]{6}',band) else 'transparent'
        # R19: general chat lines are told apart by a faint line under each
        # one (on the white list) or a nearly clear black box (over the game)
        separator=''
        if not is_announcement:
            if getattr(self,'_skin',None):
                separator='border-bottom:1px solid rgba(0,0,0,30);'
            elif background=='transparent':
                background='rgba(0,0,0,38)'
        row.setStyleSheet(f'QLabel#chatRow{{background-color:{background};padding:1px {6 if getattr(self,"_skin",None) else 4}px;'
                          f'border-radius:{0 if source_colors and is_announcement else radius_px(self.theme_variant)//2}px;border:0;'
                          f'{separator}font-size:{self._size_pt}pt;}}')
        # Explicit family on BOTH spans: Qt rich text does not always inherit
        # a registered Noonnu font from QLabel.setFont().
        font_css=f'font-family:&quot;{safe_family}&quot;;font-size:{self._size_pt}pt;'
        nickname_style='megaphone_nickname' if is_announcement else 'nickname'
        message_style='megaphone_message' if is_announcement else 'message'
        # The general feed must NEVER take foreground colors from the game
        # pixels: an alpha-composited background often produces dark text.
        # For megaphones, explicit user-selected colors override source colors.
        body_css=text_css(self._style,message_style)
        source_color=str(record.get('text_color',''))
        body_color=effective_font_color(self._style,message_style,source_colors,source_color)
        nick_css=text_css(self._style,nickname_style)
        nickname_color=str(record.get('nickname_color',''))
        nick_color=effective_font_color(self._style,nickname_style,source_colors,nickname_color)
        if getattr(self,'_skin',None) and not is_announcement:
            # black text on the game window's white list, as in the game
            body_color=nick_color='#000000'
        # What the text is actually drawn on: the megaphone band, or - when
        # the band was not recognised - the window's white list (R18: white
        # '[확성] nickname' vanished on white).
        under=(band if is_announcement and re.fullmatch(r'#[0-9a-fA-F]{6}',band)
               else '#ffffff' if getattr(self,'_skin',None) else '')
        if under:
            # R17: a missed [item] link left the pale item colour as the text
            # colour (#ffffb1 on a yellow band): keep every colour readable.
            body_color=readable_on(body_color,under)
            nick_color=readable_on(nick_color,under)
        body_css += ';color:'+body_color+';'
        nick_css += ';color:'+nick_color+';'
        item_color=(str(record.get('item_color','')) if source_colors and is_announcement
                    and self._style['megaphone_message_color'] == '#ffffff' else '')
        if under and item_color:
            item_color=readable_on(item_color,under)
        row.setText(f'<span style="{font_css}{nick_css}">{html.escape(nick)}</span>'
                    f'<span style="{font_css}{body_css}"> : '
                    f'{colored_item_html(translated,item_color,body_color)}</span>')
        row._chat_record=record
        row._chat_head_len=len(nick)+3
        return row

    # ---------------------------------------------------- R19 item tooltip
    def _item_tip(self):
        tip=getattr(self,'_tip_widget',None)
        if tip is None:
            from .item_tooltip import ItemToolTip
            tip=self._tip_widget=ItemToolTip()
        return tip

    def _hide_item_tip(self, feed=None):
        tip=getattr(self,'_tip_widget',None)
        if tip is not None and tip.isVisible():
            tip.hide_item()
        if feed is not None:
            feed.viewport().unsetCursor()

    def _item_hover(self, feed, event):
        """Show the game's item tooltip while the mouse is on an [item]."""
        try:
            content=feed.widget()
            pos=event.position().toPoint()
            child=content.childAt(content.mapFrom(feed.viewport(),pos)) if content else None
            while child is not None and child is not content and child.objectName()!='chatRow':
                child=child.parentWidget()
            if child is None or child is content:
                self._hide_item_tip(feed)
                return
            from .item_tooltip import label_at
            hit=label_at(child,child.mapFrom(feed.viewport(),pos),getattr(child,'_chat_head_len',0))
            if not hit:
                self._hide_item_tip(feed)
                return
            label,index=hit
            record=getattr(child,'_chat_record',None) or {}
            original=str(record.get('original','') or '')
            from .item_info import current_db
            info=current_db().lookup(label,original,index)
            if info is None:
                self._hide_item_tip(feed)
                return
            from .item_options import options_for_label
            options=options_for_label(original,index) if info.is_equip and not info.cash else {}
            feed.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            self._item_tip().show_item(info,label,options,event.globalPosition().toPoint())
        except Exception as exc:   # a tooltip must never break the chat
            LOG.debug('item tooltip failed: %s', exc)
            self._hide_item_tip(feed)

    def hideEvent(self, event):
        self._hide_item_tip()
        super().hideEvent(event)

    def _clear_rows(self, rows):
        while rows.count()>1:
            item=rows.takeAt(1)
            widget=item.widget()
            if widget is not None:
                widget.hide();widget.deleteLater()

    def _schedule_latest(self):
        if self._scroll_pending:
            return
        self._scroll_pending = True
        QTimer.singleShot(0,self._scroll_to_latest)
        QTimer.singleShot(65,self._scroll_to_latest)

    def _render_messages(self):
        # Full rebuild is reserved for an explicit style/font change. Suspend
        # painting while replacing rows to avoid the flash of an empty feed.
        self.splitter.setUpdatesEnabled(False)
        try:
            self._clear_rows(self.general_rows)
            self._clear_rows(self.mega_rows)
            self._live_rows.clear()
            for record in self._records[-95:]:
                rows=self.mega_rows if record.get('kind','normal')!='normal' else self.general_rows
                widget=self._make_row(record['nickname'],record['translated'],record)
                rows.addWidget(widget)
                self._live_rows.append((widget,rows))
        finally:
            self.splitter.setUpdatesEnabled(True)
        self._schedule_latest()

    def _scroll_to_latest(self):
        self._scroll_pending = False
        for feed in (self.general_feed,self.mega_feed):
            feed.widget().layout().activate()
            feed.widget().adjustSize()
            # Do not pull the reader to the latest message while browsing
            # older lines. Each (normal/megaphone) pane follows separately.
            if self._auto_follow.get(feed, True):
                bar=feed.verticalScrollBar()
                bar.setValue(bar.maximum())

    def restore_history(self):
        if self.history_store is None:return
        self._records=self.history_store.recent(95)
        for record in self._records:
            # Convert persisted wall time to this process' monotonic origin.
            record['order']=(time.monotonic()+record['captured_unix']-time.time(),0)
        self._messages=[(r['nickname'],r['translated']) for r in self._records]
        self._render_messages()

    def clear_history_display(self):
        self._records.clear();self._messages.clear();self._render_messages()

    def put(self, message: dict):
        if not message.get('fresh',True):return
        nick=str(message.get('nickname','')).strip()
        translated=str(message.get('translated','')).strip()
        if not nick or not translated:return
        record={'nickname':nick,'translated':translated,
                **{k:str(message.get(k,'')) for k in ('kind','prefix','tone','band_color','text_color','nickname_color','item_color')}}
        if record['kind'] not in ('normal','unknown','super','item','double_item'):
            record['kind']='normal'
        self._row_sequence += 1
        record['id'] = message.get('message_id') or self._row_sequence
        record['order'] = tuple(message.get('order') or (time.monotonic(), self._row_sequence))
        record['original']=str(message.get('original',''))
        record['captured_unix']=float(message.get('captured_unix') or time.time())
        record['visual_event_id']=message.get('visual_event_id')
        record['visual_session']=message.get('visual_session','')
        record['source_ink']=message.get('source_ink','')
        record['source_local_rect']=message.get('source_local_rect')
        if any(old.get('id') == record['id'] for old in self._records):
            return
        event=record.get('visual_event_id')
        if event is not None and any(old.get('visual_session')==record['visual_session'] and old.get('visual_event_id') is not None and tuple(old['visual_event_id'])==tuple(event) for old in self._records):return
        if self.history_store is not None and message.get('persist',True):
            try:
                if message.get('startup_visible') and self.history_store.contains_startup_pixels(record):return
                if not self.history_store.append(record):return
            except Exception as exc:
                LOG.exception('Could not save translation history')
                self.history_error.emit('번역 내역 저장 실패: '+str(exc)[:100])
        # A cheap shorthand may finish before an older neural translation.
        # Insert by capture order, keeping the displayed history chronological.
        position = next((i for i, old in enumerate(self._records)
                         if tuple(old.get('order', (0, 0))) > record['order']), len(self._records))
        if position == len(self._records):
            self._records.append(record)
        else:
            self._records.insert(position,record)
        rows=self.mega_rows if record.get('kind','normal')!='normal' else self.general_rows
        pane_position=1+sum((r.get('kind','normal')!='normal') == (record.get('kind','normal')!='normal')
                            for r in self._records[:position])
        widget=self._make_row(nick,translated,record)
        rows.insertWidget(pane_position,widget)
        if position == len(self._live_rows):
            self._live_rows.append((widget,rows))
        else:
            self._live_rows.insert(position,(widget,rows))
        if len(self._live_rows)>95:
            self._records.pop(0)
            stale,old_rows=self._live_rows.pop(0)
            old_rows.removeWidget(stale)
            stale.hide();stale.deleteLater()
        self._messages=[(r['nickname'],r['translated']) for r in self._records]
        self._schedule_latest()

    def set_mode(self, value: str):
        if value not in ('overlay','dock-left','dock-right','free'):
            return
        self.mode = value
        self._apply_flags()

    def set_editable(self, edit: bool):
        self.editing = bool(edit)
        self._apply_flags()

    def set_scroll_interactive(self, enabled: bool):
        # Qt.WindowTransparentForInput rejects even wheel messages at the OS
        # level. This opt-in removes click-through without changing geometry.
        enabled = bool(enabled)
        if self.scroll_interactive != enabled:
            self._feed_drag = None
            self.scroll_interactive = enabled
            self._apply_flags()

    def set_top_mode(self, value: str):
        if value not in Z_ORDER_MODES:
            raise ValueError(value)
        if value == self.top_mode:
            return
        self.top_mode = value
        self._apply_flags()
        if self.isVisible():
            enable_obs_window_capture(self)
        if value != 'always':
            set_native_stack(int(self.winId()), 'normal')

    def _apply_flags(self):
        # Input-transparent windows cannot be dragged/resized. Temporarily
        # disable click-through when user requests editing, even for overlay/dock.
        # Docked beside the game the window never covers the game, so its
        # scroll buttons/thumb take clicks. Over the game it stays click-through.
        passthrough = (not self.editing and not self.scroll_interactive
                       and self.mode not in ('free','dock-left','dock-right'))
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if self.top_mode == 'always':
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if passthrough:
            flags |= Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus
        showing = self.isVisible()
        old = self.geometry()
        self.hide()
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, passthrough)
        self.setGeometry(old)
        self.edit_tip.setVisible(self.editing)
        self.grip.setVisible(self.editing or self.mode == 'free')
        if showing:
            self.show()
            enable_obs_window_capture(self)
        self.grip.raise_()
        self._position_grip()

    def _position_grip(self):
        self.grip.move(max(0,self.width()-self.grip.width()-2),
                       max(0,self.height()-self.grip.height()-2))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_skin()
        self._position_grip()
        if self._allow_resize_signal and (self.editing or self.mode=='free'):
            self.geometry_edited.emit()

    def eventFilter(self, watched, event):
        feed = self._feeds_by_viewport.get(watched)
        if feed is not None:
            kind = event.type()
            if kind == QEvent.Type.MouseMove and self._feed_drag is None:
                self._item_hover(feed, event)
            elif kind in (QEvent.Type.Leave, QEvent.Type.Wheel, QEvent.Type.MouseButtonPress, QEvent.Type.Hide):
                self._hide_item_tip(feed)
        if feed is not None and event.type() == QEvent.Type.Wheel:
            # Hidden scrollbars still accept programmatic scrolling. A pixel
            # delta covers touchpad wheels; angle delta covers physical mice.
            bar = feed.verticalScrollBar()
            pixels = event.pixelDelta().y()
            angle = event.angleDelta().y()
            if pixels or angle:
                distance = pixels if pixels else (angle / 120.0) * max(24, bar.singleStep() * 3)
                bar.setValue(round(bar.value() - distance))
                self._auto_follow[feed] = (bar.value() >= bar.maximum() - 2)
                event.accept()
                return True
        # Left-button vertical drag scrolls chat history.  Overlay/dock mode
        # stays click-through during gameplay unless scroll mode is enabled.
        if feed is not None:
            kind = event.type()
            can_drag = self.scroll_interactive or self.mode == 'free' or self.editing
            if (kind == QEvent.Type.MouseButtonPress and can_drag
                    and event.button() == Qt.MouseButton.LeftButton):
                bar = feed.verticalScrollBar()
                self._feed_drag = (feed, event.position().y(), bar.value())
                event.accept()
                return True
            if kind == QEvent.Type.MouseMove and self._feed_drag is not None:
                dragging_feed, start_y, start_scroll = self._feed_drag
                if dragging_feed is feed:
                    bar = feed.verticalScrollBar()
                    bar.setValue(round(start_scroll - (event.position().y() - start_y)))
                    self._auto_follow[feed] = (bar.value() >= bar.maximum() - 2)
                    event.accept()
                    return True
            if kind == QEvent.Type.MouseButtonRelease and self._feed_drag is not None:
                dragging_feed, _, _ = self._feed_drag
                if dragging_feed is feed:
                    self._feed_drag = None
                    event.accept()
                    return True
        if watched is self.card and self._skin and self._scroll_event(event):
            return True
        if watched is self.card and (self.editing or self.mode == 'free'):
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_origin = event.globalPosition().toPoint() - self.pos()
                return True
            if kind == QEvent.Type.MouseMove and self._drag_origin is not None:
                self.move(event.globalPosition().toPoint() - self._drag_origin)
                return True
            if kind == QEvent.Type.MouseButtonRelease and self._drag_origin is not None:
                self._drag_origin = None
                self.geometry_edited.emit()
                return True
        return super().eventFilter(watched,event)


def hud_panel_cap() -> int:
    """Tallest side panel: 126 px at 1920x1080, more for a larger game UI."""
    return max(126, round(126 * CU.SCALE[1] / (1080 / 768)))


def _paint_hud(widget):
    """Bottom HUD panels: the game's own status-bar texture behind the controls."""
    from PySide6.QtGui import QPainter
    p=QPainter(widget)
    p.drawPixmap(0,0,CU.hud_pixmap(widget.width(),widget.height()))
    p.end()


class CompactSettings(Glass):
    PANEL_TITLE = '글클메 애드온'
    PANEL_SUB = '제작자 KAIN'
    STRIP_PX = 30      # the status line sits on the steel strip (at 1920x1080)

    def strip_px(self) -> int:
        """The strip's height at the game's current UI scale."""
        return max(22, round(self.STRIP_PX * CU.SCALE[1] / (1080 / 768)))

    def mousePressEvent(self, event):
        # R18: the title band's X quits, like the old × button did
        if getattr(self,'_hud_compact',False) and event.button()==Qt.MouseButton.LeftButton:
            x,y,w,h=CU.panel_close_rect(self.width(),self.height())
            pos=event.position().toPoint()
            if x-3<=pos.x()<=x+w+3 and y-3<=pos.y()<=y+h+3:
                self.quit.emit()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        if getattr(self,'_hud_compact',False):
            # R18: a real game window like the EXP meter: title band + strip
            from PySide6.QtGui import QPainter
            p=QPainter(self)
            p.drawPixmap(0,0,CU.panel_pixmap(self.width(),self.height(),self.PANEL_TITLE,
                                              self.PANEL_SUB,self.strip_px()-4))
            p.end()
            return
        _paint_hud(self)

    def set_theme_variant(self, variant: str):
        # v0.4.41: edge-to-edge Maple HUD needs square BUTTONS and INPUTS,
        # not just a square outer frame. Keep full-size/fallback theme configurable.
        self._requested_theme_variant=normalize_variant(variant)
        super().set_theme_variant('square' if getattr(self,'_hud_compact',False)
                                  else self._requested_theme_variant)


    toggle = Signal()
    choose = Signal()
    mode_changed = Signal(str)
    edit_changed = Signal(bool)
    scroll_mode_changed = Signal(bool)
    details = Signal()
    test_translation = Signal()
    test_ocr = Signal()
    test_display = Signal()
    obs_copy = Signal()
    hunt_show = Signal()
    price_show = Signal()
    quit = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(360, 126)
        self._hud_compact=False
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)
        self.brand=CU.ClassicText('글클메 애드온 R20')
        self.brand.setObjectName('brand')
        lay.addWidget(self.brand)
        self.description=CU.ClassicText('제작자 KAIN  ·  실시간 게임 채팅 번역')
        self.description.setObjectName('eyebrow')
        lay.addWidget(self.description)
        a=QHBoxLayout()
        self.toggle_btn=CU.ClassicButton('● 번역 OFF · R20')
        self.toggle_btn.setProperty('classic','pink')  # ON turns lime
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self.toggle)
        a.addWidget(self.toggle_btn,1)
        prefs=CU.ClassicButton('≡')  # Gulim has no ⚙ glyph
        prefs.setProperty('classic','blue')
        prefs.setFixedWidth(29)
        self.prefs_btn=prefs
        prefs.setToolTip('번역 엔진·폰트·글자 크기·투명도')
        prefs.clicked.connect(self.details)
        a.addWidget(prefs)
        close=CU.ClassicButton('×')
        close.setProperty('classic','close')   # the game's blue X (BtClose)
        close.setFixedWidth(25)
        close.clicked.connect(self.quit)
        a.addWidget(close)
        self.close_btn=close
        lay.addLayout(a)
        b=QHBoxLayout()
        btn=CU.ClassicButton('인식 영역')
        btn.setProperty('classic','pink')
        btn.clicked.connect(self.choose)
        b.addWidget(btn)
        self.mode=CU.ClassicCombo()
        self.mode.setMaxVisibleItems(8)
        self.mode.setToolTip('클릭해서 번역창 배치 방식을 선택하세요.')
        self.mode.addItem('채팅 위 덮기','overlay')
        self.mode.addItem('오른쪽 자석','dock-right')
        self.mode.addItem('왼쪽 자석','dock-left')
        self.mode.addItem('자유 플로팅','free')
        self.mode.currentIndexChanged.connect(lambda _: self.mode_changed.emit(self.mode.currentData()))
        b.addWidget(self.mode,1)
        self.scroll_button=CU.ClassicButton('휠 OFF')
        self.scroll_button.setProperty('classic','blue')
        self.scroll_button.setCheckable(True)
        self.scroll_button.setFixedWidth(62)  # fits Gulim "휠 OFF"
        self.scroll_button.setToolTip('클릭하면 마우스 휠 또는 왼쪽 버튼 상하 드래그로 지난 채팅을 볼 수 있습니다.\n'
                                      'ON 중에는 게임창 클릭 투과가 일시적으로 꺼집니다.')
        self.scroll_button.toggled.connect(self._scroll_toggled)
        b.addWidget(self.scroll_button)
        lay.addLayout(b)
        c=QHBoxLayout()
        c.setContentsMargins(0,0,0,0)
        c.setSpacing(1)
        self.edit=CU.ClassicButton('위치·크기 이동')
        self.edit.setProperty('classic','blue')
        self.edit.setCheckable(True)
        self.edit.toggled.connect(self.edit_changed)
        c.addWidget(self.edit,1)
        self.tester=CU.ClassicButton('오프라인 번역 시험')
        self.tester.setProperty('classic','lime')
        tester=self.tester
        tester.setToolTip('포함된 EN↔KO 모델을 실제 실행해 검증합니다. 인터넷 불필요')
        tester.clicked.connect(self.test_translation)
        c.addWidget(tester)
        self.ocr_button=CU.ClassicButton('OCR 진단')
        self.ocr_button.setProperty('classic','pink')
        ocr=self.ocr_button
        ocr.clicked.connect(self.test_ocr)
        c.addWidget(ocr)
        self.display_button=CU.ClassicButton('표시 시험')
        self.display_button.setProperty('classic','blue')
        display=self.display_button
        display.clicked.connect(self.test_display)
        c.addWidget(display)
        # Short OBS button in the button row; the wide row opens the EXP meter.
        self.obs_button=CU.ClassicButton('OBS')
        self.obs_button.setProperty('classic','orange')  # accent, like the WORLD button
        self.obs_button.setToolTip('OBS 브라우저 소스에 추가할 로컬 주소 복사')
        self.obs_button.clicked.connect(self.obs_copy)
        c.addWidget(self.obs_button)
        lay.addLayout(c)
        obsrow=QHBoxLayout()
        self.hunt_button=CU.ClassicButton('경험치 측정기')
        self.hunt_button.setProperty('classic','lime')
        self.hunt_button.setToolTip('이동 가능한 사냥 시간·EXP·단축키 물약 추적 위젯')
        self.hunt_button.clicked.connect(self.hunt_show)
        obsrow.addWidget(self.hunt_button,1)
        self.price_button=CU.ClassicButton('시세 보기')
        self.price_button.setProperty('classic','blue')
        self.price_button.setToolTip('자유시장 시세 기록 · 아이템 검색 (확성기·채팅 거래 글에서 자동 수집)')
        self.price_button.clicked.connect(self.price_show)
        obsrow.addWidget(self.price_button,1)
        lay.addLayout(obsrow)
        self.status=CU.ClassicText('인식 영역을 먼저 지정하세요')
        self.status.setObjectName('subtle')
        self.status.setMinimumHeight(18)
        lay.addWidget(self.status)

    def _scroll_toggled(self, enabled: bool):
        self.scroll_button.setText('휠 ON' if enabled else '휠 OFF')
        self.scroll_mode_changed.emit(enabled)

    def fit_bottom_hud(self, width: int, height: int):
        """Compact all control actions to Maple's bottom control-bar height."""
        height=max(95,int(height))
        width=max(155,int(width))
        compact=height<=210
        if compact: height=min(height,hud_panel_cap())
        if (self.width(),self.height(),self._hud_compact)==(width,height,compact):
            return
        self._hud_compact=compact
        self.set_theme_variant(getattr(self,'_requested_theme_variant',self.theme_variant))
        # Fixed button widths were set for the 1920x1080 UI scale.
        k=CU.SCALE[0]/(1920/1366)
        self.prefs_btn.setFixedWidth(max(22,round(29*k)))
        self.close_btn.setFixedWidth(max(20,round(25*k)))
        self.scroll_button.setFixedWidth(max(46,round(62*k)))
        self.brand.setVisible(not compact)
        self.description.setVisible(not compact)
        self.close_btn.setVisible(not compact)
        if compact:
            title=CU.panel_title_px()
            height+=title
            self.card.layout().setContentsMargins(5,title+2,5,0)
            self.status.setObjectName('strip')
            self.status.strip_px=self.strip_px()-4     # the strip paintEvent draws
        else:
            self.card.layout().setContentsMargins(8,6,8,6)
            self.status.setObjectName('subtle')
            self.status.strip_px=None
        self.card.layout().setSpacing(1 if compact else 6)
        self.edit.setText('이동' if compact else '위치·크기 이동')
        self.tester.setText('번역' if compact else '오프라인 번역 시험')
        self.ocr_button.setText('OCR' if compact else 'OCR 진단')
        self.display_button.setText('표시' if compact else '표시 시험')
        self.hunt_button.setText('경험치 측정기')
        self.obs_button.setText('OBS' if compact else 'OBS 주소 복사')
        # Avoid Qt's font-dependent minimum sizes clipping a short HUD.
        narrow=compact and width<225
        # The wide EXP-meter row always stays; a short HUD drops the status line.
        self.status.setVisible(not (compact and height<115))
        if narrow:
            for btn,name in ((self.edit,'위'),(self.tester,'번'),(self.ocr_button,'O'),
                             (self.display_button,'표'),(self.obs_button,'B')):
                btn.setText(name)
                btn.setMinimumWidth(0)
                btn.setMaximumWidth(max(26,(width-12)//5))
                btn.setStyleSheet('font-size:10px;padding:0px;border-radius:0px;')
        else:
            self.edit.setText('이동' if compact else '위치·크기 이동')
            self.tester.setText('번역' if compact else '오프라인 번역 시험')
            self.ocr_button.setText('OCR' if compact else 'OCR 진단')
            self.display_button.setText('표시' if compact else '표시 시험')
            self.obs_button.setText('OBS' if compact else 'OBS 주소 복사')
        for widget in (self.toggle_btn,self.edit,self.tester,self.ocr_button,
                       self.display_button,self.hunt_button,self.price_button,self.obs_button):
            widget.setMinimumHeight(0)
            widget.setMaximumHeight(26 if compact else 16777215)
        if compact:
            self.status.setMaximumHeight(self.strip_px())
            self.status.setMinimumHeight(self.strip_px())
        # Merge visually with the game's central HUD instead of showing an
        # inset, rounded floating-card frame surrounded by empty gutters.
        self.card.setStyleSheet(strip_stylesheet('left'))
        self.setFixedSize(width,height)

    def update_live(self, running: bool):
        self.toggle_btn.blockSignals(True)
        self.toggle_btn.setChecked(running)
        self.toggle_btn.setText('● 번역 ON · R20' if running else '● 번역 OFF · R20')
        self.toggle_btn.blockSignals(False)

    def set_status(self, value: str):
        # Worker and layout poll frequently; identical QLabel updates cause
        # needless repaints in a translucent overlay on some GPUs.
        if self.status.text() != value[:42]:
            self.status.setText(value[:42])
        if self.status.toolTip() != value:
            self.status.setToolTip(value)


class ComposeSignals(QObject):
    done = Signal(int,str,str)


class FontSignals(QObject):
    done = Signal(str,str,str)


class CompactComposer(Glass):
    # Title band like the game's CHARACTER STAT window: the title and the
    # state in the game's own pixel font (the Korean wording is the tooltip).
    STATE_WORDS={'입력 대기':'READY','번역 중':'TRANSLATING','복사됨':'COPIED','번역 오류':'ERROR'}

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter
        state=next((v for k,v in self.STATE_WORDS.items() if k in self.status.text()),'READY')
        p=QPainter(self)
        p.drawPixmap(0,0,CU.titled_pixmap(self.width(),self.height(),'KO > EN',state))
        p.end()

    def set_theme_variant(self, variant: str):
        # v0.4.41: edge-to-edge Maple HUD needs square BUTTONS and INPUTS,
        # not just a square outer frame. Keep full-size/fallback theme configurable.
        self._requested_theme_variant=normalize_variant(variant)
        super().set_theme_variant('square' if getattr(self,'_hud_compact',False)
                                  else self._requested_theme_variant)


    translate_clicked=Signal(str)
    def __init__(self):
        super().__init__()
        self.setFixedSize(326,150)
        self._hud_compact=False
        lay=QVBoxLayout(self.card)
        lay.setContentsMargins(8,6,8,6)
        lay.setSpacing(3)
        # heading/status keep their text for the code and tests; the panel's
        # own title band (paintEvent) is what shows them.
        self.heading=CU.TrackedLabel('글클메 애드온 · 영어 입력기',self)
        self.heading.setObjectName('sectionTitle')
        self.heading.hide()
        self.status=CU.TrackedLabel('입력 대기',self)
        self.status.setObjectName('subtle')
        self.status.hide()
        self.setToolTip('한국어 → 영어 입력기')
        row=QHBoxLayout()
        self.input=QLineEdit()
        self.input.setPlaceholderText('한국어 채팅 입력')
        self.input.returnPressed.connect(self.translate)
        row.addWidget(self.input,1)
        self.button=CU.ClassicButton('영어 변환')
        self.button.setProperty('classic','orange')
        self.button.clicked.connect(self.translate)
        row.addWidget(self.button)
        lay.addLayout(row)
        resultrow=QHBoxLayout()
        self.result=QLineEdit()
        self.result.setReadOnly(True)
        self.result.setPlaceholderText('영어 결과 · 번역 후 자동 복사')
        resultrow.addWidget(self.result,1)
        self.copy=CU.ClassicButton('복사')
        self.copy.setFixedWidth(42)
        self.copy.clicked.connect(self.copy_result)
        resultrow.addWidget(self.copy)
        lay.addLayout(resultrow)

    def fit_bottom_hud(self, width: int, height: int):
        """Keep Korean input and translated result at the same HUD top/bottom."""
        width=max(155,int(width));height=max(95,int(height))
        compact=height<=210
        if compact: height=min(height,hud_panel_cap())
        if (self.width(),self.height(),self._hud_compact)==(width,height,compact):
            return
        self._hud_compact=compact
        self.set_theme_variant(getattr(self,'_requested_theme_variant',self.theme_variant))
        self.heading.setText('한→영' if compact else '글클메 애드온 · 영어 입력기')
        # below the title band (20 native px of the stat window's top)
        top=round(21*CU.SCALE[1])
        self.copy.setFixedWidth(max(32,round(42*CU.SCALE[0]/(1920/1366))))
        self.card.layout().setContentsMargins(6, top, 6, 4)
        self.card.layout().setSpacing(2)
        # Fill the panel height with real controls, not blank black pixels.
        row_height=max(22,min(36,(height-top-10)//2)) if compact else 27
        for field in (self.input,self.result,self.button,self.copy):
            field.setMinimumHeight(row_height)
        self.card.setStyleSheet(strip_stylesheet('right'))
        self.setFixedSize(width,height)

    def translate(self):
        text=self.input.text().strip()
        if text:
            self.translate_clicked.emit(text)

    def copy_result(self):
        text=self.result.text().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText('복사됨')

    def busy(self):
        self.status.setText('번역 중…')
        self.button.setEnabled(False)

    def finish(self, value: str, error: str):
        self.button.setEnabled(True)
        if error:
            self.status.setText('번역 오류')
            self.result.setText('')
            self.result.setPlaceholderText('번역 실패 · 로컬 모델 설치 상태 확인')
        else:
            self.result.setText(value)
            QApplication.clipboard().setText(value)
            self.status.setText('복사됨')


class SettingsDialog(QDialog):
    font_url_requested = Signal(str)
    history_requested = Signal()
    price_log_requested = Signal()
    help_requested = Signal()
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle('글클메 애드온 · 설정')
        self._color_picker_open = False
        self._color_picker = None
        self.resize(570, 760)
        self.setMinimumSize(470,520)
        self.setStyleSheet(settings_stylesheet(cfg.get('theme_variant','rounded')))
        # No Windows title bar: the game's own title band (like CHARACTER STAT).
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)  # rounded corners
        shell=QVBoxLayout(self)
        shell.setContentsMargins(0,0,0,0)
        shell.setSpacing(0)
        shell.addWidget(CU.ClassicTitleBar('SETTINGS',self))
        body=QWidget(self)
        shell.addWidget(body,1)
        outer=QVBoxLayout(body)
        outer.setContentsMargins(7,6,7,7)   # tabs right under the title band
        outer.setSpacing(12)
        masthead=QLabel('글클메 애드온')
        masthead.setObjectName('brand')
        masthead.hide()  # the title band names the window, like MAPLE USER LIST
        strap=QLabel('제작자 KAIN   •   방송에 최적화된 게임 채팅 번역')
        strap.setObjectName('eyebrow')
        strap.hide()
        self.setToolTip('제작자 KAIN  ·  방송에 최적화된 게임 채팅 번역')
        tabs=QTabWidget(self)
        tabs.setObjectName('mainSettingsTabs')
        tabs.setTabBar(CU.ClassicTabBar())          # inventory-style tabs
        tabs.tabBar().setMouseTracking(True)
        tabs.setStyleSheet(f'QTabWidget::pane{{border:1px solid {T.FRAME};border-top:2px solid #d92f58;background:{T.BODY};top:-1px;}}')
        def make_tab(name):
            scroll=QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            # light stat-window body behind every settings page (not the
            # Windows dark-mode default)
            scroll.viewport().setObjectName('settingsViewport')
            scroll.viewport().setStyleSheet(f'QWidget#settingsViewport{{background:{T.BODY};}}')
            content=QWidget()
            content.setObjectName('settingsPage')
            content.setStyleSheet(f'QWidget#settingsPage{{background:{T.BODY};}}')
            content.setMinimumWidth(0)
            content.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
            layout=QVBoxLayout(content)
            layout.setContentsMargins(18,17,18,18)
            layout.setSpacing(11)
            scroll.setWidget(content)
            tabs.addTab(scroll,name)
            return layout
        general_layout=make_tab('게임 · 번역')
        appearance_layout=make_tab('채팅 디자인')
        capture_layout=make_tab('자석 · OCR')
        alerts_layout=make_tab('알림 · 시세')
        outer.addWidget(tabs,1)
        # R18: chat keyword alerts and the Free Market price log
        from PySide6.QtWidgets import QPlainTextEdit
        alerts_layout.addWidget(self._section('KEYWORD ALERT  /  채팅 키워드 알림'))
        alerts_layout.addWidget(QLabel('한 줄에 하나씩 적어 주세요. 확성기·채팅의 원문이나 번역에 나오면 알려 줍니다.'))
        alerts_layout.addWidget(QLabel('예) 노가다 목장갑 / 일비 / KPQ / 내 닉네임'))
        self.alert_words=QPlainTextEdit('\n'.join(cfg.get('alert_keywords',[])))
        self.alert_words.setObjectName('alertWords')
        self.alert_words.setFixedHeight(120)
        alerts_layout.addWidget(self.alert_words)
        self.alert_popup=QCheckBox('알림 창 띄우기 (KEYWORD ALERT)')
        self.alert_popup.setChecked(bool(cfg.get('alert_popup',True)))
        self.alert_sound=QCheckBox('알림 소리')
        self.alert_sound.setChecked(bool(cfg.get('alert_sound',True)))
        alerts_layout.addWidget(self.alert_popup)
        alerts_layout.addWidget(self.alert_sound)
        alerts_layout.addWidget(self._section('PRICE LOG  /  자유시장 시세 기록'))
        alerts_layout.addWidget(QLabel('S>/B> 거래 글의 아이템과 가격을 자동으로 모아 최근 7일 가격 범위를 보여 줍니다.'))
        self.price_enabled=QCheckBox('거래 글 가격 기록하기')
        self.price_enabled.setChecked(bool(cfg.get('price_log_enabled',True)))
        alerts_layout.addWidget(self.price_enabled)
        price_button=QPushButton('시세 기록 보기 · 아이템 검색')
        price_button.clicked.connect(self.price_log_requested.emit)
        alerts_layout.addWidget(price_button)
        alerts_layout.addStretch(1)
        lay=general_layout
        lay.addWidget(self._section('HOW TO USE  /  기능 · 사용법'))
        help_button=QPushButton('사용법 · 기능 안내 보기')
        help_button.setObjectName('primary')   # lime, like ADD
        help_button.clicked.connect(self.help_requested.emit)
        lay.addWidget(help_button)
        lay.addWidget(self._section('TRANSLATION  /  번역 엔진'))
        lay.addWidget(QLabel('Argos Translate · 로컬 오프라인 AI (API 키/글자 수 제한 없음)'))
        lay.addWidget(QLabel('EN↔KO 모델 2개는 Windows 빌드에 포함됩니다.'))
        history_button=QPushButton('번역 내역 보기 · 검색 / 전체 지우기')
        history_button.clicked.connect(self.history_requested.emit)
        lay.addWidget(history_button)
        lay.addWidget(QLabel('번역 내역은 직접 지우기 전까지 재시작 후에도 보관됩니다.'))
        lay.addWidget(self._section('ITEMS  /  허가받은 아이템 사전'))
        lay.addWidget(QLabel('허가받은 영어명·한국어명 CSV/JSON 파일을 불러와 아이템 번역에 우선 적용합니다.'))
        self.catalog_status=QLabel(f'직접 등록한 한글 아이템명: {current_catalog().count:,}개')
        lay.addWidget(self.catalog_status)
        from .classic_item_index import index_state
        lay.addWidget(QLabel('공개 구버전 ID 색인: '+index_state()))
        from .open_classic_data import status_text
        lay.addWidget(QLabel('Classic Maple Wiki 공개 DB: '+(status_text() or '미설치 (빌드 시 내려받기)')))
        lay.addWidget(QLabel('CC BY-NC-SA 4.0 · 비상업적 이용 전용 / 출처: classicmaple.wiki'))
        lay.addWidget(QLabel('공개 DB의 영어 이름은 거래 채팅에서 인식해 로컬 AI로 보조 번역합니다.'))
        lay.addWidget(QLabel('AI가 추정한 한글명은 공식 명칭이 아니며, 직접 등록한 이름이 항상 우선합니다.'))
        catalog_button=QPushButton('아이템 DB 파일 가져오기 (CSV/JSON)')
        catalog_button.clicked.connect(self.import_item_catalog)
        lay.addWidget(catalog_button)
        lay.addWidget(QLabel('전체 NiaMeowDB 데이터 복제·재배포는 운영자 허가가 필요합니다.'))
        self.engine=QComboBox()
        self.engine.addItem('오프라인 AI (CTranslate2)', 'argos')
        lay.addWidget(self.engine)
        lay.addWidget(QLabel('메이플 게임 해상도 · 자동 배치 기준'))
        self.resolution=QComboBox()
        self.resolution.addItem('자동 감지 (권장)', 'auto')
        for dimension in GAME_RESOLUTIONS[1:]:
            self.resolution.addItem(dimension, dimension)
        self.resolution.setCurrentIndex(max(0, self.resolution.findData(cfg.get('game_resolution','auto'))))
        lay.addWidget(self.resolution)
        lay.addWidget(self._section('CAPTURE  /  채팅 화면 획득'))
        lay.addWidget(QLabel('캡처 엔진 · Windows 창 캡처가 실패하면 기존 MSS로 자동 복구합니다.'))
        self.capture_backend=QComboBox()
        self.capture_backend.addItem('Windows Graphics Capture (게임 창 자동 추적 · 권장)','wgc')
        self.capture_backend.addItem('기존 화면 영역 캡처 (MSS · 호환 모드)','mss')
        self.capture_backend.setCurrentIndex(max(0,self.capture_backend.findData(cfg.get('capture_backend','wgc'))))
        lay.addWidget(self.capture_backend)
        self.auto_chat=QCheckBox('게임 창·채팅창 자동 탐지 (영역 드래그 불필요 · 권장)')
        self.auto_chat.setChecked(bool(cfg.get('auto_chat_region',True)))
        lay.addWidget(self.auto_chat)
        lay.addWidget(QLabel('WGC로 게임 창을 잡고 하단 채팅창을 자동 탐색합니다.\n탐색 실패 시 위치를 추정해 표시하며 수동 영역 지정도 가능합니다.'))
        lay.addWidget(QLabel('게임 창 제목에 포함된 단어 (자석 도킹용)'))
        self.game_title=QLineEdit(cfg.get('game_title_keyword','maple'))
        lay.addWidget(self.game_title)
        lay.addWidget(self._section('WINDOW  /  위치와 표시 순서'))
        lay.addWidget(QLabel('창 위에 표시 방식'))
        self.top_mode=QComboBox()
        self.top_mode.addItem('메이플 위에만 (권장) · 다른 앱은 가리지 않음','game')
        self.top_mode.addItem('항상 위 (다른 프로그램 위에도 표시)','always')
        self.top_mode.addItem('일반 창 · 항상 위 끔','normal')
        self.top_mode.setCurrentIndex(max(0,self.top_mode.findData(cfg.get('top_mode','game'))))
        lay.addWidget(self.top_mode)
        self.pin_settings=QCheckBox('설정창을 메이플 게임 위에 고정 (다른 앱 위에는 표시하지 않음)')
        self.pin_settings.setChecked(bool(cfg.get('pin_settings_above_game',False)))
        lay.addWidget(self.pin_settings)
        lay=appearance_layout
        lay.addWidget(self._section('APPEARANCE  /  채팅 테마'))
        lay.addWidget(QLabel('번역창 테마'))
        self.theme_choice=QComboBox()
        self.theme_choice.addItem('ROUND  /  둥근 버전','rounded')
        self.theme_choice.addItem('EDGE  /  각진 버전','square')
        self.theme_choice.setCurrentIndex(max(0,self.theme_choice.findData(normalize_variant(cfg.get('theme_variant','rounded')))))
        self.theme_choice.currentIndexChanged.connect(self._theme_preview_changed)
        lay.addWidget(self.theme_choice)
        self.source_colors=QCheckBox('게임 원본 배경·닉네임·아이템·본문 색상 유지')
        self.source_colors.setChecked(bool(cfg.get('source_chat_colors',True)))
        self.source_colors.setToolTip("확성기 배경은 원본 색상을 사용합니다. 일반채팅 글씨에는 설정 색상을 적용하며, 확성기 글씨도 사용자 지정 색상이 원본보다 우선합니다.")
        lay.addWidget(self.source_colors)
        self.game_priority=QCheckBox('게임 우선 · 번역 프로그램 CPU 우선순위 낮추기')
        self.game_priority.setChecked(bool(cfg.get('game_priority',False)))
        self.game_priority.setToolTip('게임 CPU 작업을 우선합니다. 번역 대기가 길어질 수 있습니다.')
        lay.addWidget(self.game_priority)
        lay.addWidget(QLabel('번역창 글씨 크기'))
        self.font_size=QSpinBox()
        self.font_size.setRange(8,38)
        self.font_size.setSuffix(' pt')
        self.font_size.setValue(int(cfg.get('font_size',13)))
        lay.addWidget(self.font_size)
        lay.addWidget(QLabel('눈누 폰트 주소 · URL 입력 후 바로 적용'))
        fontrow=QHBoxLayout()
        self.font_path=QLineEdit(cfg.get('font_url',''))
        self.font_path.setPlaceholderText('https://noonnu.cc/font_page/106')
        fontrow.addWidget(self.font_path,1)
        pick=QPushButton('URL 적용')
        pick.clicked.connect(lambda: self.apply_remote_font())
        fontrow.addWidget(pick)
        browse=QPushButton('눈누')
        browse.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://noonnu.cc/')))
        fontrow.addWidget(browse)
        lay.addLayout(fontrow)
        lay.addWidget(QLabel('번역창 불투명도'))
        self.opacity=QSpinBox()
        self.opacity.setRange(35,100)
        self.opacity.setSuffix(' %')
        self.opacity.setValue(int(cfg.get('opacity',86)))
        lay.addWidget(self.opacity)
        lay.addWidget(QLabel('채팅창 스타일 · 닉네임/본문 개별 설정'))
        styles = normalize_style(cfg.get('chat_style',{}))
        self.color_inputs={}
        for key, title in (('nickname_color','일반채팅 닉네임 색'),
                           ('message_color','일반채팅 본문 색'),
                           ('megaphone_nickname_color','확성기 닉네임 색'),
                           ('megaphone_message_color','확성기 채팅 본문 색'),
                           ('background_color','배경색')):
            row=QHBoxLayout()
            row.addWidget(QLabel(title))
            color=QLineEdit(styles[key]); color.setMaxLength(7)
            color.setFixedWidth(110)
            self.color_inputs[key]=color
            row.addWidget(color)
            pick_color=QPushButton('색상 선택')
            pick_color.clicked.connect(lambda _=False,k=key: self.choose_color(k))
            row.addWidget(pick_color)
            row.addStretch(1)
            lay.addLayout(row)
        row=QHBoxLayout()
        self.nick_bold=QCheckBox('닉네임 굵게')
        self.nick_bold.setChecked(styles['nickname_bold'])
        self.nick_underline=QCheckBox('닉네임 밑줄')
        self.nick_underline.setChecked(styles['nickname_underline'])
        row.addWidget(self.nick_bold); row.addWidget(self.nick_underline)
        lay.addLayout(row)
        row=QHBoxLayout()
        self.msg_bold=QCheckBox('채팅 굵게')
        self.msg_bold.setChecked(styles['message_bold'])
        self.msg_underline=QCheckBox('채팅 밑줄')
        self.msg_underline.setChecked(styles['message_underline'])
        row.addWidget(self.msg_bold); row.addWidget(self.msg_underline)
        lay.addLayout(row)
        self.style_preview=QLabel('MapleKing : 커닝 파퀘 참가하실 분?')
        self.style_preview.setMinimumHeight(45)
        lay.addWidget(self.style_preview)
        for inp in self.color_inputs.values(): inp.textChanged.connect(self.update_preview)
        for chk in (self.nick_bold,self.nick_underline,self.msg_bold,self.msg_underline):
            chk.toggled.connect(self.update_preview)
        self.update_preview()
        self.opacity.valueChanged.connect(self.update_preview)
        # Captured Maple strip colours are composited pixels; do not use the
        # old hard-coded 28% opacity. Allow fine tuning against game lighting.
        self.mega_opacity=QSpinBox()
        self.mega_opacity.setRange(40,100)
        self.mega_opacity.setSuffix(' %')
        self.mega_opacity.setValue(int(cfg.get('megaphone_opacity',92)))
        lay.addWidget(QLabel('확성기 원본 배경 재현 강도'))
        lay.addWidget(self.mega_opacity)
        lay=capture_layout
        lay.addWidget(self._section('DOCKING  /  자석 모드'))
        lay.addWidget(QLabel('자석 도킹 · 번역창 가로 너비 (게임 세로 높이와 별개)'))
        self.dock_width=QSpinBox()
        self.dock_width.setRange(180,1600)
        self.dock_width.setSuffix(' px')
        self.dock_width.setValue(int(cfg.get('chat_geometry',{}).get('dock_width',
                                           cfg.get('chat_geometry',{}).get('width',470))))
        lay.addWidget(self.dock_width)
        self.match_height=QCheckBox('자석 도킹 시 게임 창 세로 높이에 맞추기')
        self.match_height.setChecked(bool(cfg.get('chat_geometry',{}).get('dock_match_height',True)))
        lay.addWidget(self.match_height)
        self.hud_height=QCheckBox('번역 채팅창 자체도 하단 UI 높이에 맞추기 (선택)')
        self.hud_height.setChecked(bool(cfg.get('chat_geometry',{}).get('hud_match_height',False)))
        lay.addWidget(self.hud_height)
        self.hud_panels=QCheckBox('좌측 컨트롤·우측 영어 번역기 높이를 게임 하단 UI에 맞추기')
        self.hud_panels.setChecked(bool(cfg.get('hud_panels_match',True)))
        lay.addWidget(self.hud_panels)
        lay.addWidget(self._section('CAPTURE  /  화면 인식'))
        lay.addWidget(QLabel('OCR 크기 확대'))
        self.scale=QDoubleSpinBox()
        self.scale.setRange(1.0,2.0)
        self.scale.setDecimals(1)
        self.scale.setSingleStep(0.1)
        self.scale.setValue(float(cfg.get('ocr_scale',1.8)))
        lay.addWidget(self.scale)
        self.glyph_debug_enabled=QCheckBox('글리프 줄 크롭 저장 (최대 40장, 개인정보 포함)')
        self.glyph_debug_enabled.setChecked(bool(cfg.get('glyph_debug_enabled', False)))
        lay.addWidget(self.glyph_debug_enabled)
        self.glyph_dictionary_enabled=QCheckBox('글리프 @ 전용 사전 (일반 글자는 비교만, 기본 OFF)')
        self.glyph_dictionary_enabled.setChecked(bool(cfg.get('glyph_dictionary_enabled', False)))
        lay.addWidget(self.glyph_dictionary_enabled)
        lay.addWidget(QLabel('자동 배치가 빗나가면 [인식 영역]으로 수동 보정하세요.'))
        for page in (general_layout,appearance_layout,capture_layout):
            page.addStretch(1)  # keep rows packed at the top of short pages
        self.auto_requested=False
        # small game buttons on the steel strip, split by a thin groove,
        # like the buddy list's ADD | DELETE | MY STATUS row
        buttons=QHBoxLayout()
        buttons.setContentsMargins(0,4,0,0)
        buttons.setSpacing(10)
        buttons.addStretch(1)
        save=QPushButton('설정 저장')
        save.setObjectName('confirm')  # blue, like CONFIRM
        save.clicked.connect(self.accept)
        buttons.addWidget(save)
        groove=QFrame()
        groove.setFixedSize(2,22)
        groove.setStyleSheet('background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7d93a8,stop:0.5 #7d93a8,stop:0.51 #e6eef6,stop:1 #e6eef6);border:0;')
        buttons.addWidget(groove)
        auto=QPushButton('저장 + 게임 창에 자동 맞춤')
        auto.setObjectName('action')   # orange, like MY STATUS
        auto.clicked.connect(self.request_auto)
        buttons.addWidget(auto)
        buttons.addStretch(1)
        for b in (save,auto):
            b.setFixedHeight(27)
            b.setMinimumWidth(150)
        outer.addLayout(buttons)
        # Buttons inside the pages: blue CONFIRM-style game buttons at their
        # own size, not full-width bars.
        for b in tabs.findChildren(QPushButton):
            b.setFixedHeight(24)
            b.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
            box=b.parentWidget().layout() if b.parentWidget() else None
            if box is not None:
                box.setAlignment(b,Qt.AlignmentFlag.AlignLeft)
        # Long translated info, URLs and Korean strings must wrap within the
        # settings viewport instead of manufacturing a horizontal scrollbar.
        for caption in self.findChildren(QLabel):
            if caption.objectName() not in ('brand',):
                caption.setWordWrap(True)
                caption.setMinimumWidth(0)

    def import_item_catalog(self):
        filename,_=QFileDialog.getOpenFileName(self,'허가받은 아이템 사전 파일 선택','','Item list (*.csv *.json)')
        if not filename: return
        try:
            count=install_catalog(filename)
        except (CatalogError, OSError, UnicodeError) as exc:
            QMessageBox.warning(self,'아이템 사전 불러오기 실패',str(exc))
            return
        self.catalog_status.setText(f'등록된 아이템: {count:,}개')
        QMessageBox.information(self,'아이템 사전 적용',f'{count:,}개 항목을 등록했습니다. 다음 번역부터 반영됩니다.')

    def paintEvent(self, event):
        """The whole window from the game's frame pieces (white outer line,
        steel body, rounded bottom), like the buddy list window."""
        from PySide6.QtGui import QPainter
        p=QPainter(self)
        p.drawPixmap(0,0,CU.window_pixmap(self.width(),self.height()))
        p.end()

    @staticmethod
    def _section(title: str):
        # like the buddy window's blue 'BUDDY LIST' bar
        label=CU.ClassicSectionTitle(title)
        label.setObjectName('sectionTitle')
        label.setFixedHeight(round(18*CU.SCALE[1]))
        # a pink stat-window pill; never stretched by spare page height
        label.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        return label

    def _theme_preview_changed(self, *_):
        variant=self.theme_choice.currentData()
        self.setStyleSheet(settings_stylesheet(variant))
        self.update_preview()

    def style_values(self):
        return normalize_style({
            **{k:field.text() for k,field in self.color_inputs.items()},
            'nickname_bold':self.nick_bold.isChecked(),
            'nickname_underline':self.nick_underline.isChecked(),
            'message_bold':self.msg_bold.isChecked(),
            'message_underline':self.msg_underline.isChecked(),
        })

    def choose_color(self, key):
        """Open a genuinely foreground modal picker above pinned Maple panels.

        Windows can place a native child color picker *behind* a topmost Qt
        settings window. Use a Qt-owned non-native picker, make it transiently
        topmost, and suspend our game z-order polling until the dialog closes.
        A rejected or failed picker never changes the current colour.
        """
        picker = QColorDialog(QColor(self.color_inputs[key].text()), self)
        picker.setWindowTitle('색상 선택')
        picker.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        picker.setWindowModality(Qt.WindowModality.ApplicationModal)
        picker.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        picker._kain_transient_dialog = True
        self._color_picker = picker
        self._color_picker_open = True
        try:
            picker.show()
            picker.raise_()
            picker.activateWindow()
            if picker.exec() == QDialog.DialogCode.Accepted:
                color = picker.selectedColor()
                if color.isValid():
                    self.color_inputs[key].setText(color.name())
        finally:
            self._color_picker_open = False
            self._color_picker = None
            picker.close()
            if self.isVisible():
                self.raise_()
                self.activateWindow()

    def update_preview(self, *_):
        values=self.style_values()
        nick=text_css(values,'nickname'); body=text_css(values,'message')
        background=qt_rgba_color(values['background_color'],self.opacity.value())
        self.style_preview.setText(
            f'<span style="{nick}">MapleKing</span>'
            f'<span style="{body}"> : 커닝 파퀘 참가하실 분?</span>')
        self.style_preview.setStyleSheet(f'padding:8px; border-radius:{radius_px(self.theme_choice.currentData())}px;'
            f'background-color:{background};')

    def request_auto(self):
        self.auto_requested=True
        self.accept()

    def apply_remote_font(self):
        self.font_url_requested.emit(self.font_path.text().strip())

    def choose_font(self):
        filename,_=QFileDialog.getOpenFileName(self,'폰트 파일 선택','','Fonts (*.ttf *.otf)')
        if filename:
            self.font_path.setText(filename)


class Controller(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app=app
        self.cfg=load_config()
        # One-time rescue of v0.3.6's persisted 'normal' Z-order setting.
        # After migration users may still change the mode and it is saved.
        if not self.cfg.get('stacking_v037_initialized'):
            self.cfg['top_mode']='game'
            self.cfg['stacking_v037_initialized']=True
        self.cfg['engine']='argos'
        self.cfg['libre_url']=''
        self.cfg['libre_key']=''
        self.cfg['enabled']={'bubble':False,'chat':True,'trade':False}
        if self.cfg.get('top_mode') not in Z_ORDER_MODES:
            self.cfg['top_mode']='game'
        if self.cfg.get('floating_mode') not in ('overlay','dock-left','dock-right','free'):
            self.cfg['floating_mode']='overlay'
        self.worker: LiveWorker | None=None
        self.selector: RegionSelector | None=None
        self.signals=ComposeSignals()
        self.signals.done.connect(self.compose_done)
        self.compose_sequence=0
        self.closing=False
        self.last_anchor: QRect | None = None
        self.chat_relative: tuple[float,int,int,int] | None = None
        self.last_overlay_warning=False
        self.recent_ocr = None
        self._view_latency = LatencyBook()
        self.recent_error = ''
        self._dock_warning_shown=False
        self._placing=False
        self._last_geometry=None
        self._font_id=None
        self._web_font_path=None
        self._remote_font_busy=False
        self._font_apply_signal=FontSignals()
        self._font_apply_signal.done.connect(self._font_url_done)
        self.game_pid=0
        self.game_hwnd=0
        self._game_probe_at=0.0
        self._last_valid_game_at=0.0
        self.last_game_window=None
        # (width, height, scale) the chat auto detection measured on screen
        self._detected_ui_scale=None
        self._prior_stack_active = None
        self._last_stack_mode = None
        self._last_foreground_context = None
        self._settings_dialog = None
        self.obs=OBSChatSource()
        self.obs_url=''
        try:
            self.obs_url=self.obs.start()
        except OSError as exc:
            LOG.warning('OBS local source unavailable: %s',exc)
        self.history=None
        self._history_dialog=None
        try:self.history=ChatHistoryStore(config_path().parent/'chat-history.sqlite3')
        except Exception:LOG.exception('Could not open translation history')
        self.chat=FloatingChat(self.history)
        self.chat.restore_history()
        self.chat.set_split_ratio(int(self.cfg.get("split_ratio_general",70)))
        self.chat.ratio_changed.connect(self.save_split_ratio)
        self.chat.apply_theme(self.cfg.get('theme_variant','rounded'))
        self.chat.set_top_mode(self.cfg.get('top_mode','game'))
        self.chat.geometry_edited.connect(self.geometry_edited)
        self.chat._allow_resize_signal=True
        self.left=CompactSettings()
        self.chat.history_error.connect(self.left.set_status)
        if self.history is None:
            QTimer.singleShot(0,lambda:self.left.set_status('번역 내역 파일을 열지 못했습니다 · app.log 확인'))
        self.right=CompactComposer()
        self.hunt_widget=HuntWindow(self.cfg,self.save)
        self.hunt_widget.stacked_by_app=True
        self.left.set_theme_variant(self.cfg.get('theme_variant','rounded'))
        self.right.set_theme_variant(self.cfg.get('theme_variant','rounded'))
        self.left.toggle.connect(self.toggle_worker)
        self.left.choose.connect(self.choose_region)
        self.left.mode_changed.connect(self.mode_changed)
        self.left.edit_changed.connect(self.toggle_edit)
        self.left.scroll_mode_changed.connect(self.toggle_scroll_mode)
        self.left.details.connect(self.open_settings)
        self.left.test_translation.connect(self.test_translation)
        self.left.test_ocr.connect(self.show_ocr_diagnostic)
        self.left.test_display.connect(self.show_sample_message)
        self.left.obs_copy.connect(self.copy_obs_url)
        # control-panel buttons: press once to open, again to close (R18)
        self.left.hunt_show.connect(self.toggle_hunt_stats)
        self.left.price_show.connect(self.toggle_price_log)
        self.left.quit.connect(self.quit)
        self.right.translate_clicked.connect(self.translate_to_english)
        self.left.mode.blockSignals(True)
        self.left.mode.setCurrentIndex(max(0,self.left.mode.findData(self.cfg['floating_mode'])))
        self.left.mode.blockSignals(False)
        self.load_font()
        if self.cfg.get('font_url'):
            self.apply_noonnu_url(self.cfg['font_url'])
        self.apply_chat_appearance()
        self.sync_obs()
        self.chat.setWindowOpacity(1.0)
        self._placing=True
        self.chat.resize(int(self.geometry_pref('width',470)), int(self.geometry_pref('height',140)))
        self._placing=False
        self.chat.set_mode(self.cfg['floating_mode'])
        self.chat.hide()
        self.left.show()
        self.right.show()
        if not self.cfg.get('help_seen_r19'):
            # the features & usage poster once, on the first start of this version
            self.cfg['help_seen_r19']=True
            save_config(self.cfg)
            QTimer.singleShot(1500,self.show_help)
        self.layout_timer=QTimer(self)
        self.layout_timer.setInterval(200)
        self.layout_timer.timeout.connect(self.relayout)
        self.layout_timer.timeout.connect(self.sync_stack)
        self.layout_timer.start()
        self.relayout()
        self.save()

    def sync_stack(self):
        """Keep all THREE KAIN windows above Maple when enabled.

        always: the translation feed AND both control panels stay topmost,
                regardless of whether Maple is the active application.
        game:   temporarily make all three topmost while Maple or a KAIN
                control is active (also works for borderless fullscreen).
                When another app is foreground, demote all three to normal
                Z-order so other applications can cover them.
        normal: none of the three KAIN windows remain topmost.

        A separate 'pin settings' checkbox only controls the nonmodal settings
        dialog and never removes topmost from the two MINI control panels.
        """
        if self.closing or self.selector is not None:
            return
        # Do not reorder the settings window over an active color picker.
        # The picker is application-modal and briefly topmost by design.
        settings = getattr(self, '_settings_dialog', None)
        if settings is not None and getattr(settings, '_color_picker_open', False):
            return
        # ComboBox options are Qt popup WINDOWS. Reordering the game HUD every
        # 200ms while a dropdown is open can hide it behind a topmost panel.
        if getattr(QApplication, 'activePopupWidget', lambda: None)() is not None:
            return
        mode=self.cfg.get('top_mode','game')
        if mode not in Z_ORDER_MODES:
            mode='game'
        context=foreground_context(self.game_hwnd,self.game_pid,os.getpid())
        active=bool(self.game_hwnd) and context in ('game','controls')
        # A focus transition (controls -> Maple) may reorder topmost windows;
        # otherwise skip redundant 5Hz SetWindowPos calls that made HUD flash.
        state_changed = (self._last_stack_mode != mode
                         or self._prior_stack_active != active
                         or self._last_foreground_context != context)
        panels=(self.chat,self.left,self.right)
        dialogs=[w for w in QApplication.topLevelWidgets()
                 if isinstance(w,QDialog) and w.isVisible()
                 and not getattr(w, '_kain_transient_dialog', False)
                 and not getattr(w, 'isModal', lambda: False)()]
        pinned_settings=bool(self.cfg.get('pin_settings_above_game',False))

        if mode == 'always':
            # Regression fix: older builds pinned only chat, and left/right
            # panels were promoted only while Maple had focus. Both panels
            # could disappear behind Maple as soon as the focus changed.
            promoted=state_changed
            for widget in panels:
                if widget.isVisible() and (state_changed or not is_topmost(int(widget.winId()))):
                    set_native_stack(int(widget.winId()),'always')
                    promoted=True
            getattr(self,'stack_tools',lambda *a:None)('always',promoted)
            if pinned_settings:
                for dialog in dialogs:
                    set_native_stack(int(dialog.winId()),'always')
            else:
                # No permanent topmost state for dialogs when pin is disabled.
                for dialog in dialogs:
                    if is_topmost(int(dialog.winId())):
                        set_native_stack(int(dialog.winId()),'normal')
            self._prior_stack_active=True
            self._last_stack_mode='always'
            self._last_foreground_context=context
            return

        if mode == 'normal':
            # The user explicitly switched BOTH protections off. Remove the
            # native topmost flag from chat *and* both mini panels, even if a
            # stale flag survived a prior mode or the game changed focus.
            for widget in list(panels)+getattr(self,'tool_windows',lambda:[])():
                if widget.isVisible() and is_topmost(int(widget.winId())):
                    set_native_stack(int(widget.winId()),'normal')
            for dialog in dialogs:
                if is_topmost(int(dialog.winId())):
                    set_native_stack(int(dialog.winId()),'normal')
            self._last_stack_mode='normal'
            self._prior_stack_active=False
            self._last_foreground_context=context
            return

        # GAME-ONLY: Windows has no persistent "only above one particular
        # window" flag. Temporarily put each KAIN window in the topmost group
        # while Maple is in focus; demote promptly on another application's
        # activation. This also supports composited borderless fullscreen.
        if active:
            promoted=state_changed
            for widget in panels:
                if widget.isVisible() and (state_changed or not is_topmost(int(widget.winId()))):
                    set_native_stack(int(widget.winId()),'game',
                                     game_foreground=True,
                                     game_topmost=is_topmost(self.game_hwnd))
                    promoted=True
            getattr(self,'stack_tools',lambda *a:None)('game',promoted)
            if pinned_settings:
                for dialog in dialogs:
                    set_native_stack(int(dialog.winId()),'game',
                                     game_foreground=True,
                                     game_topmost=is_topmost(self.game_hwnd))
            else:
                for dialog in dialogs:
                    if is_topmost(int(dialog.winId())):
                        set_native_stack(int(dialog.winId()),'normal')
        elif self._prior_stack_active or self._last_stack_mode != 'game':
            # Yield once when switching to Chrome, OBS, Explorer, etc.
            for widget in list(panels)+getattr(self,'tool_windows',lambda:[])():
                if widget.isVisible():
                    restore_below_foreground(int(widget.winId()),self.game_hwnd)
            for dialog in dialogs:
                if is_topmost(int(dialog.winId())):
                    set_native_stack(int(dialog.winId()),'normal')
        self._prior_stack_active=active
        self._last_stack_mode='game'
        self._last_foreground_context=context

    def tool_windows(self):
        return _tool_windows(self)

    def stack_tools(self, mode, force):
        _stack_tools(self, mode, force)

    def apply_chat_appearance(self):
        self.chat._source_colors=bool(self.cfg.get('source_chat_colors',True))
        self.cfg['chat_style'] = normalize_style(self.cfg.get('chat_style',{}))
        self.chat.apply_style(self.cfg['chat_style'],int(self.cfg.get('opacity',86)),
                              int(self.cfg.get('megaphone_opacity',92)))

    def save_split_ratio(self, ratio: int):
        self.cfg['split_ratio_general']=max(15,min(85,int(ratio)))
        self.save()
        self.sync_obs()

    def sync_obs(self):
        if not self.obs_url:
            return
        self.obs.set_state(self.chat._records,
                           self.cfg.get('font_size',13), self.chat._family,
                           self.cfg.get('opacity',86),
                           self.cfg.get('chat_style',{}),
                           web_font=bool(self._web_font_path and self._font_id is not None),
                           theme_variant=self.cfg.get('theme_variant','rounded'),
                           split_ratio_general=self.cfg.get('split_ratio_general',70),
                           megaphone_opacity=self.cfg.get('megaphone_opacity',92),
                           source_chat_colors=self.cfg.get('source_chat_colors',True))

    def copy_obs_url(self):
        if not self.obs_url:
            self.left.set_status('OBS 로컬 주소 생성 실패 · 앱 로그 확인')
            return
        QApplication.clipboard().setText(self.obs_url)
        self.left.set_status('OBS 브라우저 소스 URL 복사됨: '+self.obs_url)

    def geometry_pref(self, key: str, fallback):
        return self.cfg.get('chat_geometry',{}).get(key,fallback)

    def save(self):
        save_config(self.cfg)

    def apply_noonnu_url(self, url: str):
        """Request font in background so a slow CDN cannot freeze game UI."""
        url=url.strip()
        if not url:
            self.cfg['font_url']=''
            self._web_font_path=None
            self.obs.set_font_data(b'')
            self.load_font();self.sync_obs();self.save()
            self.left.set_status('기본 글꼴로 복원')
            return
        if self._remote_font_busy:
            self.left.set_status('폰트를 적용 중입니다. 완료 후 다시 시도하세요.')
            return
        self._remote_font_busy=True
        self.left.set_status('눈누 폰트 주소 확인 중…')
        def job():
            try:
                path=cached_font_from_noonnu(url)
                self._font_apply_signal.done.emit(url,str(path),'')
            except Exception as ex:
                self._font_apply_signal.done.emit(url,'',str(ex))
        threading.Thread(target=job,daemon=True,name='kain-font-url').start()

    def _font_url_done(self, url: str, path: str, error: str):
        self._remote_font_busy=False
        if error:
            self.left.set_status('눈누 폰트 적용 실패: '+error[:150]);return
        self.cfg['font_url']=url
        self._web_font_path=path
        self.load_font()
        if self._font_id is None:
            self.left.set_status('폰트 파일은 받았지만 Qt에서 열지 못했습니다.');return
        self.obs.set_font_data(Path(path).read_bytes())
        self.save();self.sync_obs()
        self.left.set_status('눈누 폰트 적용 완료 (OBS 포함): '+self.chat._family)

    def load_font(self):
        if self._font_id is not None:
            QFontDatabase.removeApplicationFont(self._font_id)
            self._font_id = None
        path = self._web_font_path
        family='Malgun Gothic'
        if path and Path(path).is_file() and Path(path).suffix.lower() in ('.ttf','.otf'):
            fid=QFontDatabase.addApplicationFont(path)
            if fid >= 0:
                names=QFontDatabase.applicationFontFamilies(fid)
                if names:
                    family=names[0]
                    self._font_id=fid
            else:
                self.left.set_status('폰트 로딩 실패 · 맑은 고딕 사용')
        self.chat.apply_font(family, int(self.cfg.get('font_size',13)))

    def _find_game(self):
        now=time.monotonic()
        # Re-enumerating process windows five times per second is wasteful.
        # Some DirectX modes briefly drop out of enumeration during a map or
        # fullscreen transition; a single miss must not hide the entire HUD.
        if now-self._game_probe_at < 0.45:
            return self.last_game_window
        self._game_probe_at=now
        win=find_maple_window(self.game_pid, self.game_hwnd,
                              self.cfg.get('game_title_keyword','maple'))
        if win:
            self.game_pid,self.game_hwnd=win.pid,win.hwnd
            self.last_game_window=win
            self._last_valid_game_at=now
        elif self.last_game_window is not None and now-self._last_valid_game_at < 1.25:
            return self.last_game_window  # prevent intermittent one-frame flash
        else:
            self.game_pid,self.game_hwnd=0,0
            self.last_game_window=None
        return win

    def auto_place_from_game(self, notify=True) -> bool:
        win=self._find_game()
        if not win:
            if notify:self.left.set_status('MapleStory 프로세스 미검출 · 게임 실행/창모드 확인')
            return False
        x,y,w,h=estimate_chat_area(win.rect,self.cfg.get('game_resolution','auto'))
        region={'left':x,'top':y,'width':w,'height':h}
        self.cfg['regions']['chat']=region
        self._remember_region(win,region)
        self.cfg['region_source']='auto'
        g=self.cfg.setdefault('chat_geometry',{})
        g.update({'overlay_dx':0,'overlay_dy':0,'width':w,'height':h})
        self.last_anchor=QRect(*win.rect)
        self._placing=True
        try:self.chat.resize(max(180,w),max(55,h))
        finally:self._placing=False
        if self.worker and self.worker.isRunning():self.worker.update_settings(self.cfg)
        self.save()
        if notify:self.left.set_status(f'게임 PID {win.pid} 연결 · 초기 채팅 위치 추정 · 인식 영역으로 확정 권장')
        return True

    def game_ui_scale_for(self, win) -> float:
        """The game's UI scale: measured by auto detection, else from size."""
        gw,gh=int(win.rect[2]),int(win.rect[3])
        found=self._detected_ui_scale
        if found and found[:2]==(gw,gh) and self.cfg.get('auto_chat_region',True):
            return found[2]
        return game_ui_scale(gw,gh)

    def _remember_region(self, win, region):
        """Store the chat crop relative to the game and the size it was made at."""
        self.cfg['relative_chat_region']=vars(region_to_relative(win.rect,region))
        self.cfg['chat_region_game']={'width':int(win.rect[2]),'height':int(win.rect[3]),
                                      'scale':round(self.game_ui_scale_for(win),4)}

    def _region_reference(self, win) -> dict:
        ref=self.cfg.get('chat_region_game')
        if isinstance(ref,dict) and ref.get('width') and ref.get('height'):
            return ref
        # Settings from before R20 do not say which game size the crop was
        # made at: a chosen game resolution tells it, else the current size.
        size=resolution_size(self.cfg.get('game_resolution','auto')) or (int(win.rect[2]),int(win.rect[3]))
        ref={'width':size[0],'height':size[1],'scale':round(game_ui_scale(*size),4)}
        self.cfg['chat_region_game']=ref
        self.save()
        return ref

    def anchor_rect(self) -> QRect | None:
        win=self._find_game()
        if not win:
            self.last_anchor=None
            return None
        game=QRect(*win.rect)
        relative=self.cfg.get('relative_chat_region')
        if relative is None:
            # Migrate v0.2.x absolute coordinates exactly once per game link.
            # Preserve a manual selection if it still lies inside this game,
            # otherwise discard broken historic placement and start calibrated.
            old=self.cfg['regions'].get('chat')
            gx,gy,gw,gh=win.rect
            contained=is_valid_region(old) and (gx<=old['left'] and gy<=old['top']
                and old['left']+old['width']<=gx+gw
                and old['top']+old['height']<=gy+gh)
            if contained and self.cfg.get('region_source')=='manual':
                self._remember_region(win,old)
            else:
                x,y,w,h=estimate_chat_area(win.rect,self.cfg.get('game_resolution','auto'))
                old={'left':x,'top':y,'width':w,'height':h}
                self.cfg['regions']['chat']=old
                self.cfg['region_source']='auto'
                self._remember_region(win,old)
                self.cfg['chat_geometry'].update({'width':w,'height':h,'overlay_dx':0,'overlay_dy':0})
                self.left.set_status(f'PID {win.pid} 감지 · 채팅 영역 자동 추정 · [인식 영역] 재지정 권장')
            relative=self.cfg['relative_chat_region']
            self.save()
        if isinstance(relative,dict) and all(k in relative for k in ('x','y','w','h')):
            ref=self._region_reference(win)
            if (int(ref['width']),int(ref['height']))==(int(win.rect[2]),int(win.rect[3])):
                region=relative_to_region(win.rect,relative)
            else:
                # Another game resolution: the chat HUD stays at the bottom
                # centre and follows the game's UI scale, not the window.
                region=hud_relative_region(relative,ref,win.rect)
            if region != self.cfg['regions'].get('chat'):
                self.cfg['regions']['chat']=region
                if self.worker and self.worker.isRunning():self.worker.update_settings(self.cfg)
        self.last_anchor=QRect(game)
        return game

    def _set_chat_geometry(self, rect: QRect):
        if self._placing or self.chat.editing or self.cfg['floating_mode']=='free':
            return
        self._placing=True
        try:
            if self.chat.geometry() != rect:
                self.chat.setGeometry(rect)
            if not self.chat.isVisible():
                self.chat.show()
                enable_obs_window_capture(self.chat)
        finally:
            self._placing=False

    def _refit_for_ui_scale(self):
        """The game's UI scale changed: lay the game-style panels out again."""
        CU.close_pixmap.cache_clear()
        for panel in (self.left,self.right):
            panel._hud_compact=None          # fit_bottom_hud lays out afresh
            for child in panel.findChildren(QWidget):
                child.updateGeometry()
            if panel.card.layout() is not None:
                panel.card.layout().invalidate()
            panel.update()

    def relayout(self):
        if self.selector is not None or self.closing or self._placing:
            return
        game=self.anchor_rect()
        mon=monitor_for(self.cfg['regions'].get('chat'))
        target=game or mon
        ui_scale=None
        if game is not None and self.last_game_window is not None:
            # The panels, buttons and windows follow the game's own UI scale.
            ui_scale=self.game_ui_scale_for(self.last_game_window)
            if CU.set_ui_scale(ui_scale):
                self._refit_for_ui_scale()
        if game is not None and self.cfg.get('hud_panels_match',True):
            # Fit ONLY left controls and right Korean→English translator.
            # The draggable translated-chat splitter/dock geometry is separate.
            l_rect,r_rect=hud_panel_geometry((game.x(),game.y(),game.width(),game.height()),
                    (mon.x(),mon.y(),mon.width(),mon.height()),
                    self.cfg['regions'].get('chat'),ui_scale=ui_scale)
            self.left.fit_bottom_hud(l_rect[2],l_rect[3])
            self.right.fit_bottom_hud(r_rect[2],r_rect[3])
            self.left.move(l_rect[0],l_rect[1]+l_rect[3]-self.left.height())
            self.right.move(r_rect[0],r_rect[1])
        else:
            # Fallback: preserve a comfortable side-panel layout without game.
            self.left.fit_bottom_hud(360,258)
            self.right.fit_bottom_hud(326,150)
            y=max(mon.top()+5, min(target.bottom()-self.left.height()-8,
                                    mon.bottom()-self.left.height()-5))
            lx=max(mon.left()+5,min(target.left()+5,mon.right()-self.left.width()-5))
            rx=max(mon.left()+5,min(target.right()-self.right.width()-5,mon.right()-self.right.width()-5))
            self.left.move(lx,y)
            self.right.move(rx,max(mon.top()+5,min(y+self.left.height()-self.right.height(),mon.bottom()-self.right.height()-5)))
        mode=self.cfg['floating_mode']
        if mode=='free':
            # A previously saved free window might sit partly below a resized
            # monitor, making the last chat row physically unviewable. Keep at
            # least the visible panel inside the active desktop work area.
            if self.chat.isVisible() and not self.chat.editing:
                available=mon.adjusted(2,2,-2,-2)
                old=self.chat.geometry()
                if old.top()>=available.bottom()-36 or old.bottom()>available.bottom()+18:
                    new_y=max(available.top(), available.bottom()-old.height())
                    self.chat.move(min(max(old.x(),available.left()),
                        max(available.left(),available.right()-old.width())),new_y)
            if not self.chat.isVisible():
                x=self.geometry_pref('free_x',None)
                yy=self.geometry_pref('free_y',None)
                if x is None or yy is None:
                    x=mon.left()+max(10,(mon.width()-self.chat.width())//2)
                    yy=mon.top()+max(10,(mon.height()-self.chat.height())//2)
                self.chat.move(int(x),int(yy))
                self.chat.show()
                enable_obs_window_capture(self.chat)
            return
        if self.chat.editing:
            return
        w=int(self.geometry_pref('dock_width',self.geometry_pref('width',470)) if mode.startswith('dock-')
              else self.geometry_pref('width',470))
        h=int(self.geometry_pref('height',140))
        if mode=='overlay':
            region=self.cfg['regions'].get('chat')
            if not is_valid_region(region) or game is None:
                self.chat.hide()
                self.left.set_status('인식 영역을 지정하면 그 위치에 덮어 표시됩니다')
                return
            r=QRect(int(region['left'])+int(self.geometry_pref('overlay_dx',0)),
                    int(region['top'])+int(self.geometry_pref('overlay_dy',0)),w,h)
            self._set_chat_geometry(r)
            return
        if game is None:
            self.chat.hide()
            self.left.set_status('자석 모드: 게임 창을 찾지 못함 · ⚙ 제목 확인')
            return
        dock_game=(game.x(),game.y(),game.width(),game.height())
        if self.geometry_pref('hud_match_height',True):
            # Match the real bottom HUD rather than an entire game-tall column.
            # OCR region defines upper edge; never infer from monitor alone.
            region=self.cfg['regions'].get('chat')
            if is_valid_region(region):
                hud_top=max(game.top(),min(game.bottom()-50,int(region['top'])-6))
                dock_game=(game.x(),hud_top,game.width(),game.bottom()-hud_top+1)
        dock, placement = dock_to_side(
            dock_game,
            (mon.x(),mon.y(),mon.width(),mon.height()),
            w,h,'right' if mode=='dock-right' else 'left',
            bool(self.geometry_pref('dock_match_height',True)),gap=0)
        # Snap flush to the game's right/left boundary: the screenshot's
        # yellow client edge is the target, not an extra 7px blank gutter.
        self._set_chat_geometry(QRect(*dock))
        if placement=='inside-fallback' and not getattr(self,'_dock_warning_shown',False):
            self.left.set_status('자석: 바깥 공간 부족 · 게임 안쪽 임시 배치 (창 모드 권장)')
            self._dock_warning_shown=True
        elif placement=='outside':
            self._dock_warning_shown=False

    def toggle_scroll_mode(self, enabled: bool):
        self.chat.set_scroll_interactive(enabled)
        if enabled:
            self.left.set_status('휠 스크롤 ON: 위로 지난 채팅 / 게임 클릭 투과 잠시 해제')
        else:
            self.left.set_status('휠 스크롤 OFF: 게임 클릭 투과 복원 (자유 플로팅은 제외)')

    def toggle_edit(self, enabled: bool):
        if self.worker and self.worker.isRunning() and self.cfg['floating_mode']=='overlay':
            paused=dict(self.cfg)
            paused['ocr_paused']=bool(enabled)
            self.worker.update_settings(paused)
        self.chat.set_editable(enabled)
        if enabled:
            if self.cfg['floating_mode'] in ('dock-left','dock-right') and not self.chat.isVisible():
                self.left.set_status('자석 공간 없음 · 자유 플로팅 선택')
            else:
                self.chat.show()
                self.left.set_status('번역창 드래그 / 우하단 크기 변경')
        else:
            self.capture_geometry()
            self.chat.set_editable(False)
            self.relayout()
            if self.chat.isVisible():
                enable_obs_window_capture(self.chat)
            self.left.set_status('창 위치와 크기를 저장했습니다')

    def geometry_edited(self):
        if self._placing:
            return
        if self.cfg['floating_mode']=='free' or self.chat.editing:
            self.capture_geometry()

    def capture_geometry(self):
        g=self.cfg.setdefault('chat_geometry',{})
        mode=self.cfg['floating_mode']
        if mode.startswith('dock-'):
            g['dock_width']=int(self.chat.width())
        else:
            g['width']=int(self.chat.width())
            g['height']=int(self.chat.height())
        if mode=='free':
            g['free_x']=int(self.chat.x())
            g['free_y']=int(self.chat.y())
        elif mode=='overlay' and is_valid_region(self.cfg['regions'].get('chat')):
            region=self.cfg['regions']['chat']
            g['overlay_dx']=int(self.chat.x()-region['left'])
            g['overlay_dy']=int(self.chat.y()-region['top'])
        self.save()

    def mode_changed(self,value):
        if value not in ('overlay','dock-left','dock-right','free'):
            return
        # Save free-floating geometry BEFORE switching modes.
        if self.cfg['floating_mode']=='free':
            self.capture_geometry()
        if self.left.edit.isChecked():
            self.left.edit.setChecked(False)
        self.cfg['floating_mode']=value
        if value=='overlay' and is_valid_region(self.cfg['regions'].get('chat')):
            region=self.cfg['regions']['chat']
            # Initial overlay must fit selected chat area, not the old tall dock.
            if int(self.geometry_pref('height',140)) > int(region['height'])*2:
                self.cfg['chat_geometry']['height']=int(region['height'])
            if int(self.geometry_pref('width',470)) > int(region['width'])*2:
                self.cfg['chat_geometry']['width']=int(region['width'])
        self.chat.set_mode(value)
        self.chat.hide()
        self.last_overlay_warning=False
        self.save()
        self.relayout()

    def choose_region(self):
        if self.selector is not None:
            self.selector.raise_()
            self.selector.activateWindow()
            return
        if self.worker and self.worker.isRunning():
            paused=dict(self.cfg)
            paused['ocr_paused']=True
            self.worker.update_settings(paused)
        # Create/show the hit-test surface *before* hiding any program panels.
        # If the selector cannot appear, the controls remain available.
        def launch():
            picker=None
            try:
                picker=RegionSelector()
                picker.selected.connect(self.selected)
                self.selector=picker
                picker.show()
                if not picker.isVisible():
                    raise RuntimeError('영역 선택 창이 표시되지 않음')
                self.left.hide()
                self.right.hide()
                self.chat.hide()
                picker.raise_()
                picker.activateWindow()
                picker.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
                QTimer.singleShot(500,lambda: self._check_selector_visible(picker))
                # Safety net if Windows does not dispatch a mouse/ESC event.
                QTimer.singleShot(60000,lambda: picker.finish(None) if self.selector is picker else None)
            except Exception as exc:
                LOG.exception('OCR region selector failed: %s',exc)
                if picker is not None:
                    picker.finish(None)
                else:
                    self.selected(None)
                self.left.set_status('인식 영역 선택 실패 · 프로그램 창 복원됨')
        QTimer.singleShot(120,launch)

    def _check_selector_visible(self, picker):
        if self.selector is picker and not picker.isVisible():
            picker.finish(None)

    def selected(self,region):
        self.selector=None
        if is_valid_region(region):
            self.cfg['regions']['chat']=region
            self.cfg['region_source']='manual'
            self.cfg['auto_chat_region']=False  # explicit manual override wins
            win=self._find_game()
            if win:
                self._remember_region(win,region)
                self.left.set_status(f'MapleStory PID {win.pid} · 게임 창 상대 위치 저장')
            else:
                self.cfg['relative_chat_region']=None
                self.left.set_status('게임 창을 못 찾음 · OCR 영역은 임시 절대좌표로 저장')
            g=self.cfg.setdefault('chat_geometry', {})
            g['overlay_dx']=0
            g['overlay_dy']=0
            g['width']=int(region['width'])
            g['height']=int(region['height'])
            self._placing=True
            self.chat.resize(max(180, int(region['width'])), max(55, int(region['height'])))
            self._placing=False
            self.chat_relative=None
            self.last_anchor=None
            self.save()
            self.left.set_status('인식 영역 저장 · 번역 ON 선택')
            if self.worker and self.worker.isRunning():
                self.worker.update_settings(self.cfg)
        self.left.show()
        self.right.show()
        if self.worker and self.worker.isRunning():
            self.worker.update_settings(self.cfg)
        self.relayout()

    def toggle_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.left.update_live(False)
            self.left.set_status('실시간 번역 중지됨')
            return
        if not self.cfg.get('auto_chat_region',True) and not is_valid_region(self.cfg['regions'].get('chat')):
            self.left.update_live(False)
            QMessageBox.information(self.left, '하단 채팅 영역',
                '수동 모드에서는 [인식 영역]을 지정하거나 설정의 자동 채팅 탐지를 켜 주세요.')
            return
        self.worker=LiveWorker(self.cfg)
        self.worker.translated.connect(self.message_received)
        self.worker.status.connect(self.left.set_status)
        self.worker.problem.connect(self.worker_problem)
        self.worker.inspection.connect(self.ocr_inspection)
        self.worker.finished.connect(lambda: self.left.update_live(False))
        self.worker.start()
        self.left.update_live(True)
        self.left.set_status('게임 창·채팅 영역 자동 탐지 중…' if self.cfg.get('auto_chat_region',True) else 'Argos 오프라인 모델 + OCR 초기화 중…')

    def message_received(self, message: dict):
        self.chat.put(message)
        self.chat_extras(message)
        if message.get('order'):
            self._view_latency.observe('capture_to_ui_slot',(time.monotonic()-message['order'][0])*1000)
        self.sync_obs()
        self.left.set_status('번역 표시됨 · ' + str(message.get('nickname','')))

    def worker_problem(self, detail: str):
        LOG.warning(detail)
        self.recent_error = detail
        self.left.set_status('오류: ' + detail)
        self.left.toggle_btn.setToolTip(detail)

    def ocr_inspection(self, data: dict):
        self.recent_ocr = {**data, 'metrics':{**data.get('metrics',{}),**self._view_latency.snapshot()}}
        if not self.cfg.get('auto_chat_region',True):
            return
        metrics=data.get('metrics') or {}
        region=metrics.get('auto_chat_region')
        if not is_valid_region(region):
            return
        win=self._find_game()
        found_size=tuple(metrics.get('auto_chat_game_size') or ())
        if win and found_size and found_size!=(int(win.rect[2]),int(win.rect[3])):
            return   # found before the game changed resolution; wait for the new one
        scale_changed=False
        if win and metrics.get('auto_ui_scale'):
            found=(int(win.rect[2]),int(win.rect[3]),float(metrics['auto_ui_scale']))
            scale_changed=found!=self._detected_ui_scale
            self._detected_ui_scale=found
        previous=self.cfg['regions'].get('chat')
        ref=self.cfg.get('chat_region_game') or {}
        same_size=bool(win) and (ref.get('width'),ref.get('height'))==(int(win.rect[2]),int(win.rect[3]))
        if previous==region and same_size and not scale_changed:
            return
        self.cfg['regions']['chat']=dict(region)
        self.cfg['region_source']='auto'
        if win:
            self._remember_region(win,region)
        # Do not force a UI change from every frame; this fires only when
        # the actual region moves/resizes or the initial calibration completes.
        self.save()
        self.relayout()

    def show_hunt_stats(self):
        self.hunt_widget.show()
        self.hunt_widget.raise_()

    def toggle_hunt_stats(self):
        """Hide only the window; a running measurement keeps counting."""
        if self.hunt_widget.isVisible():
            hide=getattr(self.hunt_widget,'request_hide',None)
            if hide is not None:
                if not hide():
                    self.left.set_status('경험치 측정 중 · 측정기에서 종료를 누르면 닫을 수 있습니다')
            else:
                self.hunt_widget.hide()
        else:
            self.show_hunt_stats()

    def toggle_price_log(self):
        old=getattr(self,'_price_window',None)
        try:
            if old is not None and old.isVisible():
                old.close();return
        except RuntimeError:
            pass
        self.show_price_log()

    def show_ocr_diagnostic(self):
        if self.recent_ocr is None:
            QMessageBox.information(self.left, 'OCR 진단',
                '최근 OCR 데이터가 없습니다. 인식 영역을 지정하고 번역 ON을 누른 다음 다시 확인하세요.')
            return
        d = self.recent_ocr
        raw = '\n'.join(str(x) for x in d.get('raw', [])[:18]) or '(인식된 글자가 없습니다)'
        parsed = '\n'.join(str(x) for x in d.get('parsed', [])[:18]) or '(채팅 형식으로 해석된 줄이 없습니다)'
        metrics = d.get('metrics', {})
        timings = '\n'.join(f'{k}: {v}' for k,v in metrics.items())
        detail = (f'처리 측정값\n{timings}\n\n캡처 위치: {d.get("region")}\n'
                  f'빨간 확성기 후보 영역: {d.get("red_candidates", 0)}개\n'
                  f'회색 확성기 후보 영역: {d.get("gray_candidates", 0)}개\n'
                  f'발견한 원문 문자: {len(d.get("raw", []))}개\n'
                  f'해석된 채팅: {len(d.get("parsed", []))}줄\n'
                  f'마지막 오류: {self.recent_error or "없음"}\n\n'
                  f'[OCR 원문]\n{raw}\n\n[채팅 추출]\n{parsed}')
        box=QMessageBox(self.left)
        box.setWindowTitle('OCR 진단 · 게임 채팅 확인')
        box.setText('OCR 원문과 채팅 추출 결과를 확인하세요.')
        box.setDetailedText(detail)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def show_sample_message(self):
        # Independent display test: no OCR or model inference. This proves that
        # the floating chat window can render before debugging translation.
        self.chat.put({'nickname':'KAIN_TEST', 'translated':'번역창 표시 확인', 'fresh':True, 'persist':False})
        self.sync_obs()
        if not self.chat.isVisible():
            self.left.set_status('번역창 숨김 · 인식 영역/자석 공간 확인')
        else:
            self.left.set_status('번역창 표시 시험 완료 (OCR/서버와 별개)')

    def open_settings(self):
        # Non-modal: allow actual gameplay while settings remain open.
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        dlg=SettingsDialog(self.cfg,self.left)
        dlg.setModal(False)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        self._settings_dialog=dlg
        # Pin checkbox takes effect immediately while the dialog is still open.
        def pin_now(value):
            self.cfg['pin_settings_above_game']=bool(value)
            self.save()
            self.sync_stack()
        dlg.pin_settings.toggled.connect(pin_now)
        dlg.font_url_requested.connect(self.apply_noonnu_url)
        dlg.history_requested.connect(self.show_history)
        dlg.price_log_requested.connect(self.show_price_log)
        dlg.help_requested.connect(self.show_help)
        dlg.accepted.connect(lambda: self.save_settings_dialog(dlg))
        dlg.finished.connect(lambda _result: self.settings_closed(dlg))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self.sync_stack()

    def show_price_log(self):
        from .classic_windows import PriceLogWindow
        log=self._price_log_store()
        if log is None:
            self.left.set_status('시세 기록 파일을 열지 못했습니다');return
        old=getattr(self,'_price_window',None)
        try:
            if old is not None and old.isVisible():
                old.refresh();old.raise_();old.activateWindow();return
        except RuntimeError:
            pass
        self._price_window=PriceLogWindow(log)
        self._price_window.show();self._price_window.raise_();self._price_window.activateWindow()

    def show_help(self):
        """HOW TO USE poster window (also opened once on the first start)."""
        from .classic_windows import HelpWindow
        old=getattr(self,'_help_window',None)
        try:
            if old is not None and old.isVisible():
                old.raise_();old.activateWindow();return
        except RuntimeError:
            pass
        self._help_window=HelpWindow()
        self._help_window.show();self._help_window.raise_();self._help_window.activateWindow()

    def _price_log_store(self):
        if getattr(self,'_price_log',None) is None:
            try:
                from .price_log import PriceLog
                self._price_log=PriceLog()
            except Exception:
                LOG.exception('price log unavailable')
                return None
        return self._price_log

    def _alerts(self):
        from .chat_alerts import KeywordAlerts
        words=list(self.cfg.get('alert_keywords',[]))
        if getattr(self,'_keyword_alerts',None) is None:
            self._keyword_alerts=KeywordAlerts(words)
        elif self._keyword_alerts.keywords!=words:
            self._keyword_alerts.set_keywords(words)
        return self._keyword_alerts

    def chat_extras(self, message: dict):
        """R18: keyword alert and price log for one translated message."""
        nick=str(message.get('nickname',''))
        original=str(message.get('original',''))
        translated=str(message.get('translated',''))
        if not message.get('fresh',True) or not translated:
            return
        try:
            hit=self._alerts().check(nick,original,translated)
            if hit:
                if self.cfg.get('alert_sound',True):
                    try:
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    except Exception:
                        QApplication.beep()
                if self.cfg.get('alert_popup',True):
                    from .classic_windows import KeywordToast
                    toast=KeywordToast(hit,nick,translated,self.chat.geometry() if self.chat.isVisible() else None)
                    toast.show()
        except Exception:
            LOG.exception('keyword alert failed')
        if self.cfg.get('price_log_enabled',True) and original:
            log=self._price_log_store()
            if log is not None:
                try:
                    log.record(nick,original)
                except Exception:
                    LOG.exception('price log failed')

    def show_history(self):
        if self.history is None:
            self.left.set_status('번역 내역 파일을 열지 못했습니다 · app.log 확인');return
        if self._history_dialog is None:
            self._history_dialog=HistoryDialog(self.history,self.left)
            self._history_dialog.cleared.connect(self.clear_history_display)
        self._history_dialog.refresh()
        self._history_dialog.show();self._history_dialog.raise_();self._history_dialog.activateWindow()

    def clear_history_display(self):
        self.chat.clear_history_display();self.sync_obs()

    def settings_closed(self, dlg):
        if self._settings_dialog is dlg:
            self._settings_dialog=None

    def save_settings_dialog(self, dlg):
        from .chat_alerts import parse_keywords
        self.cfg['alert_keywords']=parse_keywords(dlg.alert_words.toPlainText())
        self.cfg['alert_popup']=dlg.alert_popup.isChecked()
        self.cfg['alert_sound']=dlg.alert_sound.isChecked()
        self.cfg['price_log_enabled']=dlg.price_enabled.isChecked()
        self.cfg['engine']=dlg.engine.currentData()
        self.cfg['opacity']=dlg.opacity.value()
        self.cfg['megaphone_opacity']=dlg.mega_opacity.value()
        self.cfg['game_priority']=dlg.game_priority.isChecked()
        self.cfg['source_chat_colors']=dlg.source_colors.isChecked()
        self.cfg['theme_variant']=normalize_variant(dlg.theme_choice.currentData())
        self.chat.apply_theme(self.cfg['theme_variant'])
        self.left.set_theme_variant(self.cfg['theme_variant'])
        self.right.set_theme_variant(self.cfg['theme_variant'])
        next_mode=dlg.top_mode.currentData()
        self.cfg['top_mode']=next_mode
        self.chat.set_top_mode(next_mode)
        self.cfg['font_size']=dlg.font_size.value()
        # Save URL separately; font is fetched on URL 적용 or upon first launch.
        new_font_url=dlg.font_path.text().strip()
        self.cfg['font_path']=''
        previous_resolution=self.cfg.get('game_resolution','auto')
        self.cfg['game_title_keyword']=dlg.game_title.text().strip() or 'maple'
        self.cfg['game_resolution']=dlg.resolution.currentData()
        self.cfg['capture_backend']=dlg.capture_backend.currentData()
        self.cfg['auto_chat_region']=dlg.auto_chat.isChecked()
        self.cfg['chat_geometry']['dock_match_height']=dlg.match_height.isChecked()
        self.cfg['chat_geometry']['hud_match_height']=dlg.hud_height.isChecked()
        self.cfg['hud_panels_match']=dlg.hud_panels.isChecked()
        self.cfg['chat_geometry']['dock_width']=dlg.dock_width.value()
        self.cfg['pin_settings_above_game']=dlg.pin_settings.isChecked()
        self.cfg['chat_style']=dlg.style_values()
        self.cfg['ocr_scale']=dlg.scale.value()
        self.cfg['glyph_debug_enabled']=dlg.glyph_debug_enabled.isChecked()
        self.cfg['glyph_dictionary_enabled']=dlg.glyph_dictionary_enabled.isChecked()
        self.chat.setWindowOpacity(1.0)
        self.load_font()
        if new_font_url != self.cfg.get('font_url',''):
            self.apply_noonnu_url(new_font_url)
        self.apply_chat_appearance()
        self.sync_obs()
        self.save()
        self.sync_stack()  # apply new always/game/normal mode immediately
        if self.cfg['game_resolution'] != previous_resolution or dlg.auto_requested:
            self.auto_place_from_game()
        if self.worker and self.worker.isRunning():
            self.worker.update_settings(self.cfg)
        self.relayout()

    def test_translation(self):
        self.left.set_status('로컬 번역 모델 시험 중…')
        self.compose_sequence+=1
        seq=self.compose_sequence
        def task():
            try:
                tr=Translator('argos')
                result=tr.offline_test('en-ko')
                result_reverse=tr.offline_test('ko-en')
                self.signals.done.emit(seq, 'TEST:'+result+' / '+result_reverse, '')
            except Exception as exc:
                self.signals.done.emit(seq, 'TEST:', str(exc))
        threading.Thread(target=task,daemon=True,name='maple-offline-model-test').start()

    def translate_to_english(self, text: str):
        self.compose_sequence+=1
        seq=self.compose_sequence
        self.right.busy()
        translator=Translator('argos')
        def task():
            try:
                result=translator.translate(text,'ko-en')
                self.signals.done.emit(seq,result,'')
            except Exception as exc:
                self.signals.done.emit(seq,'',str(exc))
        threading.Thread(target=task,daemon=True,name='maple-compose').start()

    def compose_done(self, seq: int, translation: str, error: str):
        if seq != self.compose_sequence or self.closing:
            return
        if translation.startswith('TEST:'):
            if error:
                self.left.set_status('오프라인 모델 시험 실패: ' + error)
                QMessageBox.warning(self.left,'오프라인 모델 오류',error)
            else:
                self.left.set_status('오프라인 EN↔KO 모델 PASS: ' + translation[5:])
            return
        self.right.finish(translation,error)
        if error:
            self.right.status.setToolTip(error)
            self.left.set_status('입력 번역 실패: ' + error)

    def quit(self):
        self.closing=True
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            if not self.worker.wait(14000):
                self.closing=False
                QMessageBox.information(self.left,'번역 종료 중','진행 중인 번역을 마치는 중입니다. 다시 종료해 주세요.')
                return
        self.save()
        self.obs.close()
        if self.history is not None:self.history.close()
        self.hunt_widget.shutdown()
        self.hunt_widget.close()
        self.chat.close()
        self.right.close()
        self.left.close()
        self.app.quit()


def main():
    if sys.platform=='win32':
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass
    config_path().parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(config_path().parent/'app.log'),
                        format='%(asctime)s %(levelname)s %(message)s',level=logging.WARNING)
    app=QApplication(sys.argv)
    app.setStyle('Fusion')
    # Windows dark mode paints unstyled areas (scroll pages, checkboxes,
    # spin boxes) black under our light stat-window text; use the
    # stat-window colours everywhere instead.
    app.setPalette(CU.light_palette())
    app.setApplicationName('글클메 애드온')
    app.setQuitOnLastWindowClosed(False)
    controller=Controller(app)
    controller.chat.setWindowOpacity(1.0)  # opacity applies to background only, never glyphs
    # Controller keeps windows alive for the app lifetime.
    return app.exec()


if __name__=='__main__':
    sys.exit(main())
