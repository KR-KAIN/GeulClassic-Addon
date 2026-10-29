"""Researched chat slang / Maple abbreviations (chat_slang.py)."""
import unittest
from kain_maple_translator.chat_slang import (peel_markers, join_markers, slang_sentence,
                                              expand_slang, koreanize_names)


class PeelMarkers(unittest.TestCase):
    def test_front_and_back_markers(self):
        self.assertEqual(peel_markers('ngl this map is so op lol'),
                         (['솔직히'], 'this map is so op', ['ㅋㅋ']))
        self.assertEqual(peel_markers('smh got ksed again'), ([], 'got ksed again', ['에휴']))
        self.assertEqual(peel_markers('fr fr this game is goated'), (['진짜'], 'this game is goated', []))

    def test_nothing_to_peel_or_no_core(self):
        self.assertIsNone(peel_markers('need a bishop for zak run'))
        self.assertIsNone(peel_markers('lol'))
        self.assertIsNone(peel_markers('omg'))

    def test_trade_lines_untouched(self):
        self.assertIsNone(peel_markers('S> ws 5m lol'))
        self.assertIsNone(peel_markers('lol [Work Gloves] 100k'))

    def test_join(self):
        self.assertEqual(join_markers(['솔직히'], '이 맵 좋아.', ['ㅋㅋ']), '솔직히 이 맵 좋아 ㅋㅋ')


class SlangSentence(unittest.TestCase):
    def test_game_situations(self):
        self.assertEqual(slang_sentence("i got dc'd"), '튕겼어')
        self.assertEqual(slang_sentence('got ksed again'), '또 스틸당했어')
        self.assertEqual(slang_sentence('stop ksing pls'), '스틸하지 마세요')
        self.assertEqual(slang_sentence('can someone hb me pls'), '누가 하이퍼 바디 좀 주세요')
        self.assertEqual(slang_sentence('gonna afk for a bit'), '잠깐 잠수할게')
        self.assertEqual(slang_sentence('where do i get my 2nd job'), '2차 전직 어디서 해요?')
        self.assertEqual(slang_sentence('thx 4 the help'), '도와줘서 고마워요')

    def test_no_guess(self):
        self.assertIsNone(slang_sentence('hello there'))
        self.assertIsNone(slang_sentence('S> hb skill book 2m'))


class ExpandSlang(unittest.TestCase):
    def test_chat_shorthand(self):
        self.assertEqual(expand_slang('tmrw ill do kpq w u'), 'tomorrow I will do kpq with you')
        self.assertEqual(expand_slang('ppl r so nice here'), 'ppl are so nice here')
        self.assertEqual(expand_slang('hmu if u need a cleric'), 'contact me if you need a cleric')

    def test_game_terms(self):
        self.assertEqual(expand_slang('need a bishop for zak run'), 'need a bishop for Zakum run')
        self.assertEqual(expand_slang('imo sin is better than dit'), 'imo Assassin is better than Bandit')
        self.assertEqual(expand_slang('is hene better for exp'), 'is Henesys better for EXP')
        self.assertEqual(expand_slang('wanna duo at gs'), 'I kind of want to duo at Ghost Ship')
        self.assertEqual(expand_slang('is cs worth it on wg'), 'is Chaos Scroll worth it on wg')
        self.assertEqual(expand_slang('buy it in cs'), 'buy it in Cash Shop')

    def test_protected_values(self):
        self.assertEqual(expand_slang('S> ws 5m'), 'S> ws 5m')
        self.assertEqual(expand_slang('anyone got [Sin Claw] u know'), 'anyone got [Sin Claw] you know')
        self.assertEqual(expand_slang('im so sleepy'), 'I am so sleepy')


class KoreanizeNames(unittest.TestCase):
    def test_names_and_particles(self):
        self.assertEqual(koreanize_names('Zakum 런을 위한 비숍이 필요합니다.'), '자쿰 런을 위한 비숍이 필요합니다.')
        self.assertEqual(koreanize_names('Chaos Scroll은 좋아요'), '혼돈의 주문서는 좋아요')
        self.assertEqual(koreanize_names('Henesys Party 퀘스트'), '헤네 파퀘')

    def test_skip_english_only_and_links(self):
        self.assertEqual(koreanize_names('Zakum run'), 'Zakum run')
        self.assertEqual(koreanize_names('[Zakum Helmet] 팝니다'), '[Zakum Helmet] 팝니다')


if __name__ == '__main__':
    unittest.main()
