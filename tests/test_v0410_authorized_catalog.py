from __future__ import annotations
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kain_maple_translator.item_catalog import (
    CatalogError, ItemCatalog, install_catalog, current_catalog, catalog_path
)
from kain_maple_translator.natural_trade import _item
from kain_maple_translator.translation import Translator

class AuthorizedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p=patch.dict(os.environ,{'LOCALAPPDATA':self.tmp.name})
        p.start();self.addCleanup(p.stop)
        self.source=Path(self.tmp.name)/'provided.csv'
        with self.source.open('w',encoding='utf-8',newline='') as fh:
            wr=csv.DictWriter(fh,fieldnames=['name_en','name_ko','aliases_en'])
            wr.writeheader()
            wr.writerow({'name_en':'Glowing Example Hat','name_ko':'빛나는 예시 모자','aliases_en':'Glowing Ex Hat|Example Hat Glowing'})
            wr.writerow({'name_en':'Crimson Example Wand','name_ko':'진홍 예시 완드','aliases_en':''})

    def test_import_lookup_and_reuse(self):
        self.assertEqual(install_catalog(self.source),2)
        self.assertEqual(current_catalog().count,2)
        self.assertEqual(current_catalog().lookup('glowing ex hat'),'빛나는 예시 모자')
        self.assertEqual(_item('Glowing Example Hat'),'빛나는 예시 모자')
        self.assertTrue(catalog_path().is_file())

    def test_partial_word_not_replaced(self):
        install_catalog(self.source)
        self.assertEqual(current_catalog().replace('HiGlowing Example HatGreat'), 'HiGlowing Example HatGreat')
        self.assertEqual(current_catalog().replace('Selling Glowing Example Hat 10k'), 'Selling 빛나는 예시 모자 10k')

    def test_catalog_used_in_real_market_route(self):
        install_catalog(self.source)
        result=Translator().translate('S> Glowing Example Hat 10k','en-ko')
        self.assertIn('빛나는 예시 모자',result)

    def test_csv_json_support(self):
        target=Path(self.tmp.name)/'two.json'
        target.write_text(json.dumps({'items':[{'name_en':'Cobalt Example Boots','name_ko':'코발트 예시 부츠'}]}),encoding='utf-8')
        self.assertEqual(install_catalog(target),1)
        self.assertEqual(current_catalog().lookup('Cobalt Example Boots'),'코발트 예시 부츠')

    def test_conflict_and_bad_path_rejected(self):
        path=Path(self.tmp.name)/'bad.json'
        path.write_text(json.dumps([{'name_en':'same english','name_ko':'하나'},{'name_en':'SAME ENGLISH','name_ko':'둘'}]),encoding='utf-8')
        with self.assertRaises(CatalogError):install_catalog(path)
        self.assertFalse(catalog_path().exists())
        with self.assertRaises(CatalogError):install_catalog('https://meowdb.com/item-db/all')

    def test_valid_no_live_site_fetch(self):
        install_catalog(self.source)
        text=(Path(__file__).parents[1]/'kain_maple_translator/item_catalog.py').read_text(encoding='utf-8')
        self.assertNotIn('requests.get(',text)
        self.assertNotIn('urlopen(',text)

if __name__=='__main__': unittest.main()
