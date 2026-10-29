"""WGC HWND geometry, native callback handoff, and backward compatible settings."""
from __future__ import annotations
import tempfile
import time
import types
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

from kain_maple_translator.wgc_capture import roi_frame_bounds, WgcWindowSource
from kain_maple_translator.core import DEFAULTS, load_config, save_config
from kain_maple_translator.capture_stream import CapturedChat, ChatCaptureStream
from kain_maple_translator import fast_vision  # pre-import cv2 before patch.dict(sys.modules)


class WgcGeometryTests(unittest.TestCase):
    def test_client_only_window_frame(self):
        a=roi_frame_bounds((720,1280,4),(130,210,1280,720),(122,180,1296,758),
                           {'left':130,'top':830,'width':750,'height':90})
        self.assertEqual(a,(0,620,750,710))

    def test_decorated_frame_uses_outer_origin(self):
        a=roi_frame_bounds((758,1296,4),(130,210,1280,720),(122,180,1296,758),
                           {'left':130,'top':830,'width':750,'height':90})
        self.assertEqual(a,(8,650,758,740))

    def test_dpi_scaled_client_dimensions(self):
        self.assertEqual(roi_frame_bounds((900,1600,4),(130,210,1280,720),
                         (122,180,1296,758),{'left':130,'top':830,'width':750,'height':90}),
                         (0,775,938,888))

    def test_wrong_target_or_off_window_region_not_silently_cropped(self):
        with self.assertRaises(ValueError):
            roi_frame_bounds((720,1280,4),(130,210,1280,720),(122,180,1296,758),
                             {'left':1900,'top':830,'width':750,'height':90})
        with self.assertRaises(ValueError):
            roi_frame_bounds((720,1280,4),(130,210,1920,1080),(120,200,1940,1120),
                             {'left':130,'top':830,'width':750,'height':90})


class FakeControl:
    def __init__(self): self.stopped=False
    def stop(self): self.stopped=True
    def is_finished(self): return self.stopped


class FakeCapture:
    def __init__(self, **kw):
        self.kw=kw
        self.events={}
        self.ctrl=FakeControl()
    def event(self, fn):
        self.events[fn.__name__]=fn
        return fn
    def start_free_threaded(self): return self.ctrl
    def dispatch(self, frame):
        class Frame: pass
        wrapped=Frame();wrapped.frame_buffer=frame
        self.events['on_frame_arrived'](wrapped,self.ctrl)


class WgcCallbackTests(unittest.TestCase):
    def new_source(self, pending=3):
        constructed=[]
        def factory(**args):
            capture=FakeCapture(**args);constructed.append(capture)
            return capture
        source=WgcWindowSource(301,(130,210,1280,720),
                {'left':130,'top':830,'width':750,'height':90},
                outer_rect=(122,180,1296,758),capture_factory=factory,max_pending=pending)
        source.start()
        self.assertEqual(constructed[0].kw['window_hwnd'],301)
        return source,constructed[0]

    def test_callback_produces_owned_bgr_crop_not_entire_window(self):
        src,cap=self.new_source()
        data=np.zeros((720,1280,4),dtype=np.uint8)
        data[620:710,:750,:3]=[10,20,30]
        cap.dispatch(data)
        frame,reg,stamp=src.get()
        self.assertEqual(frame.shape,(90,750,3))
        self.assertEqual(frame[0,0].tolist(),[10,20,30])
        data[620:710,:750,:3]=0
        self.assertEqual(frame[0,0].tolist(),[10,20,30])
        self.assertEqual(src.arrivals,1)
        src.close()
        self.assertTrue(cap.ctrl.stopped)

    def test_bounded_callback_queue_and_stop(self):
        src,cap=self.new_source(pending=2)
        for i in range(4):
            cap.dispatch(np.full((720,1280,4),i,dtype=np.uint8))
        self.assertEqual(src.queue.qsize(),2)
        self.assertEqual(src.queue_overflows,2)
        self.assertEqual(src.get()[0][0,0,0],2)
        self.assertEqual(src.get()[0][0,0,0],3)
        src.close()

    def test_invalid_geometry_stops_wgc_instead_of_wrong_roi(self):
        src,cap=self.new_source()
        src.set_geometry((130,210,1280,720), {'left':9999,'top':830,'width':750,'height':90})
        cap.dispatch(np.zeros((720,1280,4),dtype=np.uint8))
        self.assertTrue(src.finished)
        self.assertIn('outside game client',src.error)
        self.assertTrue(cap.ctrl.stopped)


class SettingsIntegrationTests(unittest.TestCase):
    def test_new_default_and_explicit_mss_saved(self):
        self.assertEqual(DEFAULTS['capture_backend'],'wgc')
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'config.json'
            config=load_config(path)
            config['capture_backend']='mss'
            save_config(config,path)
            self.assertEqual(load_config(path)['capture_backend'],'mss')
    def test_captured_chat_still_compatible_with_old_arguments(self):
        c=CapturedChat(np.zeros((20,30,3),dtype=np.uint8),{'left':0,'top':0,'width':30,'height':20},0.0)
        self.assertEqual(c.source,'mss')

class CaptureSelectionTests(unittest.TestCase):
    def fake_mss(self):
        class MssContext:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def grab(self,region):
                return np.zeros((region['height'],region['width'],4),dtype=np.uint8)
        return types.SimpleNamespace(mss=MssContext)

    def test_auto_fallback_keeps_mss_capture_alive_without_game_hwnd(self):
        cfg={'capture_backend':'wgc','enabled':{'chat':True},'ocr_paused':False,
             'regions':{'chat':{'left':0,'top':0,'width':350,'height':100}},
             'capture_interval':.05}
        errs=[]
        stream=ChatCaptureStream(lambda: cfg,errs.append)
        with (patch.dict(sys.modules,{'mss':self.fake_mss()}),
              patch('kain_maple_translator.game_window.find_maple_window',return_value=None),
              patch('kain_maple_translator.fast_vision.ink_rows',return_value=([],False))):
            stream.start()
            frame=stream.get(timeout=1.0)
            stream.close()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.image.shape,(100,350,3))
        self.assertEqual(frame.source,'mss')
        self.assertEqual(errs,[])

    def test_wgc_selection_feeds_bgr_roi_without_mss_grab(self):
        cfg={'capture_backend':'wgc','enabled':{'chat':True},'ocr_paused':False,
             'regions':{'chat':{'left':100,'top':600,'width':350,'height':100}},
             'capture_interval':.05}
        seen=[]
        class Source:
            def __init__(self,hwnd,client_rect,region):
                self.arrivals=0;self.queue_overflows=0;self.started_at=time.monotonic()
                self.error=None; self.region=region;self.closed=False
            def start(self):pass
            def set_geometry(self, client_rect, region):self.region=region
            def get(self, timeout=.05):
                self.arrivals+=1
                return (np.full((100,350,3),32,dtype=np.uint8),dict(self.region),time.monotonic())
            @property
            def finished(self):return False
            def close(self):self.closed=True
        class NeverGrab:
            def __enter__(self):return self
            def __exit__(self,*args): pass
            def grab(self,region):raise AssertionError('MSS called while WGC connected')
        game=types.SimpleNamespace(hwnd=1234,rect=(100,0,1280,720))
        stream=ChatCaptureStream(lambda: cfg,seen.append)
        with (patch.dict(sys.modules,{'mss':types.SimpleNamespace(mss=NeverGrab)}),
              patch('kain_maple_translator.game_window.find_maple_window',return_value=game),
              patch('kain_maple_translator.wgc_capture.WgcWindowSource',Source),
              patch('kain_maple_translator.fast_vision.ink_rows',return_value=([],False))):
            stream.start()
            frame=stream.get(timeout=1)
            stream.close()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.source,'wgc')
        self.assertEqual(frame.image.shape,(100,350,3))
        self.assertEqual(seen,[])

    def test_selected_mss_never_tries_to_find_game_or_load_wgc(self):
        cfg={'capture_backend':'mss','enabled':{'chat':True},'ocr_paused':False,
             'regions':{'chat':{'left':0,'top':0,'width':350,'height':100}},
             'capture_interval':.05}
        errs=[]
        stream=ChatCaptureStream(lambda: cfg,errs.append)
        with (patch.dict(sys.modules,{'mss':self.fake_mss()}),
              patch('kain_maple_translator.game_window.find_maple_window',side_effect=AssertionError('MSS must not seek HWND')),
              patch('kain_maple_translator.fast_vision.ink_rows',return_value=([],False))):
            stream.start()
            frame=stream.get(timeout=1.0)
            stream.close()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.source,'mss')
        self.assertEqual(errs,[])


if __name__=='__main__':unittest.main()
