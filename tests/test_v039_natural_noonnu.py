import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kain_maple_translator.natural_chat import phrase_override, polish_translation
from kain_maple_translator.translation import Translator
from kain_maple_translator.noonnu_fonts import (checked_url,font_css_candidates,
        cached_font_from_noonnu,FontUrlError)
from kain_maple_translator.obs_source import OBSChatSource, OBS_HTML
from kain_maple_translator.core import load_config, save_config

class ChatNaturalTests(unittest.TestCase):
    def test_natural_conversational_overrides(self):
        for source, expected in [
            ('Anyone for KPQ?','커닝 파퀘 하실 분?'),
            ('Where should we train?','어디서 사냥할까요?'),
            ('Can you invite me?','파티 초대 좀 해주세요'),
            ('cc plz','채널 좀 바꿔 주세요'),
        ]:
            self.assertEqual(Translator().translate(source,'en-ko'),expected)
    def test_no_bargain_price_rewrite(self):
        self.assertIsNone(phrase_override('S> scroll 2m','en-ko'))
        self.assertEqual(Translator().translate('CH9Player: S> 60% scroll 2m','en-ko'),
                         'CH9Player : 60% 주문서 200만 메소에 팝니다')
    def test_post_edit_is_conservative(self):
        self.assertEqual(polish_translation('Where are you training?', '어디에서 훈련하세요', 'en-ko'), '어디서 사냥해요')
        self.assertEqual(polish_translation('Selling for 20m','2,000만 메소에 팔아요','en-ko'),'2,000만 메소에 팔아요')
    def test_reverse_chat(self):
        self.assertEqual(Translator().translate('잠깐만요','ko-en'),'One sec')

class NoonnuTests(unittest.TestCase):
    def test_reject_untrusted_hosts(self):
        for url in ['http://noonnu.cc/font_page/106','https://127.0.0.1/font.ttf',
                    'https://example.com/font.ttf','file:///etc/passwd']:
            with self.assertRaises(FontUrlError):checked_url(url)
        self.assertEqual(checked_url('https://noonnu.cc/font_page/106',page=True),
                         'https://noonnu.cc/font_page/106')
    def test_resolve_css_with_import_and_woff(self):
        page="""<style>@import url('https://fonts.googleapis.com/css?family=Black+Han+Sans:400');
                  @font-face {src:url('//cdn.jsdelivr.net/example/Godo.woff2') format('woff2')}</style>"""
        got=font_css_candidates(page,'https://noonnu.cc/font_page/01')
        self.assertIn('https://cdn.jsdelivr.net/example/Godo.woff2',got)
        self.assertTrue(any('fonts.googleapis.com' in x for x in got))
    def test_cache_no_manual_download(self):
        # Use a synthetic SFNT file; GUI loader determines actual font validity.
        font=b'\x00\x01\x00\x00'+b'A'*2400
        with tempfile.TemporaryDirectory() as temp:
            url='https://noonnu.cc/font_page/01'
            with patch('kain_maple_translator.noonnu_fonts._resolve',return_value=['https://cdn.jsdelivr.net/font.ttf']), \
                 patch('kain_maple_translator.noonnu_fonts._fetch',return_value=font) as fetch:
                path=cached_font_from_noonnu(url,Path(temp))
                self.assertEqual(path.read_bytes(),font)
                self.assertEqual(cached_font_from_noonnu(url,Path(temp)),path)
                self.assertEqual(fetch.call_count,1)
    def test_obs_webfont_css_and_payload(self):
        obs=OBSChatSource()
        obs.set_font_data(b'\x00\x01\x00\x00'+b'A'*2400)
        obs.set_state([('Nick','채팅')],web_font=True)
        self.assertTrue(obs.state()['web_font'])
        self.assertIn('/font.ttf',OBS_HTML)
        self.assertIn('KainWebFont',OBS_HTML)

class FontPersistenceTests(unittest.TestCase):
    def test_font_url_config_persists(self):
        with tempfile.TemporaryDirectory() as dirname:
            dest=Path(dirname)/'config.json'
            value=load_config(dest)
            value['font_url']='https://noonnu.cc/font_page/106'
            save_config(value,dest)
            self.assertEqual(load_config(dest)['font_url'],value['font_url'])
    def test_font_obs_http(self):
        from urllib.request import urlopen
        obs=OBSChatSource(port=0)
        try:
            obs.start()
            data=b'\x00\x01\x00\x00'+b'A'*2500
            obs.set_font_data(data)
            obs.set_state([('Nick','안녕하세요')], web_font=True)
            with urlopen(obs.url+'font.ttf',timeout=3) as rsp:
                self.assertEqual(rsp.read(),data)
            with urlopen(obs.url+'state',timeout=3) as rsp:
                import json
                self.assertTrue(json.load(rsp)['web_font'])
        finally:obs.close()
