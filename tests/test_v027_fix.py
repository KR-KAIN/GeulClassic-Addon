"""v0.2.7 regressions targeting the user's Maple screenshot and reported UI bugs."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kain_maple_translator.core import parse_chat_line, merge_chat_ocr, load_config, save_config
from kain_maple_translator.translation import Translator, TranslationError

class B:
    def __init__(self, text, x, y, w=180):
        self.text=text
        self.rect=(x,y,w,14)
        self.confidence=.9

class Regression027(unittest.TestCase):
    def test_channel_badges_are_not_nicknames(self):
        self.assertEqual(parse_chat_line('poyhau CH 09 : S>Cute Mouse Ears 3m'),
                         ('poyhau','S>Cute Mouse Ears 3m'))
        self.assertEqual(parse_chat_line('Kayztah CH09 : B > average pan lid'),
                         ('Kayztah','B > average pan lid'))
        self.assertEqual(parse_chat_line('Mabiandragon (CH09) : LV50 CLAW 34ATT'),
                         ('Mabiandragon','LV50 CLAW 34ATT'))
        self.assertEqual(parse_chat_line('MemoryShadow ✿ : S> kumbi 380k'),
                         ('MemoryShadow','S> kumbi 380k'))
        self.assertEqual(parse_chat_line('UncleStatus : cleric was my main'),
                         ('UncleStatus','cleric was my main'))
        self.assertIsNone(parse_chat_line('CH09'))
        self.assertIsNone(parse_chat_line('S>Pan lid 2m'))

    def test_chat_boxes_with_badge(self):
        boxes=[B('Kayztah',(275),630,75),B('CH09 :',(352),630,55),B('B > average pan lid',(410),630,200)]
        rows=merge_chat_ocr(boxes)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['nickname'],'Kayztah')
        self.assertEqual(rows[0]['body'],'B > average pan lid')

    def test_geometry_and_font_settings_saved(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'cfg.json'
            cfg=load_config(file)
            cfg['chat_geometry'].update(width=612,height=285,overlay_dx=-12,overlay_dy=21,dock_match_height=False)
            cfg['font_size']=17
            cfg['font_path']='C:/Users/Player/Downloads/MapleFont.otf'
            save_config(cfg,file)
            read=load_config(file)
            self.assertEqual(read['chat_geometry']['width'],612)
            self.assertEqual(read['chat_geometry']['overlay_dy'],21)
            self.assertFalse(read['chat_geometry']['dock_match_height'])
            self.assertEqual(read['font_size'],17)

    def test_local_translation_model_test(self):
        with patch('kain_maple_translator.translation.translate_generic',return_value='어디 가세요?') as model:
            tr=Translator('argos')
            self.assertEqual(tr.offline_test('en-ko'),'어디 가세요?')
            self.assertEqual(model.call_count,1)
        with patch('kain_maple_translator.translation.translate_generic',side_effect=TranslationError('Model missing')):
            with self.assertRaisesRegex(TranslationError,'Model missing'):
                Translator().offline_test('en-ko')

    def test_ui_has_edit_state_drag_resize_and_dock_guard(self):
        text=(Path(__file__).resolve().parents[1]/'kain_maple_translator'/'main.py').read_text(encoding='utf-8')
        for item in ('QSizeGrip(self)','self.card.installEventFilter(self)','self.edit.toggled.connect(self.edit_changed)',
                     'self.chat.set_editable(enabled)','self.chat.geometry_edited.connect(self.geometry_edited)',
                     'bool(self.geometry_pref(\'dock_match_height\',True))',
                     '자석: 바깥 공간 부족','enable_obs_window_capture(self.chat)','self.worker.status.connect(self.left.set_status)',
                     'QFontDatabase.addApplicationFont'):
            self.assertIn(item,text)
        self.assertNotIn('if x < mon.left()+6 or x+width > mon.right()-6:',text)

if __name__=='__main__':
    unittest.main()
