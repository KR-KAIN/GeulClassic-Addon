"""Real image-pattern and end-to-end metadata regression tests; no fake claims about Windows UI."""
import json
import tempfile
import unittest
from urllib.request import urlopen
from pathlib import Path
import numpy as np
import cv2
from kain_maple_translator.megaphone import detect_band, classify, row_appearance, tinted_rgba
from kain_maple_translator.obs_source import OBSChatSource, OBS_HTML
from kain_maple_translator.core import load_config, save_config

ROOT=Path(__file__).resolve().parents[1]

class AnnouncementColors(unittest.TestCase):
    def strip(self, rgb):
        # A little OCR-like text and a channel icon should not defeat detection.
        bgr=np.zeros((65,400,3), dtype=np.uint8)
        bgr[:,:]=(rgb[2],rgb[1],rgb[0])
        cv2.putText(bgr,'SamuraiPoo CH05 : B> GFA 60%',(8,19),cv2.FONT_HERSHEY_SIMPLEX,.41,(5,5,5),1)
        cv2.putText(bgr,'Isis CH30 : item mega +4', (8,43),cv2.FONT_HERSHEY_SIMPLEX,.41,(245,245,245),1)
        return bgr

    def test_pink_bar_detected_and_super_prefix(self):
        band=detect_band(self.strip((227,160,184)),(8,3,180,16))
        self.assertEqual(band.tone,'pink')
        self.assertEqual(classify(band,'S> WG')['prefix'],'[고확]')

    def test_yellow_item_and_multiple_links(self):
        band=detect_band(self.strip((247,194,34)),(8,30,180,16))
        self.assertEqual(band.tone,'yellow')
        self.assertEqual(classify(band,'S> [Reef Claw]')['prefix'],'[아확]')
        self.assertEqual(classify(band,'[Claw] & [Cape]')['prefix'],'[아확]')

    def test_yellow_without_item_link_uses_color_label(self):
        band=detect_band(self.strip((247,194,34)),(8,30,180,16))
        self.assertEqual(classify(band,'S> GFA 60%')['prefix'],'[아확]')

    def test_cyan_and_green_colours(self):
        self.assertEqual(detect_band(self.strip((61,211,190)),(8,3,180,16)).tone,'cyan')
        self.assertEqual(detect_band(self.strip((105,207,97)),(8,3,180,16)).tone,'green')

    def test_plain_dark_chat_no_false_announcement(self):
        plain=np.full((42,400,3), 28, dtype=np.uint8)
        cv2.putText(plain,'hello',(5,19),cv2.FONT_HERSHEY_SIMPLEX,.6,(240,240,240),2)
        self.assertEqual(detect_band(plain,(5,8,120,14)).tone,'none')

    def test_row_metadata_and_rgba_safe(self):
        bgr=self.strip((227,160,184))
        kind=row_appearance(bgr,(5,2,150,17),(0,0),'S> 10%')
        self.assertEqual(kind['kind'],'super')
        self.assertRegex(kind['band_color'],r'^#[0-9a-f]{6}$')
        self.assertTrue(tinted_rgba(kind['band_color']).startswith('rgba('))

    def test_obs_uses_split_and_translated_color_metadata(self):
        obs=OBSChatSource(port=0)
        records=[{'nickname':'Isis','translated':'거래 가능','kind':'item','prefix':'[아확]', 'band_color':'#f0c234'},
                 {'nickname':'Samurai','translated':'안녕하세요','kind':'normal','prefix':'','band_color':''}]
        try:
            url=obs.start()
            obs.set_state(records,split_ratio_general=63)
            with urlopen(url+'state',timeout=4) as stream:
                value=json.loads(stream.read().decode())
            self.assertEqual(value['split_ratio_general'],63)
            self.assertEqual(value['messages'][0]['kind'],'item')
            self.assertIn('normal-lines',OBS_HTML)
            self.assertIn('mega-lines',OBS_HTML)
            self.assertIn('entry.band_color',OBS_HTML)
        finally:
            obs.close()

    def test_persist_split_and_hud_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            conf=Path(directory)/'config.json'; cfg=load_config(conf)
            self.assertEqual(cfg['split_ratio_general'],70)
            self.assertFalse(cfg['chat_geometry']['hud_match_height'])
            self.assertTrue(cfg['hud_panels_match'])
            cfg['split_ratio_general']=62
            save_config(cfg,conf)
            self.assertEqual(load_config(conf)['split_ratio_general'],62)

    def test_qt_has_real_mouse_draggable_splitter(self):
        src=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('QSplitter(Qt.Orientation.Vertical',src)
        self.assertIn('splitterMoved.connect',src)
        self.assertIn('self.chat.ratio_changed.connect(self.save_split_ratio)',src)
        self.assertIn("'hud_match_height'",src)

if __name__ == '__main__':unittest.main()
