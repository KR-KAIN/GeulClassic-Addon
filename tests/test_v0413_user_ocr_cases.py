import unittest
from unittest.mock import patch
from kain_maple_translator.chat_safety import has_url_or_domain, should_keep_untranslated
from kain_maple_translator.market_item_terms import replace_market_items
from kain_maple_translator.natural_trade import trade_override
from kain_maple_translator.translation import Translator


class UserOCRCases(unittest.TestCase):
    def test_copied_web_links_not_translated(self):
        urls=('https://mesolane.gg',
              'https://meowdb.com/msclassic/ko/item-db',
              'https : // mesolane.gg',
              'www.mesolane.gg')
        translator=Translator()
        with patch('kain_maple_translator.translation.translate_generic', side_effect=AssertionError('url passed to MT')):
            for url in urls:
                with self.subTest(url=url):
                    self.assertTrue(has_url_or_domain(url))
                    self.assertEqual(translator.translate(url, 'en-ko'), url)

    def test_url_inside_nickname_kept(self):
        translator=Translator()
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('URL passed to MT')):
            self.assertEqual(translator.translate('Ravers : https://mesolane.gg/market','en-ko'), 'Ravers : https://mesolane.gg/market')

    def test_multi_item_names(self):
        self.assertEqual(trade_override('S> baby wings/Toy hammer/kitty shoes'),
                        '아기 날개 / 장난감 망치 / 고양이 신발 팝니다')

    def test_korean_fan_and_pm(self):
        result=trade_override('S> +3 Clean KOREAN FAN pm')
        self.assertIn('태극부채',result)
        self.assertIn('+3',result)
        self.assertIn('미강화',result)
        self.assertIn('귓말 주세요',result)
        self.assertNotIn(' pm ',result.lower())

    def test_inkwash_not_confused_with_arbitrary_person(self):
        result=trade_override('S> INKWASH THOUGHT BUBBLE (2) Ayai 100k ea')
        self.assertIn('잉크 앤 워시 말풍선',result)
        self.assertIn('Ayai',result)
        self.assertIn('10만 메소',result)

    def test_no_invented_pricing(self):
        result=trade_override('S> Baby Wings/Toy Hammer')
        self.assertIn('아기 날개 / 장난감 망치',result)
        self.assertNotIn('메소',result)

    def test_no_midword_replacement(self):
        self.assertEqual(replace_market_items('CustomMadeForKorean Fantasy'), 'CustomMadeForKorean Fantasy')

    def test_weapon_attack_bonus_scroll(self):
        self.assertEqual(trade_override('S> one-handed sword wa+2 60% scr'),
                         '한손검 공격력 +2 60% 주문서 팝니다')

    def test_korean_named_item_preserved(self):
        self.assertIn('[흰색 고양이 비니]', trade_override('S> [흰색 고양이 비니] 400k'))

if __name__=='__main__':unittest.main()
