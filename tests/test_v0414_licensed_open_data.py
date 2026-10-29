from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kain_maple_translator.open_classic_data import (
    DATASETS, read_dataset, item_name_rows, status_text, counts)
from kain_maple_translator.classic_item_index import ClassicItemIndex
from scripts.fetch_classic_world_open_data import build, validate_export


class LicensedOpenDataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.src=self.root/'fake-publisher-exports'
        self.src.mkdir()
        for kind in DATASETS:
            self._save(kind,[])
        self._save('items',[
            {'id':'red-warrior-hat','name':'Red Warrior Hat','category':'equipment'},
            {'id':'hat','name':'Hat','category':'equipment'},
            {'id':'purple-slime-shoes','name':'Purple Slime Shoes','category':'equipment'},
        ])
        for kind in ('monsters','maps','npcs','quests'):
            self._save(kind,[{'id':'test-'+kind,'name':'Test '+kind}])
    def _save(self,kind,obj):
        (self.src/(kind+'.json')).write_text(json.dumps(obj),encoding='utf-8')
    def test_full_open_export_packaging_from_offline_fixtures(self):
        report=build(self.root,self.src)
        self.assertTrue(report['required_data_available'])
        self.assertEqual(len(report['datasets']),len(DATASETS))
        self.assertEqual(json.loads((self.root/'resources/open-classic/items.json').read_text())[-1]['name'],'Purple Slime Shoes')
        self.assertEqual(report['datasets'][0]['items'],3)
        self.assertEqual(len(report['datasets'][0]['sha256']),64)
    def test_missing_required_collection_reported_not_faked(self):
        (self.src/'items.json').unlink()
        report=build(self.root,self.src)
        self.assertFalse(report['required_data_available'])
        self.assertEqual(report['datasets'][0]['status'],'unavailable')
    def test_bad_schema_rejected(self):
        with self.assertRaises(ValueError):validate_export('items',b'[1]')
        with self.assertRaises(ValueError):validate_export('items',b'{}')
    def test_no_invented_korean_titles(self):
        with patch('kain_maple_translator.open_classic_data.data_directory',return_value=self.src):
            read_dataset.cache_clear()
            rows=item_name_rows()
            self.assertEqual(len(rows),3)
            self.assertEqual(rows[0]['name_ko'],'')
            index=ClassicItemIndex([])
            self.assertEqual(index.count,0)
            self.assertEqual(index.open_classic_count,2)
            self.assertEqual(index.find('S> Red Warrior Hat 10m')[0][2],'Red Warrior Hat')
            self.assertEqual(index.replace_verified('Red Warrior Hat 팝니다'),'Red Warrior Hat 팝니다')
            self.assertEqual(counts()['items'],3)
            read_dataset.cache_clear()
    def test_offline_existing_data_survives_failure(self):
        first=build(self.root,self.src)
        self.assertTrue(first['required_data_available'])
        (self.src/'items.json').unlink()
        again=build(self.root,self.src)
        self.assertTrue(again['required_data_available'])
        self.assertEqual(again['datasets'][0]['status'],'reused-cache')

if __name__=='__main__':unittest.main()
