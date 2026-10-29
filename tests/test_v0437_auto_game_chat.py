import sys
import time
import types
import threading
import unittest
from unittest.mock import patch
from dataclasses import dataclass

import numpy as np
import cv2

from kain_maple_translator.auto_chat_detect import detect_chat_region, estimate, local_crop
from kain_maple_translator.capture_stream import ChatCaptureStream
from kain_maple_translator.core import DEFAULTS, load_config, save_config
from kain_maple_translator.game_window import RelativeRegion, relative_to_region

RECT=(100,200,1366,768)


def fake_maple_frame():
    # Reproduce the relevant *geometry and colors* of the bottom-left Maple
    # '전체' chat toolbar using synthetic pixels (does not depend on fixtures).
    # R20: where the 1366x768 client really draws the button (287..366 x
    # 706..723) with the white chat input field right of it.
    img=np.full((768,1366,3), (155,155,155), np.uint8)
    cv2.rectangle(img,(370,706),(830,721),(245,245,245),-1)
    cv2.rectangle(img,(287,706),(366,723),(111,83,54),-1)
    # The small gray text knockouts are not mandatory for color-bar detection.
    cv2.rectangle(img,(311,710),(332,717),(210,210,210),-1)
    return img


class VisualAutoLocate(unittest.TestCase):
    def test_find_chat_hud_without_selected_rectangle(self):
        result=detect_chat_region(fake_maple_frame(),RECT)
        self.assertIsNotNone(result)
        self.assertEqual(result.method,'visual-chat-toolbar')
        self.assertGreater(result.confidence,.7)
        self.assertTrue(RECT[0]+200 < result.region['left'] < RECT[0]+500)
        self.assertTrue(RECT[1]+620 < result.region['top'] < RECT[1]+715)
        crop=local_crop(fake_maple_frame(),RECT,result.region)
        self.assertEqual(crop.shape[:2],(result.region['height'],result.region['width']))

    def test_no_false_verified_location_without_chat_toolbar(self):
        img=np.zeros((768,1366,3),np.uint8)
        self.assertIsNone(detect_chat_region(img,RECT))
        self.assertEqual(estimate(RECT).method,'geometry-estimate')

    def test_reject_arbitrary_wgc_frame_as_game_client(self):
        self.assertIsNone(detect_chat_region(fake_maple_frame()[100:300,200:400],RECT))

    def test_auto_config_saved(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config.json'
            cfg=load_config(p)
            self.assertTrue(cfg['auto_chat_region'])
            cfg['auto_chat_region']=False
            save_config(cfg,p)
            self.assertFalse(load_config(p)['auto_chat_region'])


class IntegrationAutoCapture(unittest.TestCase):
    @dataclass
    class Game:
        hwnd:int=245
        rect:tuple=RECT

    class FakeMss:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def grab(self,r):return np.ones((r['height'],r['width'],4),np.uint8)

    def test_mss_automatic_fallback_never_needs_drag(self):
        cfg={'capture_backend':'mss','auto_chat_region':True,'enabled':{'chat':True},
             'regions':{'chat':None},'capture_interval':.08}
        stream=ChatCaptureStream(lambda:cfg,lambda err:None)
        with (patch.dict(sys.modules,{'mss':types.SimpleNamespace(mss=self.FakeMss)}),
              patch('kain_maple_translator.game_window.find_maple_window',return_value=self.Game()),
              patch('kain_maple_translator.fast_vision.ink_rows',return_value=([],False))):
            stream.start();frame=stream.get(timeout=1.5);stream.close()
        self.assertIsNotNone(frame)
        self.assertTrue(frame.region['top']>RECT[1]+580)
        self.assertEqual(frame.source,'mss')
        self.assertEqual(stream.auto_method,'mss-geometry-estimate')

    def test_wgc_first_frame_detects_then_crops(self):
        cfg={'capture_backend':'wgc','auto_chat_region':True,'enabled':{'chat':True},
             'regions':{'chat':None},'capture_interval':.08}
        calls=[]
        class Source:
            def __init__(self,hwnd,client_rect,region):
                self.game_rect=client_rect
                self.region=region
                self.arrivals=0;self.queue_overflows=0;self.started_at=time.monotonic()
                self.error=None;self.closed=False
            def start(self): pass
            def set_geometry(self,rect,region):
                calls.append(dict(region));self.region=region
            def get(self,timeout=.05):
                self.arrivals+=1
                if self.arrivals==1:
                    return fake_maple_frame(),dict(self.region),time.monotonic()
                x=self.region['left']-RECT[0]
                y=self.region['top']-RECT[1]
                w=self.region['width'];h=self.region['height']
                return fake_maple_frame()[y:y+h,x:x+w,:].copy(),dict(self.region),time.monotonic()
            @property
            def finished(self):return False
            def close(self):self.closed=True
        class NoMss(self.FakeMss):
            def grab(self,r):raise AssertionError('Unexpected MSS when WGC is live')
        stream=ChatCaptureStream(lambda:cfg,lambda err: (_ for _ in ()).throw(AssertionError(err)))
        with (patch.dict(sys.modules,{'mss':types.SimpleNamespace(mss=NoMss)}),
              patch('kain_maple_translator.game_window.find_maple_window',return_value=self.Game()),
              patch('kain_maple_translator.wgc_capture.WgcWindowSource',Source),
              patch('kain_maple_translator.fast_vision.ink_rows',return_value=([],False))):
            stream.start();frame=stream.get(timeout=2.0);stream.close()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.source,'wgc')
        self.assertEqual(stream.auto_method,'visual-chat-toolbar')
        self.assertEqual(frame.image.shape[:2],(frame.region['height'],frame.region['width']))
        self.assertTrue(any('left' in x for x in calls))

if __name__=='__main__': unittest.main()
