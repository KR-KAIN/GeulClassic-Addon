"""v0.3.8 full glossary, style sync, pinned settings, dock width regressions."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from kain_maple_translator.chat_style import normalize_style, rgba_color, text_css
from kain_maple_translator.core import load_config, save_config
from kain_maple_translator.glossary_catalog import CATALOG, headwords, term_index
from kain_maple_translator.glossary import rule_translate, TERMS
from kain_maple_translator.layout import dock_to_side
from kain_maple_translator.obs_source import OBSChatSource

ROOT=Path(__file__).resolve().parents[1]

class MapleGlossaryStyleTests(unittest.TestCase):
    def test_full_glossary_category_coverage(self):
        self.assertEqual(len(CATALOG),11)
        self.assertGreaterEqual(len(headwords()),110)
        self.assertGreaterEqual(len(term_index()),150)
        self.assertGreaterEqual(len(TERMS),140)
        self.assertEqual(len({(e.casefold(),c) for e,_,c in headwords()}),len(headwords()))

    def test_headwords_and_game_chat_translate_locally(self):
        expected = {
            'AP Reset':'능력치 초기화', 'Lesser scroll':'하급 주문서',
            'Mushmom':'머쉬맘', 'store permit':'개인 상점 허가증',
            'pre-BB':'빅뱅 업데이트 이전', 'max level':'최대 스킬 레벨',
            'passive skill':'패시브 스킬', 'res met':'최소 판매가 충족',
        }
        for phrase,ko in expected.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(rule_translate(phrase,'en-ko'),ko)
        self.assertIsNone(rule_translate('Please clean my room','en-ko'))
        self.assertEqual(rule_translate('S> 60% scroll 2m','en-ko'),
                         '60% 주문서 200만 메소에 팝니다')

    def test_color_validation_and_split_styles(self):
        style=normalize_style({'nickname_color':'#FF0000', 'message_color':'#00ff00',
                               'background_color':'#123456', 'nickname_bold':True,
                               'message_underline':True, 'message_bold':False})
        self.assertEqual(style['nickname_color'],'#ff0000')
        self.assertIn('font-weight:bold',text_css(style,'nickname'))
        self.assertIn('text-decoration:underline',text_css(style,'message'))
        self.assertIn('17,34,51,0.550',rgba_color('#112233',55))
        bad=normalize_style({'nickname_color':'red; background:url(http://bad)',
                             'background_color':'#12345g','message_bold':'true'})
        self.assertEqual(bad['nickname_color'],'#b5d6ff')
        self.assertFalse(bad['message_bold'])

    def test_config_persists_pin_style_and_dock_width(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'settings.json'
            cfg=load_config(path)
            cfg['pin_settings_above_game']=True
            cfg['chat_style']['nickname_color']='#ffcc00'
            cfg['chat_style']['message_underline']=True
            cfg['chat_geometry']['dock_width']=617
            save_config(cfg,path)
            again=load_config(path)
            self.assertTrue(again['pin_settings_above_game'])
            self.assertEqual(again['chat_style']['nickname_color'],'#ffcc00')
            self.assertTrue(again['chat_style']['message_underline'])
            self.assertEqual(again['chat_geometry']['dock_width'],617)

    def test_dock_width_without_forcing_height(self):
        game=(500,80,800,600)
        monitor=(0,0,2200,1200)
        a,_=dock_to_side(game,monitor,300,150,'right',True)
        b,_=dock_to_side(game,monitor,617,150,'right',True)
        self.assertEqual(a[1],b[1]);self.assertEqual(a[3],b[3]);self.assertEqual(b[2],617)
        self.assertEqual(b[0],1307)

    def test_obs_style_is_serialized_and_html_uses_it(self):
        obs=OBSChatSource(port=0)
        try:
            url=obs.start()
            obs.set_state([('Nick','커닝 파퀘')],17,'Malgun Gothic',73,
                          {'nickname_color':'#aa6600','message_color':'#cc11dd',
                           'background_color':'#222244', 'nickname_bold':True,
                           'message_underline':True})
            with urlopen(url+'state',timeout=3) as resp:
                state=json.loads(resp.read().decode('utf-8'))
            self.assertEqual(state['chat_style']['nickname_color'],'#aa6600')
            self.assertTrue(state['chat_style']['message_underline'])
            with urlopen(url,timeout=3) as resp:
                page=resp.read().decode('utf-8')
            self.assertIn('style.nickname_color',page)
            self.assertIn('style.message_color',page)
            self.assertIn('style.background_color',page)
            self.assertIn("style.message_underline",page)
        finally:
            obs.close()

    def test_ui_contains_new_controls_and_edit_resizing(self):
        source=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('self.pin_settings=QCheckBox',source)
        self.assertIn("cfg.get('pin_settings_above_game'",source)
        self.assertIn('self.cfg[\'pin_settings_above_game\']=dlg.pin_settings.isChecked()',source)
        self.assertIn('self.cfg[\'chat_geometry\'][\'dock_width\']=dlg.dock_width.value()',source)
        self.assertIn("g['dock_width']=int(self.chat.width())",source)
        self.assertIn('self.msg_underline=QCheckBox',source)
        self.assertIn('picker = QColorDialog(QColor(self.color_inputs[key].text()), self)',source)
        self.assertIn('QColorDialog.ColorDialogOption.DontUseNativeDialog',source)
        self.assertIn('self._color_picker_open = True',source)
        self.assertIn('self.chat.apply_style',source)
        self.assertIn("self.cfg.get('chat_style',{})",source)

if __name__ == '__main__':
    unittest.main()
