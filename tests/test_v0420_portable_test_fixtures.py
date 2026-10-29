"""Guard against Windows CP949 default encoding corrupting Korean fixture JSON."""
import ast
import json
import tempfile
import unittest
from pathlib import Path
from kain_maple_translator.item_catalog import _read_rows


class PortableKoreanFixtureTests(unittest.TestCase):
    def test_all_gms_kms_test_text_writes_declare_utf8(self):
        path = Path(__file__).with_name('test_v0419_item_api_sync.py')
        module = ast.parse(path.read_text(encoding='utf-8'))
        writes = [call for call in ast.walk(module)
                  if isinstance(call, ast.Call)
                  and isinstance(call.func, ast.Attribute)
                  and call.func.attr == 'write_text']
        self.assertGreaterEqual(len(writes), 4)
        for call in writes:
            encoded = [kw.value.value for kw in call.keywords
                       if kw.arg == 'encoding' and isinstance(kw.value, ast.Constant)]
            self.assertEqual(encoded, ['utf-8'], 'All test fixtures must explicitly write UTF-8')

    def test_manual_korean_catalog_roundtrip_as_utf8(self):
        with tempfile.TemporaryDirectory() as folder:
            sample = Path(folder) / 'authorized-items.json'
            name = '수동 모자'
            sample.write_text(json.dumps({'items': [{'name_en': 'Royal Maple Hat',
                                                    'name_ko': name}]}, ensure_ascii=False),
                              encoding='utf-8')
            self.assertEqual(_read_rows(sample)[0]['name_ko'], name)
            self.assertIn(name.encode('utf-8'), sample.read_bytes())


if __name__ == '__main__':
    unittest.main()
