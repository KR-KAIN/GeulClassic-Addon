import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.sync_gms_kms_items import (PAGE, match_ids, parse_item_rows, retrieve,
                                         sync, local_db_path)
from kain_maple_translator import classic_item_index as index

class ApiGmsKmsIDTests(unittest.TestCase):
    def test_accepts_real_api_shape(self):
        items=[{'Id':2000000,'Name':'Red Potion'}, {'Id':2000001,'Name':'Blue Potion'},
               {'Id':2000002,'Name':'Red Potion'}]
        ko=[{'Id':2000000,'Name':'빨간 포션'}, {'Id':2000001,'Name':'파란 포션'},
            {'Id':2000002,'Name':'분홍 물약'}]
        parsed_en=parse_item_rows(items,'GMS')
        parsed_ko=parse_item_rows(ko,'KMS')
        result=match_ids(parsed_en,parsed_ko)
        self.assertEqual(result['id_matched'],3)
        self.assertEqual(result['safe_name_rows'],1)
        self.assertEqual(result['ambiguous_english_rows'],2)
        self.assertEqual(result['items'][0]['name_ko'],'파란 포션')

    def test_no_wrong_ko_english_or_bad_ids(self):
        parsed=parse_item_rows([{'Id':2000000,'Name':'Red Potion'}, {'Id':2000001,'Name':'초록 물약'},
                                {'Id':'notanid','Name':'Bad'}, {'Id':2000002,'Name':'Potion'}],'GMS')
        self.assertEqual(len(parsed),2)
        self.assertNotIn('2000001',parsed)

    def test_no_db_write_when_fetch_fails(self):
        from urllib.error import URLError
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'names.json'
            dest.write_text('previous data', encoding='utf-8')
            def fail(url): raise URLError('offline')
            with self.assertRaises(URLError):
                sync(loader=fail,output=dest)
            self.assertEqual(dest.read_text(),'previous data')

    def test_kms_65_fail_284_fallback_and_runtime_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'names.json'
            def loader(url):
                if '/KMS/65/' in url:
                    raise ValueError('KMS 65 not uploaded')
                if 'startPosition=4000' in url:
                    return []
                if '/GMS/62/' in url:
                    return [{'Id':1003000+i,'Name':f'Unique Maple Item {i}'} for i in range(25)]
                return [{'Id':1003000+i,'Name':f'고유 메이플 아이템 {i}'} for i in range(25)]
            result=sync(loader=loader,pause=0,output=output)
            self.assertEqual(result['kms_version'],284)
            self.assertEqual(result['id_matched'],25)
            self.assertEqual(result['safe_name_rows'],25)
            self.assertEqual(result['skipped_kms_versions']['65'].startswith('ValueError'),True)
            new=index._safe_synced_rows(output)
            idx=index.ClassicItemIndex([{'item_id':'1003000','name_en':'Unique Maple Item 0','name_ko':'수작업 확인 명칭'}],new)
            self.assertEqual(idx.replace_verified('Unique Maple Item 0 / Unique Maple Item 1'),
                             '수작업 확인 명칭 / 고유 메이플 아이템 1')
            self.assertEqual(idx.synced_count,24)

    def test_existing_manual_catalog_untouched(self):
        from kain_maple_translator.item_catalog import _read_rows
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'gms-kms-item-names.json'
            old=Path(folder)/'authorized-items.json'
            old.write_text(json.dumps({'items':[{'name_en':'Royal Maple Hat','name_ko':'수동 모자'}]},ensure_ascii=False), encoding='utf-8')
            def loader(url):
                if 'startPosition=4000' in url: return []
                if '/GMS/' in url: return [{'Id':1003000+i,'Name':f'Unique Maple Item {i}'} for i in range(25)]
                return [{'Id':1003000+i,'Name':f'고유 아이템 {i}'} for i in range(25)]
            sync(loader=loader,pause=0,output=dest)
            self.assertEqual(_read_rows(old)[0]['name_ko'],'수동 모자')

    def test_cache_reloads_new_local_sync_without_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            bundled=Path(folder)/'gms-v83-index.json'
            bundled.write_text(json.dumps({'items':[{'item_id':'2000000','name_en':'Red Potion','name_ko':''}]}), encoding='utf-8')
            dynamic=Path(folder)/'gms-kms-item-names.json'
            with patch.object(index,'bundled_index_path',return_value=bundled),patch.object(index,'synced_names_path',return_value=dynamic):
                index._CACHED=None;index._CACHED_KEY=None
                self.assertEqual(index.current_index().localized_count,0)
                dynamic.write_text(json.dumps({'source':'maplestory.io','items':[{'item_id':'2000000','name_en':'Red Potion','name_ko':'빨간 포션'}]}), encoding='utf-8')
                self.assertEqual(index.current_index().localized_count,1)
            index._CACHED=None;index._CACHED_KEY=None

    def test_item_api_version_and_host_fixed(self):
        seen=[]
        def loader(url):
            seen.append(url)
            return [{'Id':1000000,'Name':'Maple Wand'}]
        items=retrieve('GMS',62,loader=loader,pause=0)
        self.assertEqual(items['1000000'],'Maple Wand')
        self.assertEqual(seen[0], 'https://maplestory.io/api/GMS/62/item?startPosition=0&count=4000')
        with self.assertRaises(ValueError):retrieve('GMS',-1,loader=loader)

if __name__=='__main__': unittest.main()
