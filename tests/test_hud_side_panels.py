"""v0.4.2 HUD-panel alignment tests: never change the chat overlay geometry."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kain_maple_translator.layout import hud_panel_geometry
from kain_maple_translator.core import DEFAULTS

class HUDSidePanels(unittest.TestCase):
    def test_1366_game_client_matches_hud_top_and_bottom(self):
        game=(0,0,1366,768)
        chat={'left':288,'top':630,'width':558,'height':64}
        left,right=hud_panel_geometry(game,game,chat)
        self.assertEqual(left[1]+left[3],768)
        self.assertEqual(right[1]+right[3],768)
        self.assertEqual((left[3],right[3]),(126,126))
        self.assertEqual(left[0],0)
        self.assertEqual(right[0]+right[2],1366)
        self.assertEqual(right[0]-(left[0]+left[2]),803)

    def test_game_client_move_tracks_hud(self):
        base=(30,50,1366,768)
        chat={'left':318,'top':680,'width':558,'height':60}
        (lx,ly,lw,lh),(rx,ry,rw,rh)=hud_panel_geometry(base,(0,0,1920,1080),chat)
        self.assertEqual((ly+lh,ry+rh),(818,818))
        self.assertEqual((lh,rh),(126,126))
        self.assertTrue(lx<rx)

    def test_no_manual_chat_uses_hud_scale(self):
        (lx,ly,lw,lh),(rx,ry,rw,rh)=hud_panel_geometry(
            (0,0,1920,1080),(0,0,1920,1080),None)
        self.assertEqual((ly+lh,ry+rh),(1080,1080))
        self.assertLessEqual(lh,126)
        self.assertEqual(lh,rh)

    def test_stale_chat_crop_ignored(self):
        old={'left':100,'top':100,'width':500,'height':50}
        first=hud_panel_geometry((0,0,1366,768),(0,0,1366,768),old)
        second=hud_panel_geometry((0,0,1366,768),(0,0,1366,768),None)
        self.assertEqual(first,second)

    def test_settings_are_for_controls_not_chat(self):
        self.assertTrue(DEFAULTS['hud_panels_match'])
        self.assertFalse(DEFAULTS['chat_geometry']['hud_match_height'])
        src=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf8')
        self.assertIn('self.left.fit_bottom_hud',src)
        self.assertIn('self.right.fit_bottom_hud',src)
        self.assertIn('self.hud_panels=QCheckBox',src)
        self.assertIn("self.cfg['hud_panels_match']=dlg.hud_panels.isChecked()",src)

if __name__=='__main__':unittest.main()
