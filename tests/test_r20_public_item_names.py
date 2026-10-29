"""R20: the public build knows the same item names as a build with meowdb.

resources/meowdb stays out of the public repository. Its table was mostly
Korean-client (KMS) names joined to Classic World items; resources/item-info/
kms-names.json now carries those names from game data alone.
"""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import kain_maple_translator.classic_item_index as cii

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / 'resources' / 'item-info' / 'kms-names.json'
SCRIPT = ROOT / 'scripts' / 'fetch_kms_names.py'


def _clear_name_caches():
    cii._CACHED = None
    cii._CACHED_KEY = None
    from kain_maple_translator import item_info, ko_trade
    item_info._korean_names.cache_clear()
    ko_trade._game_names.cache_clear()
    ko_trade._nospace_names.cache_clear()


class WithoutMeowdb(unittest.TestCase):
    """Exactly what a fresh public clone sees: no resources/meowdb."""

    def setUp(self):
        self.patch = patch.object(cii, 'meowdb_path', lambda: Path('Z:/missing/meowdb-items-ko.json'))
        self.patch.start()
        _clear_name_caches()

    def tearDown(self):
        self.patch.stop()
        _clear_name_caches()

    def test_cash_and_pet_names_are_known(self):
        index = cii.current_index()
        self.assertEqual(index.meowdb_count, 0)
        self.assertGreater(index.kms_count, 2000)
        for en, ko in {'Megaphone': '확성기', 'Super Megaphone': '고성능 확성기',
                       'Brown Kitty': '갈색고양이', 'Water of Life': '생명의 물',
                       'Pet Name Tag': '펫작명하기'}.items():
            with self.subTest(item=en):
                self.assertEqual(index.by_en[en.casefold()][1], ko)

    def test_korean_post_to_english(self):
        from kain_maple_translator.ko_trade import korean_post
        self.assertEqual(korean_post('갈색고양이 팝니다 50만', lambda v: v), 'S> Brown Kitty 500k')
        self.assertEqual(korean_post('생명의 물 팝니다 20만', lambda v: v), 'S> Water of Life 200k')

    def test_classic_world_korean_still_wins(self):
        # Classic World's own name, not a Korean-client one
        self.assertEqual(cii.current_index().by_en['work gloves'][1], '노가다 목장갑')
        self.assertEqual(cii.current_index().by_en['iron ore'][1], '철 원석')

    def test_one_word_items_traded_every_day(self):
        # left out before R20.1 by a stricter length rule than meowdb's
        index = cii.current_index()
        for en, ko in {'Sapphire': '사파이어', 'Amethyst': '자수정', 'Crossbow': '석궁',
                       'Shinkita': '신기타', 'Aquamarine': '아쿠아마린'}.items():
            with self.subTest(item=en):
                self.assertEqual(index.by_en[en.casefold()][1], ko)

    def test_one_word_hair_names_stay_words(self):
        index = cii.current_index()
        for word in ('casanova', 'antagonist', 'pigtails', 'veronica'):
            with self.subTest(word=word):
                self.assertFalse((index.by_en.get(word) or ('', ''))[1])

    def test_half_english_names_use_the_korean_client(self):
        index = cii.current_index()
        self.assertEqual(index.by_en['speed potion'][1], '속도향상의 물약')
        self.assertEqual(index.by_en['red thief hood'][1], '레드 시프 후드')


class NameTable(unittest.TestCase):
    def test_table_is_game_data_only(self):
        data = json.loads(TABLE.read_text(encoding='utf-8'))
        self.assertIn('KMS', data['source'])
        self.assertNotIn('meowdb', data['source'].lower())
        self.assertGreater(len(data['items']), 2000)
        self.assertTrue(all(row['ko'] and row['en'] for row in data['items']))
        self.assertNotIn('meowdb.com', SCRIPT.read_text(encoding='utf-8'))

    def test_build_rules(self):
        spec = importlib.util.spec_from_file_location('fetch_kms_names', SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        items = [(1, 'Work Gloves', '노가다 목장갑'),   # Classic World Korean: kept, not listed
                 (2, 'Brown Kitty', ''),               # same ID, GMS confirms the name
                 (3, 'Megaphone', ''),                 # renumbered: found by English name
                 (4, 'Red Bandana', ''),               # two different Korean names: skipped
                 (5, 'Reused Id', ''),                 # same ID but GMS says another item
                 (6, 'Speed Potion', 'Speed 포션'),     # half English: the KMS name goes first
                 (7, 'Glove Scroll', '장갑 Attack 주문서'),  # half English, no KMS name: kept
                 (8, 'Casanova', '카사노바', 'Character')]  # one-word hair: a word in chat
        kms = {'2': '갈색고양이', '71': '확성기', '80': '빨간 두건', '81': '빨간 반다나', '5': '엉뚱한 이름',
               '90': '속도향상의 물약'}
        gms = [{'2': 'Brown Kitty', '71': 'Megaphone', '80': 'Red Bandana', '81': 'Red Bandana',
                '5': 'Something Else', '90': 'Speed Potion'}]
        out, stats = mod.build(items, kms, gms)
        self.assertEqual({r['en']: (r['ko'], r['by'], r.get('over_cw', False)) for r in out},
                         {'Brown Kitty': ('갈색고양이', 'id', False), 'Megaphone': ('확성기', 'name', False),
                          'Speed Potion': ('속도향상의 물약', 'name', True)})
        self.assertEqual(stats['has_cw_korean'], 2)
        self.assertEqual(stats['ambiguous'], 1)
        self.assertEqual(stats['not_found'], 1)
        self.assertEqual(stats['one_word_hair'], 1)


if __name__ == '__main__':
    unittest.main()
