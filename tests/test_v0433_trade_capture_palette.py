"""v0.4.33: real Serpent's Tongue mixed-KO listing, pale banners and undimmed ROI."""
from pathlib import Path
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.natural_trade import equipment_no_slots_override, split_market_location
from kain_maple_translator.translation import Translator
from kain_maple_translator.megaphone import detect_band, row_appearance
from kain_maple_translator.row_admission import classified_chat_rows, _CLASSIFIED_CACHE
from kain_maple_translator.vision import Line

ROOT=Path(__file__).parents[1]


class EquipmentAndLocation(unittest.TestCase):
    def setUp(self):
        self.translator=Translator(body_only=True)

    def test_actual_76_attack_no_slots_and_incomplete_market_location(self):
        raw="SERPENT'S TONGUE 76 공격력 +4 no slots left ch 13 fm"
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('AI must not be called')):
            result=self.translator.translate(raw,'en-ko')
        for expected in ('장팔사모','76','+4','업그레이드 횟수 0','13채널 자유시장','방 번호 미기재'):
            self.assertIn(expected,result)
        self.assertNotIn('17번 방',result)
        self.assertNotIn('no slots left',result)
        self.assertNotIn('TONGUE',result)

    def test_ocr_quote_variants_of_verified_item_name(self):
        for name in ("SERPENT''S TONGUE", 'SERPENT"S TONGUE', 'SERPENT”S TONGUE'):
            self.assertIn('장팔사모', self.translator.translate_fast(
                name+' 76 공격력 +4 no slots left ch 13 fm'))

    def test_explicit_market_room(self):
        raw="SERPENT'S TONGUE 76 공격력 +4 no slots left ch13 fm17"
        result=self.translator.translate_fast(raw)
        self.assertIn('13채널 자유시장 17번 방',result)
        self.assertNotIn('방 번호 미기재',result)

    def test_partial_market_location_but_not_fake_room(self):
        self.assertEqual(split_market_location('S> WG 220k ch 13 fm'),
                         ('S> WG 220k','13채널 자유시장 (방 번호 미기재)'))
        self.assertIsNone(split_market_location('S> WG 220k ch 13 family'))
        self.assertIsNone(split_market_location('S> WG 220k ch0 fm'))

    def test_absent_stat_and_unrelated_sentences_not_guessed(self):
        for txt in ('SERPENTS TONGUE 76 atk +4 ch13 fm',
                    'Can we meet near ch 13 fm?',
                    'SERPENTS TONGUE 76 공격력 no slots left',
                    'SERPENTS TONGUE 76 공격력 +4 no slots left x'):
            self.assertIsNone(equipment_no_slots_override(txt),txt)

    def test_previous_sp_reset_unchanged(self):
        self.assertEqual(self.translator.translate_fast('S> SP resets 60k ch31 FM17'),
                         'SP 초기화권 팝니다. 가격 6만 메소 (31채널 자유시장 17번 방)')


class PastelSourceEvidence(unittest.TestCase):
    def setUp(self):
        _CLASSIFIED_CACHE.clear()

    def frame(self,rgb=(248,213,228),color=(130,26,89),txt='Alice ; S> WG 220k'):
        im=np.full((35,650,3),rgb[::-1],dtype=np.uint8)
        cv2.putText(im,txt,(6,25),cv2.FONT_HERSHEY_SIMPLEX,.68,color[::-1],1,cv2.LINE_AA)
        return im

    def test_pale_pink_banner_even_when_saturation_below_55(self):
        im=self.frame()
        self.assertEqual('pink',detect_band(im,(4,5,240,27)).tone)
        appearance=row_appearance(im,(4,5,240,27),(0,0),'S> WG 220k')
        self.assertEqual('super',appearance['kind'])
        rows=classified_chat_rows([Line('Alice ; S> WG 220k',.99,(4,5,240,27))],im,0,0)
        self.assertEqual(rows[0]['kind'],'super',rows)
        self.assertEqual(rows[0]['prefix'],'[고확]')

    def test_empty_solid_pastel_is_not_banner(self):
        im=self.frame()
        im[:]=np.array([228,213,248],dtype=np.uint8)
        self.assertEqual('none',detect_band(im,(4,5,240,27)).tone)

    def test_plain_white_chat_stays_normal(self):
        im=self.frame((26,25,24),(248,248,248))
        appearance=row_appearance(im,(4,5,240,27),(0,0),'hi')
        self.assertEqual('normal',appearance['kind'])

    def test_previous_bright_yellow_banner_unchanged(self):
        im=self.frame((247,194,34),(30,30,30))
        self.assertEqual('yellow',detect_band(im,(4,5,240,27)).tone)


class NoFullscreenDimmer(unittest.TestCase):
    def test_roi_selection_paints_border_not_black_fullscreen(self):
        src=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        selector=src.split('class RegionSelector(QWidget):',1)[1].split('class Glass(QWidget):',1)[0]
        self.assertIn('p.fillRect(self.rect(), QColor(0, 0, 0, 2))',selector)
        self.assertNotIn('QColor(2,8,16,135)',selector)
        self.assertNotIn('CompositionMode_Clear',selector)
        self.assertIn('p.drawRect(rect)',selector)
        self.assertIn('WA_TranslucentBackground',selector)
