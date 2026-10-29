import unittest
from pathlib import Path
from kain_maple_translator.colloquial import conversational_shortcut, polite_long_message
from kain_maple_translator.translation import Translator
from kain_maple_translator.chat_style import DEFAULT_STYLE, normalize_style, text_css

ROOT=Path(__file__).resolve().parents[1]

class NaturalChatAndDisplayTests(unittest.TestCase):
    def test_single_word_casual(self):
        for source, result in [('hi','안녕'),('hey','안녕'),('ty','고마워'),('thanks','고마워'),('np','괜찮아'),('gg','수고했어'),('gz','축하해'),('brb','금방 올게'),('ok','알겠어'),('idk','모르겠어'),('bye','잘 가')]:
            with self.subTest(source=source):
                self.assertEqual(Translator().translate(source,'en-ko'),result)

    def test_greeting_exceptions_and_long_messages(self):
        self.assertEqual(Translator().translate('hello','en-ko'),'안녕하세요')
        self.assertEqual(Translator().translate('HOLLO!!','en-ko'),'안녕하세요')
        self.assertEqual(Translator().translate('hello everyone','en-ko'),'다들 안녕하세요')
        self.assertEqual(Translator().translate('hi guys','en-ko'),'다들 안녕하세요')
        self.assertEqual(Translator().translate('can someone help me','en-ko'),'누가 좀 도와주실 수 있나요?')
        self.assertEqual(polite_long_message('I really need that','그거 필요해'), '그거 필요해요')
        self.assertEqual(polite_long_message('That is completely fine','그냥 괜찮아.'), '그냥 괜찮아요.')

    def test_known_multi_item_slash_mapping(self):
        self.assertEqual(Translator().translate('S> Mokbi/Wooden Tops 700k ea','en-ko'), '목비 / 나무팽이 표창 팝니다. 개당 70만 메소')

    def test_trade_not_confused_for_smalltalk(self):
        self.assertIsNone(conversational_shortcut('B> hi 10k'))
        self.assertIsNone(conversational_shortcut('S> hello world 3m'))
        self.assertEqual(polite_long_message('S> hello world 3m','메소가 없어'), '메소가 없어')
        self.assertEqual(Translator().translate('B> GFA 60%', 'en-ko'), '장공 60% 주문서 삽니다')

    def test_megaphone_colors_are_separate(self):
        s=normalize_style({'nickname_color':'#111111','message_color':'#222222', 'megaphone_nickname_color':'#abcdef','megaphone_message_color':'#123456'})
        self.assertIn('#abcdef',text_css(s,'megaphone_nickname'))
        self.assertIn('#123456',text_css(s,'megaphone_message'))
        self.assertIn('#111111',text_css(s,'nickname'))
        self.assertIn('#222222',text_css(s,'message'))
        main=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        obs=(ROOT/'kain_maple_translator/obs_source.py').read_text(encoding='utf-8')
        self.assertIn("('megaphone_nickname_color','확성기 닉네임 색')",main)
        self.assertIn('style.megaphone_nickname_color',obs)
        self.assertIn('style.megaphone_message_color',obs)

    def test_bottom_cut_improvements(self):
        main=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('rows.setContentsMargins(0,0,0,7)',main)
        self.assertIn('feed.widget().adjustSize()',main)
        self.assertIn('QTimer.singleShot(65,self._scroll_to_latest)',main)

if __name__ == '__main__': unittest.main()
