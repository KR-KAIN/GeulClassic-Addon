"""Stable HWND capture identity, geometry snapshots, true fixture separation."""
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from kain_maple_translator.capture_stream import CapturedChat, ChatCaptureStream, logical_capture_identity
from kain_maple_translator.wgc_capture import WgcWindowSource
from kain_maple_translator.hunt_capture import locate_keyboard,find_exp_label_roi

ROOT=Path(__file__).resolve().parents[1]

class FakeController:
    def __init__(self):self.stopped=False
    def stop(self):self.stopped=True
    def is_finished(self):return self.stopped

class FakeWgc:
    def __init__(self,**params):
        self.params=params;self.events={};self.control=FakeController()
    def event(self,callback):self.events[callback.__name__]=callback;return callback
    def start_free_threaded(self):return self.control
    def dispatch(self,bgra):
        class Frame:pass
        frame=Frame();frame.frame_buffer=bgra
        self.events['on_frame_arrived'](frame,self.control)

class Tests(unittest.TestCase):
    def sample(self,xy,source,hwnd=123,size=(600,100)):
        x,y=xy;w,h=size
        return CapturedChat(np.zeros((h,w,3),np.uint8),dict(left=x,top=y,width=w,height=h),
                            time.monotonic(),source=source,window_hwnd=hwnd)

    def test_moving_hwnd_does_not_restart_history(self):
        a=self.sample((10,550),'wgc')
        b=self.sample((300,750),'wgc')
        c=self.sample((300,750),'mss')
        self.assertEqual(logical_capture_identity(a),logical_capture_identity(b))
        self.assertEqual(logical_capture_identity(b),logical_capture_identity(c))

    def test_other_hwnd_and_resize_reset(self):
        a=self.sample((10,550),'wgc')
        self.assertNotEqual(logical_capture_identity(a),logical_capture_identity(self.sample((10,550),'wgc',hwnd=678)))
        self.assertNotEqual(logical_capture_identity(a),logical_capture_identity(self.sample((10,550),'wgc',size=(700,100))))

    def test_manual_source_switch_does_reset(self):
        self.assertNotEqual(logical_capture_identity(self.sample((10,550),'wgc',hwnd=0)),
                            logical_capture_identity(self.sample((10,550),'mss',hwnd=0)))

    def test_wgc_target_is_hwnd_and_owns_frame(self):
        created=[]
        def make(**kwargs):
            inst=FakeWgc(**kwargs);created.append(inst);return inst
        source=WgcWindowSource(987,(100,200,800,600),
            {'left':150,'top':650,'width':400,'height':80},outer_rect=(92,170,816,638),
            capture_factory=make)
        source.start()
        self.assertEqual(created[0].params['window_hwnd'],987)
        self.assertFalse('monitor_index' in created[0].params)
        pixels=np.zeros((600,800,4),np.uint8)
        pixels[450:530,50:450,:3]=[3,22,91]
        created[0].dispatch(pixels)
        frame,reg,_=source.get()
        self.assertEqual(frame[0,0].tolist(),[3,22,91])
        self.assertEqual((reg['left'],reg['top']),(150,650))
        source.close()

    def test_wgc_geometry_update_discards_old_position_frames(self):
        capture=[]
        def make(**kw):
            f=FakeWgc(**kw);capture.append(f);return f
        source=WgcWindowSource(901,(100,200,800,600),
            {'left':100,'top':650,'width':400,'height':80},outer_rect=(92,170,816,638),capture_factory=make)
        source.start()
        capture[0].dispatch(np.zeros((600,800,4),np.uint8))
        self.assertEqual(source.queue.qsize(),1)
        source.set_geometry((300,400,800,600),{'left':300,'top':850,'width':400,'height':80},
                            outer_rect=(292,370,816,638))
        self.assertEqual(source.queue.qsize(),0)
        capture[0].dispatch(np.zeros((600,800,4),np.uint8))
        _,region,_=source.get()
        self.assertEqual(region['left'],300)
        source.close()

    def test_wgc_transient_resize_frame_does_not_end_capture(self):
        constructed=[]
        def make(**kw):
            obj=FakeWgc(**kw);constructed.append(obj);return obj
        source=WgcWindowSource(901,(100,200,800,600),
            {'left':100,'top':650,'width':400,'height':80},outer_rect=(92,170,816,638),capture_factory=make)
        source.start()
        # Old DWM swapchain size arrives immediately after resizing window.
        constructed[0].dispatch(np.zeros((720,1280,4),np.uint8))
        self.assertFalse(source.finished)
        self.assertEqual(source.geometry_errors,1)
        # Next frame uses the new correct dimensions.
        constructed[0].dispatch(np.zeros((600,800,4),np.uint8))
        self.assertEqual(source.arrivals,1)
        self.assertEqual(source.geometry_retries,0)
        source.close()

    def test_exp_and_keyboard_fixture_do_not_confuse_one_another(self):
        exp=cv2.imread(str(ROOT/'tests/fixtures/hunt-exp-hud.png'))
        keyboard=cv2.imread(str(ROOT/'resources/hunt/keyboard-reference.png'))
        self.assertIsNotNone(find_exp_label_roi(exp))
        self.assertIsNone(locate_keyboard(exp))
        self.assertIsNotNone(locate_keyboard(keyboard))

    def test_capture_queue_retains_changed_frames_and_drops_refreshes(self):
        stream=ChatCaptureStream(lambda:{},lambda _:None,capacity=2)
        a=self.sample((0,0),'wgc');b=self.sample((0,0),'wgc');b.captured_at=a.captured_at+1
        stream.publish(a);stream.publish(b)
        c=self.sample((0,0),'wgc');c.changed=False
        self.assertFalse(stream.publish(c))
        self.assertEqual(stream.overflows,0)
        self.assertEqual(stream.get().captured_at,a.captured_at)
        self.assertEqual(stream.get().captured_at,b.captured_at)

if __name__=='__main__':unittest.main()
