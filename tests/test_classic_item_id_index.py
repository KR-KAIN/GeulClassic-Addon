import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kain_maple_translator.classic_item_index import ClassicItemIndex, replace_unverified_item_names
from scripts.build_classic_index import extract_items, build_index


class CompleteItemIDIndexTests(unittest.TestCase):
    def test_wz_nested_ids(self):
        xml=b'<imgdir name="Eqp"><imgdir name="Eqp"><imgdir name="Cap"><imgdir name="1000010"><string name="name" value="Nordic Steel Helm"/></imgdir><imgdir name="1000011"><string name="name" value="Blue Hat"/></imgdir></imgdir></imgdir></imgdir>'
        self.assertEqual(extract_items(xml),{'1000010':'Nordic Steel Helm','1000011':'Blue Hat'})

    def test_matching_joins_by_id_without_guessing(self):
        from unittest.mock import patch
        with patch('kain_maple_translator.classic_item_index.meowdb_pairs', return_value=[]), \
                patch('kain_maple_translator.classic_item_index.mcw_pairs', return_value=[]):
            self._joins_by_id()

    def _joins_by_id(self):
        idx=ClassicItemIndex([{'item_id':'1000010','name_en':'Nordic Steel Helm','name_ko':'노르딕 강철 투구'}, {'item_id':'1000020','name_en':'Wooden Sword','name_ko':''}])
        self.assertEqual(idx.count,2)
        self.assertEqual(idx.localized_count,1)
        self.assertEqual(idx.replace_verified('S> Nordic Steel Helm 10m'),'S> 노르딕 강철 투구 10m')
        self.assertEqual(idx.replace_verified('Wooden Sword 팝니다'),'Wooden Sword 팝니다')

    def test_do_not_change_chat_without_market_context(self):
        idx=ClassicItemIndex([{'item_id':'1000010','name_en':'Nordic Steel Helm','name_ko':''}])
        with patch('kain_maple_translator.classic_item_index.current_index',return_value=idx):
            self.assertEqual(replace_unverified_item_names('Nordic Steel Helm 좋아요',lambda _: '노르딕 투구'),'Nordic Steel Helm 좋아요')

    def test_offline_fallback_and_cache(self):
        import kain_maple_translator.classic_item_index as mod
        idx=ClassicItemIndex([{'item_id':'1000010','name_en':'Nordic Steel Helm','name_ko':''}])
        with tempfile.TemporaryDirectory() as folder:
            mod._AUTOTRANSLATIONS=None
            with patch.object(mod,'current_index',return_value=idx),patch.object(mod,'_auto_cache_path',return_value=Path(folder)/'cache.json'):
                calls=[]
                def tr(t): calls.append(t);return '노르딕 강철 투구'
                self.assertEqual(replace_unverified_item_names('Nordic Steel Helm 팝니다',tr),'노르딕 강철 투구 팝니다')
                self.assertEqual(replace_unverified_item_names('Nordic Steel Helm 팝니다',tr),'노르딕 강철 투구 팝니다')
                self.assertEqual(calls,['Nordic Steel Helm'])
            mod._AUTOTRANSLATIONS=None

    def test_preserve_ambiguous_short_words(self):
        idx=ClassicItemIndex([{'item_id':'1000010','name_en':'Hat','name_ko':'모자'}])
        self.assertEqual(idx.replace_verified('That Hat was cool'),'That Hat was cool')

    def test_offline_local_xml_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for language,name in [('en','Red Shirt'),('ko','빨간 셔츠')]:
                d=root/'item-sources'/language
                d.mkdir(parents=True)
                xml=f'<imgdir name="Eqp"><imgdir name="Eqp"><imgdir name="Coat"><imgdir name="1040001"><string name="name" value="{name}"/></imgdir></imgdir></imgdir></imgdir>'
                (d/'Eqp.img.xml').write_text(xml,encoding='utf-8')
            result=build_index(root,offline=True)
            self.assertEqual(result['total_ids'],1)
            self.assertEqual(result['korean_names'],1)
            d=json.loads((root/'resources/item-ids/gms-v83-index.json').read_text(encoding='utf-8'))
            self.assertEqual(d['items'][0]['name_ko'],'빨간 셔츠')

if __name__=='__main__': unittest.main()
