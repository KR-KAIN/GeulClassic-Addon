"""Movable, square-corner session widget with a monotonic hunting timer."""
from __future__ import annotations
import base64
import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, QTimer, QPoint, Qt
from PySide6.QtGui import QImage,QPixmap
from PySide6.QtWidgets import QWidget,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,QFrame,QGridLayout,QApplication,QSizePolicy
from .hunt_stats import HuntSession,parse_exp_text
from .hunt_capture import read_hud_info,find_exp_label_roi,ExpChangeGate
from .hunt_aux import HuntAuxAnalyzer
from .game_window import find_maple_window
from .hunt_zorder import GameRelativeOverlay
from . import visual_theme as T
from . import classic_ui as CU

LOG=logging.getLogger(__name__)

class HuntCaptureThread(QThread):
    observed=Signal(object)
    warning=Signal(str)
    frame_preview=Signal(bytes)
    def __init__(self,game_keyword='maple',backend='wgc',parent=None,keyboard_relative=None):
        super().__init__(parent)
        self.keyword=game_keyword
        self.backend=backend
        self._stopping=threading.Event()
        self._keyboard_relative=keyboard_relative
        self._aux=None
        self._preview_requested=False
        self._redetect_requested=False
    def request_keyboard_preview(self):
        self._preview_requested=True
    def set_keyboard_relative(self, relative):
        self._keyboard_relative=relative
        if self._aux:self._aux.reconfigure(relative)
    def redetect_keyboard(self):
        if self._aux:self._aux.redetect()
        else:self._redetect_requested=True
    def stop(self):
        self._stopping.set()
    def run(self):
        from .vision import TextRecognizer
        from .wgc_capture import WgcWindowSource
        recognizer=None
        wgc=None
        hwnd=None
        preferred=self.backend
        active=preferred
        next_wgc_retry=0.0
        next_exp=0.0
        next_aux_frame=0.0
        exp_gate=ExpChangeGate(minimum_interval=.20,verify_interval=1.15,retry_interval=.35)
        last_shape=None
        game_lost_notice=False
        game=None
        next_game_probe=0.0
        last_game_rect=None
        try:
            while not self._stopping.is_set():
                now=time.monotonic()
                if now>=next_game_probe or game is None:
                    game=find_maple_window(keyword=self.keyword,preferred_hwnd=hwnd or 0)
                    next_game_probe=now+.85
                if game is None:
                    if not game_lost_notice:
                        self.warning.emit('메이플 게임 창 검색 중 · 타이머는 계속됩니다')
                    game_lost_notice=True
                    self._stopping.wait(.5)
                    continue
                game_lost_notice=False
                x,y,w,h=game.rect
                region={'left':x,'top':y,'width':w,'height':h}
                if hwnd != game.hwnd:
                    if wgc is not None:wgc.close();wgc=None
                    hwnd=game.hwnd
                    last_shape=None
                    exp_gate.reset()
                    if self._aux:self._aux.redetect()
                    last_game_rect=None
                if active=='mss' and preferred=='wgc' and now>=next_wgc_retry:
                    active='wgc'
                    self.warning.emit('경험치 측정기 · WGC 다시 연결 중')
                try:
                    if active=='wgc':
                        if wgc is None:
                            wgc=WgcWindowSource(game.hwnd,game.rect,region,max_pending=3,
                                                minimum_update_interval=100)
                            wgc.start()
                        elif last_game_rect!=game.rect:
                            wgc.set_geometry(game.rect,region)
                        last_game_rect=game.rect
                        item=wgc.get(timeout=.35)
                        if item is None:
                            # WGC may legitimately be idle for seconds when
                            # the game frame is static; an idle event stream
                            # is not a capture failure.
                            if wgc.finished or (wgc.started_at and
                                    now-wgc.started_at>5 and wgc.arrivals==0):
                                detail=str(wgc.error or '프레임 시간 초과')[:65]
                                self.warning.emit('WGC 캡처 끊김 · MSS 임시 전환: '+detail)
                                wgc.close();wgc=None
                                active='mss';next_wgc_retry=time.monotonic()+15.
                            continue
                        image,_,_=item
                    else:
                        import mss
                        with mss.mss() as grabber:
                            raw=np.asarray(grabber.grab(region))
                            image=raw[:,:,:3].copy()
                except Exception as exc:
                    self.warning.emit('게임 캡처 실패 · MSS 임시 사용: '+str(exc)[:70])
                    if wgc is not None:wgc.close();wgc=None
                    active='mss';next_wgc_retry=time.monotonic()+15.
                    self._stopping.wait(.25)
                    continue
                now=time.monotonic()
                if image is None or image.size==0:continue
                if image.shape[:2]!=last_shape:
                    last_shape=image.shape[:2]
                    exp_gate.reset()
                    if self._aux:self._aux.redetect()
                if self._preview_requested:
                    self._preview_requested=False
                    ok,jpeg=cv2.imencode('.jpg',image,[int(cv2.IMWRITE_JPEG_QUALITY),86])
                    if ok:self.frame_preview.emit(jpeg.tobytes())
                # The HUD is the primary measurement. Do not delay EXP OCR
                # behind the auxiliary potion-count crops.
                if now>=next_exp and exp_gate.should_read(image,now):
                    next_exp=now+.20
                    if recognizer is None:
                        try:recognizer=TextRecognizer()
                        except Exception as exc:
                            self.warning.emit('통계 OCR 초기화 실패: '+str(exc)[:90])
                            recognizer=False
                    if recognizer:
                        level,exp,pct,exp_diag=read_hud_info(recognizer,image)
                        exp_gate.result(exp is not None,time.monotonic())
                        self.observed.emit({'level':level,'exp':exp,'pct':pct,
                                            'exp_diag':exp_diag,'capture_mode':active,
                                            'exp_roi_found':bool(find_exp_label_roi(image)),
                                            'frame_size':(image.shape[1],image.shape[0]),
                                            'frame_ok':True})
                    else:
                        self.observed.emit({'frame_ok':True,'capture_mode':active,
                                            'frame_size':(image.shape[1],image.shape[0])})
                    # OCR failure means OCR failed. It does NOT mean WGC
                    # failed: do not replace valid HWND capture with MSS.
                # Expensive potion-count OCR runs on its own worker.
                # Replacing an unprocessed frame is intentional: EXP remains
                # scheduled on this capture thread without waiting for potion OCR.
                if self._aux is None:
                    self._aux=HuntAuxAnalyzer(self.observed.emit,self.warning.emit,
                                             self._keyboard_relative,self._stopping)
                    if self._redetect_requested:
                        self._aux.redetect();self._redetect_requested=False
                if now>=next_aux_frame:
                    next_aux_frame=now+.38
                    self._aux.publish(image,active)
                self._stopping.wait(.025)
        except Exception as exc:
            LOG.exception('Hunt capture thread stopped')
            self.warning.emit('경험치 측정기 캡처 스레드 오류: '+str(exc)[:95])
        finally:
            if self._aux:
                self._aux.stop()
            if wgc is not None:wgc.close()

class HuntWindow(QWidget):
    def __init__(self, config, save_config_fn=None):
        super().__init__(None)
        self.cfg=config
        self.on_save=save_config_fn
        self.session=HuntSession()
        self.capture=None
        self._preflight_slots={}
        self.setWindowTitle('글클메 경험치 측정기')
        # A normal movable window by default; pinning is the user's choice.
        # v0.4.50: older sessions could persist a global TOPMOST flag even
        # when the user expected the ordinary Maple-relative panel behavior.
        # One-time migration defaults the tracker to game-only stacking;
        # a deliberate new click on '고정 ON' still opts into global pinning.
        if not self.cfg.get('hunt_window_order_v050_migrated',False):
            self.cfg['hunt_widget_always_on_top']=False
            self.cfg['hunt_window_order_v050_migrated']=True
            if self.on_save:self.on_save()
        self._pinned=bool(self.cfg.get('hunt_widget_always_on_top',False))
        self._relative_zorder=GameRelativeOverlay()
        self._known_game_hwnd=0
        self._next_game_probe=0.0
        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.setObjectName('huntRoot')
        # Pre-Big Bang CHARACTER STAT window: white title strip, light body,
        # pink/lime label pills, beige value cells, steel-blue bottom strip.
        self.setStyleSheet(f'''QWidget#huntRoot{{background:{T.FRAME};border:1px solid {T.OUTLINE};}}
            QWidget{{font-family:'Malgun Gothic','Segoe UI';}}
            QLabel{{color:{T.TEXT};background:transparent;border:0px;}}
            QFrame#huntTitle{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #e9eef3);
                border:0px;border-bottom:1px solid {T.TITLE_LINE};}}
            QLabel#huntTitleText{{color:#3a4652;font-size:10px;font-weight:800;letter-spacing:1px;}}
            QLabel#huntState{{color:{T.SUBTLE};font-size:10px;font-weight:700;}}
            QFrame#huntBody{{background:{T.BODY};border:1px solid {T.TITLE_LINE};}}
            QLabel#pinkPill{{{T.pill_css(T.PINK,T.PINK_DARK)}font-size:10px;}}
            QLabel#limePill{{{T.pill_css(T.LIME,T.LIME_DARK)}font-size:9px;padding:1px 3px;}}
            QLabel#huntTime,QLabel#huntExp{{background:{T.VALUE};border:1px solid {T.VALUE_EDGE};
                border-radius:2px;padding:1px 6px;font-size:15px;font-weight:800;color:{T.TEXT};}}
            QLabel#huntExp{{color:#2f7a14;}}
            QLabel#slotIcon{{background:#ffffff;border:1px solid {T.VALUE_EDGE};border-radius:2px;color:#b9bec4;}}
            QLabel#slotCount{{font-size:13px;font-weight:800;color:{T.TEXT};}}
            QLabel#slotUsed{{font-size:10px;font-weight:800;color:{T.USED};}}
            QLabel#huntHeading{{font-size:10px;color:{T.SUBTLE};}}
            QFrame#huntStrip{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {T.STRIP},stop:1 {T.STRIP_DARK});
                border:0px;border-top:1px solid {T.STRIP_DARK};}}
            QLabel#huntHint{{color:#ffffff;font-size:10px;font-weight:700;}}
            {T.button_css('QPushButton',T.BLUE,T.BLUE_DARK,3)}
            QPushButton{{padding:2px 4px;}}
            {T.button_css('QPushButton#limeBtn',T.LIME,T.LIME_DARK,3)}
            {T.button_css('QPushButton#pinkBtn',T.PINK,T.PINK_DARK,3)}
            QPushButton#closeBtn{{background:{T.CLOSE};border:1px solid #1d6d97;border-radius:2px;padding:0px;font-size:12px;}}
            QPushButton#pinBtn{{font-size:10px;padding:0px 3px;}}
            ''')
        # The Qt widgets below hold the state and actions (and stay testable);
        # they live in a hidden container. What the user sees is painted from
        # the game's own CHARACTER STAT pieces (classic_ui) in paintEvent.
        self._model=QWidget(self);self._model.hide()
        self._hover=None;self._press=None;self._hotspots={}
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        layout=QVBoxLayout(self._model)
        layout.setContentsMargins(3,3,3,3)
        layout.setSpacing(0)
        title_bar=QFrame();title_bar.setObjectName('huntTitle')
        header=QHBoxLayout(title_bar);header.setContentsMargins(6,3,3,3);header.setSpacing(3)
        self.title=QLabel('EXP METER  ·  경험치 측정기')
        self.title.setObjectName('huntTitleText')
        header.addWidget(self.title,1)
        self.state=QLabel('대기');self.state.setObjectName('huntState')
        header.addWidget(self.state)
        self.pin_btn=QPushButton('고정 ON' if self._pinned else '게임 위')
        self.pin_btn.setObjectName('pinBtn')
        self.pin_btn.setToolTip('기본: 메이플 창 위의 일반 창(다른 프로그램을 가리지 않음) / 고정 ON: 모든 창 위')
        self.pin_btn.setFixedSize(52,18)
        self.pin_btn.clicked.connect(self.toggle_pin)
        header.addWidget(self.pin_btn)
        self.close_btn=QPushButton('×');self.close_btn.setFixedSize(18,18)
        self.close_btn.setObjectName('closeBtn')
        self.close_btn.clicked.connect(self.request_hide)
        header.addWidget(self.close_btn)
        layout.addWidget(title_bar)

        body=QFrame();body.setObjectName('huntBody')
        body_layout=QVBoxLayout(body);body_layout.setContentsMargins(6,6,6,6);body_layout.setSpacing(4)
        layout.addWidget(body)
        counters=QGridLayout();counters.setHorizontalSpacing(4);counters.setVerticalSpacing(3)
        def metric(row,title,object_name,initial):
            head=QLabel(title);head.setObjectName('pinkPill');head.setFixedWidth(64)
            head.setAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            value=QLabel(initial);value.setObjectName(object_name)
            counters.addWidget(head,row,0);counters.addWidget(value,row,1)
            return value
        self.timer_text=metric(0,'사냥 시간','huntTime','00:00:00')
        self.exp_label=metric(1,'획득 EXP','huntExp','—')
        body_layout.addLayout(counters)
        self.minutes=QLabel('0분 0초 사냥')
        self.minutes.hide()
        self.exp_info=QLabel('EXP 인식 대기')
        self.exp_info.hide()
        self.history_label=QLabel('이전 물약: 0개')
        self.history_label.hide()

        self.potion_row=QHBoxLayout();self.potion_row.setSpacing(3)
        self.potion_heading=QLabel('맨 아래 4칸 · 수량 인식 대기')
        self.potion_heading.setObjectName('huntHeading')
        self.potion_row.addWidget(self.potion_heading)
        self.slot_icons={};self.slot_labels={};self.slot_views={}
        self.slot_widgets={};self.extra_rows=[]
        for key in ('Ctrl','Del','End','PgDn'):
            self._show_slot(key,None)
        separator=QFrame();separator.setFixedHeight(1)
        separator.setStyleSheet(f'background:{T.TITLE_LINE};border:0px;')
        body_layout.addWidget(separator)
        body_layout.addLayout(self.potion_row)
        # Potions on 1-4 / Q-R keys appear here once their count is read.
        self.extra_box=QVBoxLayout();self.extra_box.setSpacing(1)
        body_layout.addLayout(self.extra_box)
        strip=QFrame();strip.setObjectName('huntStrip')
        strip_layout=QVBoxLayout(strip);strip_layout.setContentsMargins(5,4,5,3);strip_layout.setSpacing(2)
        layout.addWidget(strip)
        actions=QHBoxLayout();actions.setSpacing(3)
        self.start_btn=QPushButton('▶ 시작');self.stop_btn=QPushButton('■ 종료')
        self.start_btn.setObjectName('limeBtn');self.stop_btn.setObjectName('pinkBtn')
        self.start_btn.setFixedHeight(23);self.stop_btn.setFixedHeight(23)
        self.start_btn.clicked.connect(self.start_session)
        self.stop_btn.clicked.connect(self.stop_session)
        self.stop_btn.setEnabled(False)
        actions.addWidget(self.start_btn);actions.addWidget(self.stop_btn)
        self.redetect_btn=QPushButton('재인식')
        self.redetect_btn.setText('인식')
        self.redetect_btn.setFixedHeight(23)
        self.redetect_btn.setToolTip('퀵슬롯 위치와 아이콘을 다시 탐색합니다.')
        self.redetect_btn.clicked.connect(self.redetect_slots)
        actions.addWidget(self.redetect_btn)
        self.auto_btn=QPushButton('자동')
        self.auto_btn.setFixedHeight(23)
        self.auto_btn.setToolTip('수동 지정 위치를 해제하고 단축키 패널을 자동으로 찾습니다.')
        self.auto_btn.clicked.connect(self.reset_auto_slots)
        actions.addWidget(self.auto_btn)
        self.pick_btn=QPushButton('영역 지정')
        self.pick_btn.setFixedHeight(23)
        self.pick_btn.setToolTip('게임 화면에서 단축키 4열×3행 패널을 선택합니다.')
        self.pick_btn.clicked.connect(self.pick_keyboard)
        actions.addWidget(self.pick_btn)
        self.hint=QLabel('시작을 누르면 메이플 화면 자동 분석')
        self.hint.setObjectName('huntHint')
        strip_layout.addLayout(actions)
        strip_layout.addWidget(self.hint)
        self._drag=None
        pos=self.cfg.get('hunt_widget_pos')
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import QPoint
        if (isinstance(pos,(list,tuple)) and len(pos)==2
                and QGuiApplication.screenAt(QPoint(int(pos[0])+20,int(pos[1])+20)) is not None):
            self.move(int(pos[0]),int(pos[1]))
        else:
            # first start / monitor gone: the main screen, lower middle
            area=QGuiApplication.primaryScreen().availableGeometry()
            self.move(area.left()+area.width()//2-160,area.top()+int(area.height()*.62))
        self.tick=QTimer(self);self.tick.setInterval(200)
        self.tick.timeout.connect(self.update_clock);self.tick.start()
        self.zorder_tick=QTimer(self)
        self.zorder_tick.setInterval(350)
        self.zorder_tick.timeout.connect(self._sync_game_zorder)
        self.zorder_tick.start()
        self.setFixedSize(CU.Canvas(self.NATIVE_W,self.NATIVE_H).pixmap(scale=self.SKIN_SCALE).size())

    # ------------------------------------------------------------------
    # Classic (pre-Big Bang) skin, native 1366x768 pixels stretched like the game
    NATIVE_W=248;NATIVE_H=122    # flat wide stat window: TIME/EXP, potions, RATE/NEXT, buttons
    # Shown at 1.2x instead of the game's 1.4056x so the meter stays small.
    SKIN_SCALE=(1.2,1.2)
    SLOT_PILLS={'Ctrl':'CTRL','Del':'DEL','End':'END','PgDn':'PGDN'}
    KEY_LABELS={'Ctrl':'Ctrl','Del':'Del','End':'End','PgDn':'Pdn'}  # as printed on the game's keys
    SUB=(102,102,153)   # BGR of the stat window's grey-red sub line (SWORDMAN)

    def _state(self,key,enabled=True):
        if not enabled:return 'disabled'
        if self._press==key:return 'pressed'
        return 'hover' if self._hover==key else 'normal'

    def _compose(self):
        W,H=self.NATIVE_W,self.NATIVE_H
        c=CU.Canvas(W,H);c.frame(strip=True);hs={}
        c.title(7,9,'EXP METER')
        # X and 고정 share one 14px row inside the title band; the X sprite
        # (12px square, below its white top row) is stretched by its edges.
        cx=W-18;ty=5;bh=12
        c.ui_button(cx-28,ty,25,bh,'고정','pressed' if self._pinned else self._state('pin'),'orange',px=11)
        hs['pin']=(cx-28,ty,25,bh)
        c.close_button(cx,ty,self._state('close'))     # the game's blue X (BtClose)
        hs['close']=(cx,ty,bh,bh)
        # state next to the title; the full hint is the title's tooltip
        # State in the title's own pixel font, so it sits exactly on the
        # EXP METER line; the Korean wording is the tooltip.
        state=self.state.text()
        word=('SCANNING' if '인식' in state else 'RUNNING' if '측정' in state
              else 'STOPPED' if '종료' in state else 'READY')
        c.title(64,9,word,(70,70,170))
        hs['state']=(60,4,cx-27-62,14)
        # line 1: TIME and EXP side by side, large (the point of the meter)
        y=30;half=(W-14-4)//2
        c.pill('pink',7,y,30,20,'TIME');c.cell(39,y+1,half-32,19)
        c.big_text(45,y+1,19,CU.fit_text(self.timer_text.text(),half-42,True,14),(0,0,0),px=14)
        ex=7+half+4
        c.pill('pink',ex,y,30,20,'EXP.');c.cell(ex+32,y+1,W-7-ex-32,19)
        # gain since 시작; the % is added when it fits the cell
        room=W-7-ex-46;full=getattr(self,'_exp_full',self.exp_label.text())
        shown=full if CU.text_width(full,True,14)<=room else self.exp_label.text()
        c.big_text(ex+38,y+1,19,CU.fit_text(shown,room,True,14),(0,0,0),px=14)
        hs['exp']=(ex,y,W-7-ex,20)
        # line 2: the four keys in one small line: game key name (Ctrl/Del/
        # End/Pdn), small icon and count in the quickslot digits (3/4 size).
        # Potions used are in each slot's tooltip.
        y=53;gap=2;sw=(W-14-3*gap)//4
        for i,key in enumerate(self.SLOT_PILLS):
            x=7+i*(sw+gap)
            # small key name, bigger potion and count
            c.key_pill('lime',x,y+2,23,12,self.KEY_LABELS[key]);c.cell(x+24,y,sw-24,16)
            pix=self.slot_icons[key].pixmap() if key in self.slot_icons else None
            c.icon_fit(pix,x+25,y+1,14)
            count=self.slot_labels[key].text() if key in self.slot_labels else '—'
            plain=count.replace(',','')
            if plain.isdigit():
                # R18: at or below the warning count the digits turn red
                low=key in getattr(self,'_low_slots',set())
                c.count_digits(x+40,y+3,plain,scale=0.9,tint=(60,60,235) if low else None)
            else:
                c.text(x+41,y+2,CU.fit_text(count,sw-42),(0,0,0))
            hs['slot:'+key]=(x,y,sw,16)
        # line 3 (R18): EXP per hour and time to the next level, at this pace
        from .hunt_extras import exp_per_hour,level_up_seconds,format_amount,format_duration
        y=72;half=(W-14-4)//2
        rate=exp_per_hour(self.session) if self.session.running or self.session.finished_at else None
        eta=level_up_seconds(self.session) if self.session.running else None
        c.pill('blue',7,y,30,16,'RATE');c.cell(39,y,half-32,16)
        c.text(44,y+2,CU.fit_text(format_amount(rate) if rate else '—',half-42,True),(0,0,0),bold=True)
        hs['rate']=(7,y,half,16)
        ex=7+half+4
        c.pill('blue',ex,y,30,16,'NEXT');c.cell(ex+32,y,W-7-ex-32,16)
        c.text(ex+37,y+2,CU.fit_text(format_duration(eta) if eta is not None else '—',W-7-ex-42,True),(0,0,0),bold=True)
        hs['next']=(ex,y,W-7-ex,16)
        # line 4: the game's lime buttons
        # Only the everyday actions; 자동/영역 live in the right-click menu.
        buttons=(('start','시작',self.start_btn),('stop','종료',self.stop_btn),
                 ('scan',self.redetect_btn.text(),self.redetect_btn))
        # buttons sit on the steel-blue bottom strip with a little air,
        # like the buddy list's ADD / DELETE / MY STATUS row
        gap=4;bw=(W-16-(len(buttons)-1)*gap)//len(buttons)
        # centred in the strip: its inside is rows H-26..H-4 (23 px), the
        # buttons the game's own 18 px; horizontally the leftover splits evenly.
        bh=18;by=H-34+8+(23-bh)//2
        x0=(W-(len(buttons)*bw+(len(buttons)-1)*gap))//2
        for i,(key,label,btn) in enumerate(buttons):
            x=x0+i*(bw+gap)
            # Korean labels in Gulim with the dark rim, on the game's lime button.
            c.ui_button(x,by,bw,bh,label,self._state(key,btn.isEnabled()),'lime')
            hs[key]=(x,by,bw,bh)
        self._hotspots=hs
        return c

    def paintEvent(self,event):
        from PySide6.QtGui import QPainter
        p=QPainter(self)
        p.drawPixmap(0,0,self._compose().pixmap(size=(self.width(),self.height())))
        p.end()

    def _native(self,pos):
        return pos.x()*self.NATIVE_W/max(1,self.width()),pos.y()*self.NATIVE_H/max(1,self.height())

    def _hit(self,pos):
        nx,ny=self._native(pos)
        for key,(x,y,w,h) in self._hotspots.items():
            if x<=nx<x+w and y<=ny<y+h:return key
        return None

    def _tooltip_for(self,key):
        if key is None:return ''
        if key.startswith('slot:'):
            slot=key[5:]
            detail=self.slot_labels[slot].toolTip() or self.slot_icons[slot].toolTip()
            return self.KEY_LABELS.get(slot,slot)+' 키 · '+detail if detail else self.KEY_LABELS.get(slot,slot)+' 키'
        return {'pin':self.pin_btn.toolTip(),'close':'닫기','start':'측정 시작','stop':'측정 종료',
                'scan':self.redetect_btn.toolTip(),'auto':self.auto_btn.toolTip(),
                'area':self.pick_btn.toolTip(),'exp':getattr(self,'_exp_tip','시작을 누른 뒤 오른 경험치를 보여줍니다'),
                'rate':self._rate_tip(),'next':self._next_tip(),'state':self.state.text()+' · '+self.hint.text()}.get(key,'')

    def request_hide(self):
        """Hide the meter unless a measurement is running (R18)."""
        if self.session.running:
            self.hint.setText('측정 중에는 닫을 수 없습니다 · 먼저 종료를 누르세요')
            self.state.setToolTip(self.hint.text())
            self.show();self.raise_()
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
            self.update()
            return False
        self.hide()
        return True

    def _rate_tip(self):
        from .hunt_extras import exp_per_hour
        rate=exp_per_hour(self.session)
        return ('시간당 경험치: '+f'{rate:,}' if rate else '시간당 경험치 · 시작 후 20초부터 계산')

    def _next_tip(self):
        from .hunt_extras import level_up_seconds,format_duration
        eta=level_up_seconds(self.session)
        if eta is None:
            return '다음 레벨까지 예상 시간 · 경험치가 오르면 계산'
        return f'지금 속도면 다음 레벨까지 약 {format_duration(eta)}'

    def _check_potions(self):
        """R18: red count and one beep when a stack reaches the warning count."""
        from .hunt_extras import low_potion_slots
        limit=int(self.cfg.get('hunt_potion_warn',30) or 0)
        low=set(low_potion_slots(self.session,limit)) if self.session.running else set()
        fresh=low-getattr(self,'_low_slots',set())
        self._low_slots=low
        if fresh:
            from PySide6.QtWidgets import QApplication
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                QApplication.beep()
            names=', '.join(self.KEY_LABELS.get(k,k) for k in sorted(fresh))
            self.hint.setText(f'물약 부족 · {names} {limit}개 이하')

    def _set_potion_warn(self,value):
        self.cfg['hunt_potion_warn']=int(value)
        if self.on_save:self.on_save()
        self._low_slots=set();self._check_potions();self.update()

    def show_hunt_log(self):
        from .classic_windows import HuntLogWindow
        self._log_window=HuntLogWindow(self)
        self._log_window.show();self._log_window.raise_()

    def _activate(self,key):
        if key=='pin':self.toggle_pin()
        elif key=='close':self.request_hide()
        elif key=='start' and self.start_btn.isEnabled():self.start_btn.click()
        elif key=='stop' and self.stop_btn.isEnabled():self.stop_btn.click()
        elif key=='scan':self.redetect_btn.click()
        elif key=='auto':self.auto_btn.click()
        elif key=='area':self.pick_btn.click()

    def _apply_window_flags(self):
        flags=Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if self._pinned: flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _sync_game_zorder(self):
        """Keep the tracker over Maple using normal, non-topmost Z-order.

        Native SetWindowPos(SWP_NOACTIVATE) adjusts z-order only; it never
        activates the tracker or steals keyboard focus from the game.
        Manual pin mode is deliberately left to Qt's topmost window flag.
        """
        if self._pinned or not self.isVisible():
            self._relative_zorder.release(self)
            return
        if getattr(self,'stacked_by_app',False):
            return   # R18: the app keeps it above the chat window (sync_stack)
        now=time.monotonic()
        if now>=self._next_game_probe or not self._relative_zorder.is_game_window(self._known_game_hwnd):
            self._next_game_probe=now+1.5
            try:
                target=find_maple_window(preferred_hwnd=self._known_game_hwnd,
                                         keyword=self.cfg.get('game_title_keyword','maple'))
                self._known_game_hwnd=target.hwnd if target else 0
            except Exception:
                self._known_game_hwnd=0
        self._relative_zorder.sync(self,self._known_game_hwnd)

    def showEvent(self,event):
        super().showEvent(event)
        # On initial show, the game may be the foreground window already.
        QTimer.singleShot(0,self._sync_game_zorder)

    def hideEvent(self,event):
        self._relative_zorder.release(self)
        super().hideEvent(event)

    def toggle_pin(self):
        previous=self.pos()
        was_visible=self.isVisible()
        self._relative_zorder.release(self)
        self._pinned=not self._pinned
        self.cfg['hunt_widget_always_on_top']=self._pinned
        if self.on_save:self.on_save()
        self._apply_window_flags()
        self.move(previous)
        self.pin_btn.setText('고정 ON' if self._pinned else '게임 위')
        if was_visible:
            self.show()
            self._sync_game_zorder()

    # Keys above the bottom row, in keyboard order, with the labels the
    # Classic keyboard UI shows (middle row: Q W E R).
    EXTRA_SLOT_LABELS={'1':'1','2':'2','3':'3','4':'4',
                       'Shift':'Q','Ins':'W','Hm':'E','Pup':'R'}

    def _extra_row_for(self,key):
        """Rows of four under the bottom-row potions, filled as keys appear."""
        rows=self.extra_rows
        if not rows or rows[-1].count()>=4:
            row=QHBoxLayout();row.setSpacing(3)
            self.extra_box.addLayout(row)
            rows.append(row)
        return rows[-1]

    def _set_slot_visible(self,key,visible):
        for widget in self.slot_widgets.get(key,()):
            widget.setVisible(visible)

    def _show_slot(self,key,blob):
        """Bottom-row keys stay fixed; other keys appear when they hold a count."""
        if key not in ('Ctrl','Del','End','PgDn') and key not in self.EXTRA_SLOT_LABELS:
            return
        if not hasattr(self,'slot_widgets'):
            self.slot_widgets={}
        if key not in self.slot_views:
            # Fix ordering independently of which slot the OCR discovers first.
            # Stat-window style: lime key pill above the icon, count beside it.
            holder=QHBoxLayout();holder.setSpacing(2)
            title=QLabel(self.EXTRA_SLOT_LABELS.get(key,key))
            title.setObjectName('limePill')
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon=QLabel('□');icon.setFixedSize(34,34)
            icon.setObjectName('slotIcon')
            icon.setMargin(0);icon.setContentsMargins(0,0,0,0)
            icon.setScaledContents(False)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left=QVBoxLayout();left.setSpacing(1);left.setContentsMargins(0,0,0,0)
            left.addWidget(title);left.addWidget(icon,0,Qt.AlignmentFlag.AlignHCenter)
            number=QLabel('—')
            number.setObjectName('slotCount')
            number.setMinimumWidth(20)
            # Potions used since 시작, right under the remaining count.
            used=QLabel('')
            used.setObjectName('slotUsed')
            numbers=QVBoxLayout();numbers.setSpacing(0);numbers.setContentsMargins(0,0,0,0)
            numbers.addStretch(1);numbers.addWidget(number);numbers.addWidget(used);numbers.addStretch(1)
            holder.addLayout(left);holder.addLayout(numbers)
            if not hasattr(self,'slot_used'):self.slot_used={}
            self.slot_used[key]=used
            if key in self.EXTRA_SLOT_LABELS:
                self._extra_row_for(key).addLayout(holder,1)
                self.adjustSize()
            else:
                self.potion_row.addLayout(holder,1)
            self.slot_views[key]=holder;self.slot_icons[key]=icon
            self.slot_labels[key]=number
            self.slot_widgets[key]=(title,icon,number,used)
            self.potion_heading.hide()
        self._set_slot_visible(key,True)
        if blob:
            im=QImage.fromData(blob,'PNG')
            if not im.isNull():
                # Native game sprites fit inside 32px. Preserve every source
                # pixel instead of resampling a 30px bottle to 27px.
                pix=QPixmap.fromImage(im)
                if pix.width()>32 or pix.height()>32:
                    pix=pix.scaled(32,32,Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.FastTransformation)
                self.slot_icons[key].setPixmap(pix)
                self.slot_icons[key].setToolTip('내장 물약 PNG')
        else:
            self.slot_icons[key].clear()
            self.slot_icons[key].setText('□')
            self.slot_icons[key].setToolTip('빈 칸 또는 아이템 미확인')

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:
            super().mousePressEvent(event);return
        key=self._hit(event.position().toPoint())
        if key is not None and not key.startswith('slot:') and key!='state':
            self._press=key;self.update();event.accept();return
        if self._native(event.position().toPoint())[1]<20:
            # Title band drags the window, like the game's own windows.
            self._drag=event.globalPosition().toPoint()-self.frameGeometry().topLeft()
            event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint()-self._drag);event.accept();return
        key=self._hit(event.position().toPoint())
        if key!=self._hover:
            self._hover=key;self.update()
            from PySide6.QtWidgets import QToolTip
            tip=self._tooltip_for(key)
            if tip:QToolTip.showText(event.globalPosition().toPoint(),tip,self)
            else:QToolTip.hideText()
        super().mouseMoveEvent(event)
    def contextMenuEvent(self,event):
        """Rarely needed keyboard-panel options, kept off the meter itself."""
        from PySide6.QtWidgets import QMenu
        menu=QMenu(self)
        auto=menu.addAction('단축키 위치 자동으로 찾기')
        auto.setToolTip(self.auto_btn.toolTip())
        area=menu.addAction('단축키 영역 직접 지정')
        area.setToolTip(self.pick_btn.toolTip())
        menu.addSeparator()
        log=menu.addAction('사냥 기록 보기')
        warn=menu.addMenu('물약 부족 알림')
        current=int(self.cfg.get('hunt_potion_warn',30) or 0)
        choices={}
        for value in (0,10,20,30,50,100,200):
            act=warn.addAction('끄기' if value==0 else f'{value}개 이하')
            act.setCheckable(True);act.setChecked(value==current)
            choices[act]=value
        menu.setToolTipsVisible(True)
        chosen=menu.exec(event.globalPos())
        if chosen is auto:self.auto_btn.click()
        elif chosen is area:self.pick_btn.click()
        elif chosen is log:self.show_hunt_log()
        elif chosen in choices:self._set_potion_warn(choices[chosen])

    def leaveEvent(self,event):
        self._hover=None;self.update();super().leaveEvent(event)
    def mouseReleaseEvent(self,event):
        if self._press is not None:
            key=self._press;self._press=None;self.update()
            if self._hit(event.position().toPoint())==key:self._activate(key)
            return
        if self._drag is not None:
            self._drag=None
            self.cfg['hunt_widget_pos']=[self.x(),self.y()]
            if self.on_save:self.on_save()
            event.accept()
        else:super().mouseReleaseEvent(event)

    def redetect_slots(self):
        if self.capture is None or not self.capture.isRunning():
            self._start_preview()
            return
        # Never silently forget a user-calibrated rectangle.  Re-capture the
        # icon/count at that location; automatic mode can be restored alone.
        if self.capture is not None and self.capture.isRunning():
            self.capture.redetect_keyboard()
        self._found_keyboard=False
        if not self.session.running:
            self._preflight_slots.clear()
            for label in self.slot_labels.values():label.setText('—')
        self.hint.setText('단축키 재인식 요청 · 아이콘·수량 갱신 중')

    def _start_preview(self):
        """Start OCR preview without advancing time, EXP or potion consumption."""
        self._preflight_slots.clear()
        self.capture=HuntCaptureThread(self.cfg.get('game_title_keyword','maple'),
                        self.cfg.get('capture_backend','wgc'),self,
                        keyboard_relative=self.cfg.get('hunt_keyboard_roi_rel'))
        self.capture.observed.connect(self.receive)
        self.capture.warning.connect(self.report_warning)
        self.capture.frame_preview.connect(self.open_keyboard_picker)
        self.capture.start()
        if not self.session.running:
            self.state.setText('● 물약 인식 중')
            self.hint.setText('현재 물약 아이콘 및 남은 수량 인식 · 시작 전 확인')

    def reset_auto_slots(self):
        self.cfg.pop('hunt_keyboard_roi_rel',None)
        if self.on_save:self.on_save()
        if self.capture is not None and self.capture.isRunning():
            self.capture.set_keyboard_relative(None)
            self.capture.redetect_keyboard()
        self._found_keyboard=False
        self.hint.setText('단축키 자동 탐색으로 복귀')

    def pick_keyboard(self):
        if self.capture is None or not self.capture.isRunning():
            self._start_preview()
        self.hint.setText('게임 캡처 이미지 준비 중 · 단축키 패널 선택')
        self.capture.request_keyboard_preview()

    def open_keyboard_picker(self, jpeg):
        from .hunt_picker import KeyboardPicker
        try:
            picker=KeyboardPicker(jpeg,self)
            if picker.exec():
                relative=picker.selected()
                if relative is not None:
                    self.cfg['hunt_keyboard_roi_rel']=relative
                    if self.on_save:self.on_save()
                    if self.capture:self.capture.set_keyboard_relative(relative)
                    self._found_keyboard=False
                    self.hint.setText('단축키 영역 수동 지정 완료 · 수량 확인 중')
        except Exception as exc:
            self.report_warning('단축키 영역 선택 실패: '+str(exc)[:75])

    def start_session(self):
        if self.session.running:return
        self.session.start()
        self.state.setText('● 측정 중')
        self.exp_label.setText('+0')
        self._exp_full='+0'
        self._exp_tip='시작 시점 경험치를 읽는 중입니다'
        self.history_label.setText('이전 물약: 0개')
        self.exp_info.setText('게임 EXP 기준값 분석 중')
        self._last_capture_mode='—'
        self._exp_diagnostic='대기'
        self._last_frame_size=None
        self._last_roi_status=None
        self._found_keyboard=False
        for label in self.slot_labels.values():
            if label.text() == '—':label.setText('확인 중')
        for key,used in getattr(self,'slot_used',{}).items():
            used.setText('사용 0개' if key in self._preflight_slots else '')
        self.start_btn.setEnabled(False);self.stop_btn.setEnabled(True)
        for slot,data in self._preflight_slots.items():
            if data.get('count') is not None:
                # HuntSession confirms a visual icon twice before anchoring.
                self.session.observe_slot(slot,data['icon'],data['count'])
                self.session.observe_slot(slot,data['icon'],data['count'])
        if self.capture is None or not self.capture.isRunning():
            self._start_preview()
        self.redetect_btn.setText('재인식')
        self.update_clock()

    def stop_session(self):
        was_running=self.session.running
        self.session.finish()
        if was_running:
            # R18: every finished hunt goes into the hunting log
            from .hunt_extras import session_record,append_hunt
            append_hunt(session_record(self.session))
        self._low_slots=set()
        self.state.setText('■ 종료')
        self.state.setToolTip('측정 종료 · 결과 유지')
        self.start_btn.setEnabled(True);self.stop_btn.setEnabled(False)
        if self.capture is not None:
            self.capture.stop()
        self.redetect_btn.setText('인식')
        self.update_clock()

    def update_clock(self):
        self.timer_text.setText(self.session.elapsed_label)
        total=int(self.session.elapsed_seconds)
        self.minutes.setText(f'총 {total//60}분 {total%60}초 사냥')
        if self.isVisible():self.update()  # repaint the classic skin

    def receive(self,measurement):
        if 'slots' in measurement:
            present={entry.get('slot') for entry in measurement['slots']}
            for key in set(self.slot_labels)-present:
                self.slot_labels[key].setText('—')
                if key in getattr(self,'slot_used',{}):self.slot_used[key].setText('')
                self.slot_icons[key].clear()
                self._preflight_slots.pop(key,None)
                if key in self.EXTRA_SLOT_LABELS:
                    self._set_slot_visible(key,False)
        if not self.session.running:
            if 'found_keyboard' in measurement:
                self._found_keyboard=bool(measurement['found_keyboard'])
            for entry in measurement.get('slots',[]):
                key=entry.get('slot')
                self._show_slot(key,entry.get('png'))
                if key not in self.slot_labels:continue
                from .potion_icon_db import POTIONS
                name=POTIONS.get(entry.get('potion_id'),'아이템 미확인 · 내장 PNG 매칭 대기')
                self.slot_icons[key].setToolTip(name)
                previous=self._preflight_slots.get(key)
                if previous and previous.get('icon')!=entry.get('icon'):
                    self._preflight_slots.pop(key,None)
                if entry.get('count') is not None:
                    self._preflight_slots[key]=dict(entry)
                    self.slot_labels[key].setText(f"{entry['count']:,}")
                elif key not in self._preflight_slots:
                    self.slot_labels[key].setText('—')
            if 'slots' in measurement:
                self.hint.setText('물약 초기 수량 확인 완료 · 시작 가능' if self._preflight_slots
                                  else '슬롯 인식 중 · 수량 확인 필요')
            return
        self._last_capture_mode=measurement.get('capture_mode',getattr(self,'_last_capture_mode','—'))
        self._exp_diagnostic=measurement.get('exp_diag',getattr(self,'_exp_diagnostic',''))
        has_ocr='exp' in measurement
        if has_ocr:
            self.session.observe_exp(measurement.get('level'),measurement.get('exp'),measurement.get('pct'))
            suffix='~' if self.session.exp_estimated else ''
            if self.session.last_exp is not None:
                # Gain since 시작 (not the character's current EXP)
                ses=self.session
                pct=f' ({ses.gained_percent:.2f}%)' if ses.start_percent is not None else ''
                self.exp_label.setText(f'+{ses.gained_exp:,}{suffix}')
                self._exp_full=f'+{ses.gained_exp:,}{suffix}{pct}'
                self.exp_info.setText(f'현재 {ses.last_exp:,} EXP')
                start_exp=f'{ses.start_exp:,}' if ses.start_exp is not None else '?'
                self._exp_tip=(f'시작 후 획득 경험치: {ses.gained_exp:,}{pct}\n'
                               f'시작 시점: Lv.{ses.start_level or "?"} {start_exp} EXP'
                               + (f' ({ses.start_percent:.2f}%)' if ses.start_percent is not None else '')
                               + f'\n현재: Lv.{ses.last_level or "?"} {ses.last_exp:,} EXP'
                               + (f' ({ses.last_percent:.2f}%)' if ses.last_percent is not None else ''))
            else:
                self.exp_label.setText('OCR 대기')
        if 'found_keyboard' in measurement:
            self._found_keyboard=bool(measurement['found_keyboard'])
        if 'keyboard_source' in measurement:
            self._keyboard_source=measurement['keyboard_source']
        for entry in measurement.get('slots',[]):
            key=entry.get('slot')
            if not key or not entry.get('icon'):continue
            self._show_slot(key,entry.get('png'))
            from .potion_icon_db import POTIONS
            self.slot_icons[key].setToolTip(POTIONS.get(entry.get('potion_id'),'아이템 미확인 · 내장 PNG 매칭 대기'))
            self.session.observe_slot(key,entry['icon'],entry.get('count'))
            record=self.session.slots.get(key)
            if key in self.slot_labels:
                if record is not None and record.last_count is not None:
                    label=f'{record.last_count:,}'
                    tooltip=f'{key} | 현재 {record.last_count}개 / 사용 {record.spent}개 / 보충 {record.refills}개'
                    from .hunt_extras import potion_minutes,format_duration
                    left=potion_minutes(record,self.session.elapsed_seconds)
                    if left is not None:
                        tooltip+=f'\n이 속도면 남은 물약으로 약 {format_duration(left*60)}'
                    used_text=f'사용 {record.spent:,}개'
                else:
                    label='—'
                    tooltip=f'{key} | 실제 아이콘 확인 · 작은 수량 OCR 대기'
                    used_text=''
                self.slot_labels[key].setText(label)
                if key in getattr(self,'slot_used',{}):
                    self.slot_used[key].setText(used_text)
                    self.slot_used[key].setToolTip(tooltip)
                self.slot_labels[key].setToolTip(tooltip)
        self.history_label.setText(f'이전 물약: {sum(self.session.retired_usage.values())}개')
        self._check_potions()
        if not getattr(self,'_found_keyboard',False):
            self.hint.setText(f'{self._last_capture_mode.upper()} · 단축키 탐색 중')
        elif has_ocr and self.session.last_exp is None:
            self.hint.setText(f'{self._last_capture_mode.upper()} · EXP 판독 실패')
        elif self.session.slots and all(v.last_count is None for v in self.session.slots.values()):
            self.hint.setText('아이콘 확인 · 수량 OCR 대기 ('+getattr(self,'_keyboard_source','auto')+')')
        else:
            self.hint.setText(f'{self._last_capture_mode.upper()} · 게임 화면 추적 중')

        diag=self._exp_diagnostic
        if 'frame_size' in measurement:
            self._last_frame_size=measurement['frame_size']
        if 'exp_roi_found' in measurement:
            self._last_roi_status=measurement['exp_roi_found']
        image_size=getattr(self,'_last_frame_size',None)
        roi=getattr(self,'_last_roi_status',None)
        self.hint.setToolTip(f'캡처: {self._last_capture_mode} / 크기: {image_size} / EXP 게이지 발견: {roi}\n'
                             f'OCR: {diag}')

    def report_warning(self,text):
        if self.session.running:self.hint.setText(str(text)[:110])

    def shutdown(self):
        self._relative_zorder.release(self)
        self.stop_session()
        if self.capture is not None and self.capture.isRunning():
            self.capture.wait(15000)
        self.tick.stop()
