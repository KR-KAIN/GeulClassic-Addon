import unittest
from kain_maple_translator.layout import (GAME_RESOLUTIONS, resolution_size,
                                          estimate_chat_area, dock_to_side)
from kain_maple_translator.core import load_config, save_config
from pathlib import Path
from tempfile import TemporaryDirectory

class ResolutionLayoutTests(unittest.TestCase):
    def test_preset_values_and_unknown_values(self):
        self.assertEqual(resolution_size('1366x768'), (1366,768))
        self.assertIsNone(resolution_size('auto'))
        self.assertIsNone(resolution_size('random-stuff'))
        self.assertIn('1920x1080', GAME_RESOLUTIONS)

    def test_game_client_origin_matters(self):
        a=estimate_chat_area((10,20,1366,768),'1366x768')
        b=estimate_chat_area((510,320,1366,768),'1366x768')
        self.assertEqual((b[0]-a[0],b[1]-a[1]),(500,300))
        self.assertGreaterEqual(a[0],10)
        self.assertLessEqual(a[0]+a[2],1376)
        self.assertGreater(a[1],600)

    def test_autofit_works_across_common_sizes(self):
        for res in ('800x600','1024x768','1280x720','1366x768','1920x1080'):
            w,h=resolution_size(res)
            x,y,cw,ch=estimate_chat_area((80,60,w,h),res)
            self.assertGreaterEqual(x,80)
            self.assertGreaterEqual(y,60)
            self.assertLessEqual(x+cw,80+w)
            self.assertLessEqual(y+ch,60+h)

    def test_dock_left_matches_full_game_height(self):
        dock,where=dock_to_side((400,200,850,600),(0,0,1920,1080),200,100,'left')
        self.assertEqual(dock,(193,200,200,600))
        self.assertEqual(where,'outside')

    def test_dock_right_matches_full_game_height(self):
        dock,where=dock_to_side((200,50,900,750),(0,0,1920,1080),250,120,'right')
        self.assertEqual(dock,(1107,50,250,750))
        self.assertEqual(where,'outside')

    def test_dock_fullscreen_fallback_remains_visible(self):
        dock,where=dock_to_side((0,0,1366,768),(0,0,1366,768),250,100,'left')
        self.assertEqual(dock,(0,0,250,768))
        self.assertEqual(where,'inside-fallback')
        right,where=dock_to_side((0,0,1366,768),(0,0,1366,768),250,100,'right')
        self.assertEqual(right,(1116,0,250,768))

    def test_disabled_height_match(self):
        dock,where=dock_to_side((300,100,850,600),(0,0,1920,1080),250,185,'right',False)
        self.assertEqual(dock,(1157,100,250,185))

    def test_resolution_and_region_source_persist(self):
        with TemporaryDirectory() as folder:
            cfgpath=Path(folder)/'preferences.json'
            cfg=load_config(cfgpath)
            cfg['game_resolution']='1280x720'
            cfg['region_source']='auto'
            save_config(cfg,cfgpath)
            reread=load_config(cfgpath)
            self.assertEqual(reread['game_resolution'],'1280x720')
            self.assertEqual(reread['region_source'],'auto')

    def test_main_integration_uses_real_client(self):
        s=(Path(__file__).resolve().parents[1]/'kain_maple_translator'/'main.py').read_text('utf-8')
        self.assertIn('def auto_place_from_game',s)
        self.assertIn('game_client_rect(',s)
        self.assertIn("self.cfg['game_resolution']=dlg.resolution.currentData()",s)
        self.assertIn('dock_to_side(',s)

if __name__=='__main__':
    unittest.main()
