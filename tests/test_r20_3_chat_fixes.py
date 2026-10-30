"""R20.3: the KO > EN composer's nonsense ("What's New" for '여기는 내자리야')
and the pet potion status line that became a chat message (2026-10-30)."""
import os
import unittest
from collections import namedtuple

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from kain_maple_translator.core import merge_chat_ocr, parse_chat_line
from kain_maple_translator.natural_chat import chatify_english, faithful_english, korean_chat_phrase
from kain_maple_translator.system_lines import system_line

PET = 'Your pet is running low on the allotted HP potions.'
Line = namedtuple('Line', 'text rect confidence')


class KoreanToMapleEnglish(unittest.TestCase):
    def test_the_lines_from_the_report(self):
        for ko, en in {'여기는 내자리야': 'this is my spot',
                       '여기는 내 사냥터야': 'this is my spot',
                       '같이 사냥할래?': 'wanna train together?',
                       '이 맵 자리 있어요?': 'any free spot here?',
                       '잠깐 쉬었다 올게': 'brb',
                       '누가 내 몹 뺏어감': 'pls stop ksing',
                       '여기 주인 있어요': 'this spot is taken',
                       '같이 해요': 'wanna go together?',
                       '자리 비켜줘': 'pls find another spot',
                       '채널 옮겨주세요': 'cc pls'}.items():
            with self.subTest(ko=ko):
                self.assertEqual(korean_chat_phrase(ko), en)

    def test_maple_abbreviations(self):
        for ko, en in {'모르겠어요': 'idk', '어서오세요': 'wb', '화이팅': 'gl', '잘자요': 'gn',
                       '나중에 봐요': 'cya', '농담이에요': 'jk', '지금 갈게요': 'omw', '버프 주세요': 'buff pls',
                       '포션 다 떨어졌어요': 'out of pots', '오늘 레벨 30 찍었어요': 'hit lvl 30!',
                       '보스 언제 나와요?': 'when does the boss spawn?', '렙업!': 'lvl up!'}.items():
            with self.subTest(ko=ko):
                self.assertEqual(korean_chat_phrase(ko), en)

    def test_questions_the_model_got_wrong(self):
        self.assertEqual(korean_chat_phrase('오늘 저녁에 같이 파티 퀘스트 하실 분 있나요'), 'anyone wanna PQ?')
        self.assertEqual(korean_chat_phrase('이 아이템 얼마에 팔면 될까요'), 'how much should i sell this for?')

    def test_long_sentences_are_left_to_the_model(self):
        self.assertIsNone(korean_chat_phrase('헤네시스로 가는 길을 모르겠어요'))

    def test_model_english_in_chat_short_forms(self):
        self.assertEqual(chatify_english('Thank you, please wait. I will be right back.'), 'ty, pls wait. I will brb.')
        self.assertEqual(chatify_english("I don't know how to get to Henesys"), 'idk how to get to Henesys')
        self.assertEqual(chatify_english('Can I get a party quest today?'), 'Can I get a PQ today?')

    def test_round_trip_catches_unrelated_english(self):
        back = {"What's New": '새로운 소식', 'Here is my place.': '여기는 내 자리입니다'}.get
        self.assertFalse(faithful_english('여기는 내자리야', "What's New", back))
        self.assertTrue(faithful_english('여기는 내 자리입니다', 'Here is my place.', back))
        self.assertTrue(faithful_english('네', 'yes', back))      # too short to judge


class PetStatusLine(unittest.TestCase):
    def test_known_line_in_korean(self):
        self.assertEqual(system_line(PET), '펫에게 지급한 HP 물약이 얼마 남지 않았습니다.')
        self.assertEqual(system_line('You : pet is running low on the allotted MP potions.'),
                         '펫에게 지급한 MP 물약이 얼마 남지 않았습니다.')
        self.assertIsNone(system_line('LewdGirl : my pet is cute'))

    def test_not_a_player_called_you(self):
        # the row splitter cut 'Your' at the gap before 'r'
        self.assertIsNone(parse_chat_line('You : pet is running low on the allotted HP potions.'))
        self.assertEqual(parse_chat_line('LewdGirl : My Huntington'), ('LewdGirl', 'My Huntington'))

    def test_not_glued_to_the_message_above(self):
        rows = merge_chat_ocr([Line('LewdGirl : My Huntington', (10, 100, 200, 14), .95),
                               Line(PET, (10, 116, 330, 14), .93)])
        self.assertEqual([(r['nickname'], r['body']) for r in rows],
                         [('LewdGirl', 'My Huntington'), ('시스템', PET)])

    def test_translated_in_the_games_words(self):
        from kain_maple_translator.translation import Translator
        self.assertEqual(Translator('argos').translate(PET, 'en-ko'), '펫에게 지급한 HP 물약이 얼마 남지 않았습니다.')


class ComposerStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        from kain_maple_translator.main import CompactComposer
        self.panel = CompactComposer()
        self.clip = QApplication.clipboard()
        self.clip.setText('before')

    def test_sure_english_is_copied(self):
        self.panel.finish('this is my spot', '')
        self.assertEqual(self.clip.text(), 'this is my spot')
        self.assertEqual(self.panel.status.text(), '복사됨')

    def test_unsure_english_is_shown_not_copied(self):
        self.panel.finish("What's New", '', sure=False)
        self.assertEqual(self.panel.result.text(), "What's New")
        self.assertEqual(self.clip.text(), 'before')
        self.assertEqual(self.panel.status.text(), '확인 필요')

    def test_untranslated_korean_never_goes_to_the_game(self):
        self.panel.finish('자리 비켜줘', '')
        self.assertEqual(self.panel.result.text(), '')
        self.assertEqual(self.clip.text(), 'before')
        self.assertEqual(self.panel.status.text(), '다르게 입력')


if __name__ == '__main__':
    unittest.main()
