"""v0.4.52 regression: only potion assets, ordinary chat and stable event IDs."""
from pathlib import Path
import unittest
import cv2
import numpy as np
from kain_maple_translator.potion_icon_db import PotionIconLibrary,POTIONS
from kain_maple_translator.megaphone import detect_band
from kain_maple_translator.visual_message_ledger import FrameMessageLedger
from kain_maple_translator.linked_ocr import repair_corrupt_bracket
from kain_maple_translator.item_link_protection import protect_hangul_links
ROOT=Path(__file__).resolve().parents[1]

class V0452Tests(unittest.TestCase):
    def test_only_potion_pngs_not_all_consumables(self):
        folder=ROOT/'resources/hunt/potions'
        files=list(folder.glob('*.png'))
        self.assertTrue(set(['2000000','2000001','2000002','2000003','2000004','2000005','2000006']).issubset(POTIONS))
        self.assertTrue(files)
        self.assertLess(sum(f.stat().st_size for f in files),120000)
        self.assertTrue(all(f.name.startswith('captured-') or f.stem in POTIONS for f in files))
    def test_png_decodes_and_self_match(self):
        db=PotionIconLibrary()
        self.assertTrue(db.templates)
        for name,_,blob in db.templates:
            raw=cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_UNCHANGED)
            got=db.identify(raw)
            self.assertIsNotNone(got)
            self.assertEqual(got[0],name)
    def test_blank_nonpotion_rejected(self):
        db=PotionIconLibrary()
        self.assertIsNone(db.identify(np.full((35,35,4),255,np.uint8)))
        self.assertIsNone(db.identify(np.zeros((35,35,4),np.uint8)))
    def test_dark_olive_normal_is_not_item_announcement(self):
        # Regress user screenshot: K3tchup : gz was ordinary chat.
        dark=np.full((25,290,3),(51,101,108),np.uint8)
        self.assertEqual(detect_band(dark,(0,0,290,25)).tone,'none')
    def test_genuine_bright_yellow_kept(self):
        bright=np.full((24,300,3),(2,194,247),np.uint8)
        self.assertEqual(detect_band(bright,(0,0,300,24)).tone,'yellow')
    def test_fuzzy_nickname_old_announcement_one_event(self):
        t=FrameMessageLedger()
        def line(n,y):return dict(nickname=n,body='S> [천사 헤일로] 190k FM16',rect=(0,y,250,16),kind='item')
        old=[line('TofuDew',40)]
        self.assertEqual(len(t.filter(old,old,1)),1)
        new=[line('TofuDcw',39)]
        self.assertEqual(t.filter(new,new,1.3),[])
        moved=[line('TofuDcw',23),line('TofuDew',44)]
        self.assertEqual(len(t.filter(moved,moved,1.5)),1)
    def test_multiple_brackets_repair_only_damaged_name(self):
        raw='S> [엘릭서] 10m [人回 买] 20m'
        new='S> [엘릭서] 10m [신사의 콧수염] 20m'
        self.assertEqual(repair_corrupt_bracket(raw,new,.95),new)
        self.assertIsNone(repair_corrupt_bracket(raw,'S> [엘릭서] 10m [신사의 콧수염] 30m',.95))
        self.assertIsNone(repair_corrupt_bracket('S> [천사 헤일로] 10m', 'S> [Angel Halo] 10m',.99))
    def test_korean_brackets_only_normalized_not_translated(self):
        self.assertEqual(protect_hangul_links('S> ［천사 헤일로］ 190k'), 'S> [천사 헤일로] 190k')
        self.assertEqual(protect_hangul_links('S> [천사 헤일로] 190k'), 'S> [천사 헤일로] 190k')
    def test_preview_recognize_before_timer_present(self):
        src=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf8')
        self.assertIn('def _start_preview(self):',src)
        self.assertIn('self._preflight_slots',src)
        self.assertIn("self.redetect_btn.setText('인식')",src)

if __name__=='__main__':unittest.main()
