"""The 2026-10-24 live screenshot: avoid half-English megaphone listings."""
from __future__ import annotations
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from kain_maple_translator.core import should_translate_body
from kain_maple_translator.megaphone_item_translation import (
    localize_equipment_stats, localized_item_text, translate_announcement_trade,
)
from kain_maple_translator.market_item_terms import replace_market_items
from kain_maple_translator.translation import Translator


class ScreenshotMegaphoneItemNames(unittest.TestCase):
    def setUp(self):
        self.translator = Translator()

    def translate_without_model(self, source: str) -> str:
        with patch('kain_maple_translator.translation.translate_generic',
                   side_effect=AssertionError('trade items must bypass general MT')):
            return self.translator.translate(source, 'en-ko')

    def test_repeated_seller_markers_and_stats_from_screenshot(self):
        source = 'Fairy s> Fairy Wing s> lvl 35 archer gloves 3 dex 2 crit'
        result = self.translate_without_model(source)
        self.assertIn('요정의 날개 팝니다', result)
        self.assertIn('35레벨 궁수 장갑 (민첩 +3, 크리티컬 +2) 팝니다', result)
        self.assertNotIn('Fairy Wing', result)
        self.assertNotIn('archer gloves', result)
        self.assertNotIn(' 3 dex 2 crit', result)
        self.assertTrue(result.startswith('Fairy · ')) # Ambiguous fragment is not made into an item.

    def test_linked_item_pm_offer_from_screenshot(self):
        self.assertEqual(self.translate_without_model("[Gentleman's Mustache] PM offer"),
                         '[신사의 콧수염] 가격 제안은 귓말로 주세요')

    def test_korean_bracketed_item_with_tiny_english_request_is_translated(self):
        source='[스틸 슬레인] PMO'
        self.assertTrue(should_translate_body(source, .9))
        self.assertEqual(self.translate_without_model(source),
                         '[스틸 슬레인] 가격 제안은 귓말로 주세요')

    def test_exact_name_only_inside_trade_context(self):
        self.assertEqual(replace_market_items('Fairy Wing'), '요정의 날개')
        self.assertEqual(self.translate_without_model('S> Fairy Wing'), '요정의 날개 팝니다')
        self.assertEqual(self.translate_without_model('S> [요정의 날개]'), '[요정의 날개] 팝니다')
        self.assertFalse(should_translate_body('한글 아이템 팝니다',.90))

    def test_do_not_touch_player_nicknames_and_urls(self):
        self.assertEqual(self.translate_without_model('FairyWing : https://guild.gg'),
                         'FairyWing : https://guild.gg')
        self.assertEqual(translate_announcement_trade('https://website.gg s> Fairy Wing'),None)
        self.assertIsNone(translate_announcement_trade('I really enjoy fairy stories'))

    def test_missing_ocr_data_is_preserved(self):
        value=self.translate_without_model('??? s> GloveUnknownXYZ')
        self.assertIn('GloveUnknownXYZ',value)
        self.assertIn('???',value)
        self.assertNotIn('요정의 날개',value)

    def test_single_marker_with_explicit_equipment_stats(self):
        output=self.translate_without_model('S> lvl 35 archer gloves 3 dex 2 crit')
        self.assertEqual(output,'35레벨 궁수 장갑 (민첩 +3, 크리티컬 +2) 팝니다')

    def test_existing_transliterated_fairy_item(self):
        result=self.translate_without_model('S> 페어리 윙 S> lvl 35 archer gloves 3 dex 2 crit')
        self.assertIn('요정의 날개 팝니다',result)

    def test_stat_parser_requires_full_context(self):
        self.assertEqual(localize_equipment_stats('lvl 35 archer gloves 3 dex 2 crit'),
                         '35레벨 궁수 장갑 (민첩 +3, 크리티컬 +2)')
        self.assertEqual(localize_equipment_stats('3 dex 2 crit'), '3 dex 2 crit')
        self.assertEqual(localize_equipment_stats('lvl 35 random gloves 3 dex 2 crit'),
                         'lvl 35 random gloves 3 dex 2 crit')
        self.assertEqual(localize_equipment_stats('lvl 35 archer gloves 3 dex 2 crit'),
                         '35레벨 궁수 장갑 (민첩 +3, 크리티컬 +2)')

    def test_manual_catalog_overrides_curated_and_does_not_mutate_file(self):
        from kain_maple_translator import item_catalog
        import json
        with TemporaryDirectory() as tmp:
            path=Path(tmp)
            manual=path/'KAINMapleTranslator'/'authorized-items.json'
            manual.parent.mkdir(parents=True)
            manual.write_text(json.dumps({'items':[{'name_en':'Fairy Wing',
                                                      'name_ko':'사용자가 정한 이름'}]},ensure_ascii=False),encoding='utf8')
            previous=manual.read_bytes()
            with patch.dict(os.environ,{'LOCALAPPDATA':str(path)}):
                item_catalog._CATALOG=None
                item_catalog._CACHE_STAMP=None
                try:
                    self.assertEqual(self.translate_without_model('S> Fairy Wing'),
                                     '사용자가 정한 이름 팝니다')
                    self.assertEqual(manual.read_bytes(),previous)
                finally:
                    item_catalog._CATALOG=None
                    item_catalog._CACHE_STAMP=None

    def test_id_synced_names_override_curated_when_not_manually_mapped(self):
        from kain_maple_translator import classic_item_index
        with patch('kain_maple_translator.classic_item_index.current_index') as current:
            current.return_value.replace_verified.side_effect=lambda v: v.replace('Fairy Wing','ID동기화 이름')
            self.assertEqual(localized_item_text('Fairy Wing'), 'ID동기화 이름')


if __name__=='__main__':
    unittest.main()
