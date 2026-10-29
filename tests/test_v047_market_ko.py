"""Regression: Free Market should never be displayed as 무료시장."""
import unittest
from unittest.mock import patch
from kain_maple_translator.translation import Translator
from kain_maple_translator.natural_trade import normalize_maple_market_name, polish_meso_units

class MarketNameTests(unittest.TestCase):
    def test_maple_localized_market_spellings(self):
        for raw in ('Free Market', 'FREE MARKET', 'Free-Market', 'FM',
                    '무료시장', '무료 시장', '프리마켓', '프리 마켓', '자유 시장'):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_maple_market_name(raw), '자유시장')

    def test_no_damage_to_non_market_terms(self):
        source='FM 20 / CH5, farming, 155k mesos'
        self.assertEqual(normalize_maple_market_name(source),
                         '자유시장 20 / CH5, farming, 155k mesos')
        self.assertEqual(polish_meso_units('무료 시장 3번방, 130 천 mesos'),
                         '자유시장 3번방, 13만 메소')

    def test_general_chat_posttranslate_uses_localized_name(self):
        # Simulate a generic offline model using the incorrect natural meaning.
        with patch('kain_maple_translator.translation.translate_generic',
                   return_value='저는 무료 시장에 갈 거예요'):
            self.assertEqual(Translator().translate('I will visit that market soon', 'en-ko'),
                             '저는 자유시장에 갈 거예요')

    def test_game_nickname_kept(self):
        with patch('kain_maple_translator.translation.translate_generic',
                   return_value='무료 시장에서 뵈어요'):
            self.assertEqual(Translator().translate('MarketGuy : see you at the market', 'en-ko'),
                             'MarketGuy : 자유시장에서 뵈어요')

if __name__=='__main__':
    unittest.main()
