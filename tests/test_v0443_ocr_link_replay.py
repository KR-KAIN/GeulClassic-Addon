"""Regression: real Windows build reported missing R in linked denim item."""
import unittest
from kain_maple_translator.ocr_item_aliases import repair_confirmed_item_link
from kain_maple_translator.translation import Translator


class KnownBracketLinkRepairTests(unittest.TestCase):
    def setUp(self):
        self.translator = Translator(body_only=True)

    def test_confirmed_missing_r_only_in_link(self):
        source = '[Denim Winkled Skirt] SELLING FOR 30k OBO'
        self.assertEqual(repair_confirmed_item_link(source),
                         '[Denim Wrinkled Skirt] SELLING FOR 30k OBO')
        result = self.translator.translate_fast(source)
        self.assertIsNotNone(result)
        for required in ('[청 주름 치마]', '3만', '협의'):
            self.assertIn(required, result)

    def test_valid_item_unchanged(self):
        source = '[Denim Wrinkled Skirt] SELLING FOR 30k OBO'
        self.assertEqual(repair_confirmed_item_link(source), source)

    def test_unknown_items_are_never_fuzzy_repaired(self):
        for name in ('[Denim Winkled Skirts]', '[Denim Winkle Skirt]',
                     '[Denim Wrinkled shirt]', '[데님 스커트]', '[Wingled Hat]'):
            self.assertEqual(repair_confirmed_item_link(name), name)

    def test_not_in_prose_nickname_or_price(self):
        source = 'Denim Winkled Skirt : SELLING FOR 30k OBO'
        self.assertEqual(repair_confirmed_item_link(source), source)
        source = '[Denim Winkled Skirt] SELLING FOR 30k OBO [Other Item]'
        result = repair_confirmed_item_link(source)
        self.assertIn('[Other Item]',result)
        self.assertIn('30k OBO',result)

    def test_no_changes_to_korean_item_link(self):
        source='[아대 공격력 주문서 60%] S> 300k'
        self.assertEqual(repair_confirmed_item_link(source), source)

    def test_fast_and_general_translation_share_repair(self):
        original='[Denim Winkled Skirt] SELLING FOR 30k OBO'
        result=self.translator.translate_fast(original)
        self.assertIn('[청 주름 치마]', result)
        self.assertNotIn('Winkled', result)

if __name__=='__main__': unittest.main()
