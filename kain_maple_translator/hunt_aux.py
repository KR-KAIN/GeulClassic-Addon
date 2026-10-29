"""Non-blocking auxiliary HUD analyzer for quickslot potion counts.

The game's newest full-window frame replaces old waiting frames.  This worker
never holds up the EXP OCR/capture loop and does not mutate Qt widgets.
"""
from __future__ import annotations
import logging
import threading
import time
import cv2

from .potion_icon_db import PotionIconLibrary
from .hunt_capture import (locate_keyboard_near_hud, potion_crops,
                           icon_identity, slot_occupied, read_potion_amounts,
                           _digit_region)

LOG=logging.getLogger(__name__)


def keyboard_from_relative(frame, relative):
    """Validate an explicit user-selected client-relative keyboard rectangle."""
    if frame is None or frame.size==0 or not isinstance(relative,(list,tuple)) or len(relative)!=4:
        return None
    h,w=frame.shape[:2]
    try:
        a,b,c,d=(float(v) for v in relative)
        if not all(0<=v<=1 for v in (a,b,c,d)):return None
        x,y,bw,bh=round(a*w),round(b*h),round(c*w),round(d*h)
        if bw<75 or bh<50 or x+bw>w or y+bh>h:return None
        if not .95<bw/bh<2.:return None
        return (x,y,bw,bh)
    except (ValueError,TypeError):return None


def _snapshot_png(crop):
    """PNG of the slot artwork for items not in the built-in potion list."""
    from .hunt_capture import icon_snapshot
    try:
        pic=icon_snapshot(crop)
        ok,data=cv2.imencode('.png',pic) if pic is not None else (False,None)
        return data.tobytes() if ok else b''
    except Exception:
        return b''


class SlotCountGate:
    """Reuse a confirmed amount while the *digit region* is unchanged.

    A periodic recheck and immediate retry of unreadable counts prevent stale
    values from becoming unverified consumption records.
    """
    def __init__(self, refresh_after=3.0, difference=1.3):
        self.refresh_after=float(refresh_after)
        self.difference=float(difference)
        self.last={}

    def reset(self):self.last.clear()

    @staticmethod
    def pixels(crop):
        digits=_digit_region(crop)
        gray=cv2.cvtColor(digits,cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray,(36,21),interpolation=cv2.INTER_AREA)

    def reuse(self,key,icon,crop,now):
        prior=self.last.get(key)
        if prior is None:return None
        old_icon,old_pixels,old_count,old_time=prior
        if old_count is None or icon!=old_icon or now-old_time>=self.refresh_after:
            return None
        return old_count if float(cv2.absdiff(old_pixels,self.pixels(crop)).mean())<=self.difference else None

    def record(self,key,icon,crop,count,now):
        # Never mark an unreadable value as fresh for future cache hits.
        if count is not None:
            self.last[key]=(icon,self.pixels(crop),int(count),float(now))


class HuntAuxAnalyzer:
    """Separate OCR thread consuming only freshest captured frame (size-one queue)."""
    def __init__(self, emit, warning, keyboard_relative=None, stop_event=None):
        self.emit=emit
        self.warning=warning
        self._condition=threading.Condition()
        self._frame=None
        self._frame_mode='wgc'
        self._frame_serial=0
        self._stopping=False
        self._keyboard_relative=keyboard_relative
        self._generation=0
        self._stop_event=stop_event
        self._thread=threading.Thread(target=self._run,name='geulclassic-hunt-aux',daemon=True)
        self._thread.start()

    def publish(self, frame, mode='wgc'):
        with self._condition:
            if self._stopping:return
            self._frame=frame.copy()
            self._frame_mode=mode
            self._frame_serial+=1
            self._condition.notify()

    def reconfigure(self, relative):
        with self._condition:
            self._keyboard_relative=relative
            self._generation+=1
            self._condition.notify()

    def redetect(self):
        with self._condition:
            self._generation+=1
            self._condition.notify()

    def stop(self):
        with self._condition:
            self._stopping=True
            self._condition.notify_all()
        if threading.current_thread()!=self._thread:self._thread.join(timeout=7)

    def _run(self):
        recognizer=None
        count_gate=SlotCountGate()
        potion_db=PotionIconLibrary()
        pending_counts={}
        extra_misses={}
        keyboard=None
        last_shape=None
        last_gen=-1
        next_slots=0.
        next_search=0.
        serial=0
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda:self._stopping or
                        (self._frame is not None and self._frame_serial!=serial),timeout=.45)
                    if self._stopping:return
                    if self._frame is None or self._frame_serial==serial:continue
                    frame=self._frame
                    mode=self._frame_mode
                    serial=self._frame_serial
                    gen=self._generation
                    relative=self._keyboard_relative
                now=time.monotonic()
                if last_shape!=frame.shape[:2] or gen!=last_gen:
                    keyboard=None
                    count_gate.reset()
                    pending_counts.clear()
                    last_shape=frame.shape[:2]
                    last_gen=gen
                    next_search=0.
                    next_slots=0.
                if now>=next_slots:
                    next_slots=now+.8
                    manual=keyboard_from_relative(frame,relative)
                    if manual is not None:
                        keyboard=manual
                    elif now>=next_search:
                        keyboard=locate_keyboard_near_hud(frame)
                        next_search=now+(4. if keyboard is not None else 1.3)
                    visible=[];selected={};extra_selected={}
                    if keyboard is not None:
                        bottom=potion_crops(frame,keyboard)
                        # Only the bottom 4 keys (Ctrl/Del/End/PgDn) hold
                        # tracked potions; other keys are not scanned.
                        extra=[]
                        for key,crop in list(potion_crops(frame,keyboard).items())+extra:
                            is_extra=key not in bottom
                            # Match the intact slot BEFORE saturation gates:
                            # white potions and pale liquids are real potions.
                            matched=potion_db.identify(crop)
                            if not matched and not slot_occupied(crop):continue
                            identity=('potion:'+matched[0]) if matched else icon_identity(crop)
                            if not identity:continue
                            miss=extra_misses.get(key)
                            if is_extra and miss and miss[0]==identity and miss[1]>=3 and now<miss[2]:
                                continue  # e.g. a skill icon: no stack count to read
                            # Screenshots contain count overlays and clipped bottle
                            # outlines. Display only identified, complete assets.
                            item_name=matched[0] if matched else ''
                            display_png=matched[1] if matched else (_snapshot_png(crop) if is_extra else b'')
                            cached=count_gate.reuse(key,identity,crop,now)
                            if cached is None:
                                (extra_selected if is_extra else selected)[key]=crop
                            visible.append({'slot':key,'icon':identity,'png':display_png,
                                            'potion_id':item_name,'count':cached,'extra':is_extra})
                            if len(visible)>=12:break
                    def shown():
                        return [e for e in visible if not e['extra'] or e['count'] is not None]
                    self.emit({'slots':shown(),'found_keyboard':keyboard is not None,
                               'capture_mode':mode,'keyboard_source':'manual' if manual is not None else 'auto'})
                    if extra_selected:
                        # Raster digits only: no OCR model for keys that may
                        # hold skills, so a missing count costs ~0.1s, not 1s.
                        from .stack_digits import match_stack_digits
                        extra_counts={}
                        for key,crop in extra_selected.items():
                            got=match_stack_digits(crop)
                            extra_counts[key]=got[0] if got else None
                            icon=next(e['icon'] for e in visible if e['slot']==key)
                            if got:
                                extra_misses.pop(key,None)
                            else:
                                old=extra_misses.get(key)
                                misses=(old[1]+1) if old and old[0]==icon else 1
                                extra_misses[key]=(icon,misses,now+20.)
                    else:
                        extra_counts={}
                    if selected or extra_selected:
                        if recognizer is None and selected:
                            from .vision import TextRecognizer
                            try:recognizer=TextRecognizer()
                            except Exception as exc:
                                self.warning('물약 OCR 초기화 실패: '+str(exc)[:80])
                                recognizer=False
                        if recognizer or extra_counts:
                            counts=read_potion_amounts(recognizer,selected) if selected and recognizer else {}
                            counts.update(extra_counts)
                            selected.update(extra_selected)
                            for entry in visible:
                                if entry['slot'] in selected:
                                    value=counts.get(entry['slot'])
                                    slot=entry['slot']
                                    # Number recognition on 6-10px text can
                                    # hallucinate a plausible quantity once.
                                    # Confirm a new number in two independent
                                    # observations before showing/using it.
                                    prior=count_gate.last.get(slot)
                                    old_count=prior[2] if prior and prior[0]==entry['icon'] else None
                                    if value is not None and value==old_count:
                                        pending_counts.pop(slot,None)
                                        entry['count']=value
                                        count_gate.record(slot,entry['icon'],selected[slot],value,time.monotonic())
                                    elif value is not None:
                                        pending=pending_counts.get(slot)
                                        if pending and pending[0]==entry['icon'] and pending[1]==value and pending[3]!=serial:
                                            pending_counts.pop(slot,None)
                                            entry['count']=value
                                            count_gate.record(slot,entry['icon'],selected[slot],value,time.monotonic())
                                        else:
                                            pending_counts[slot]=(entry['icon'],value,time.monotonic(),serial)
                                            entry['count']=old_count
                                    else:
                                        entry['count']=old_count
                            self.emit({'slots':shown(),'found_keyboard':True,
                                       'capture_mode':mode,'keyboard_source':'manual' if manual is not None else 'auto'})
        except Exception as exc:
            LOG.exception('Potion analyzer stopped')
            self.warning('물약 분석 오류: '+str(exc)[:80])
