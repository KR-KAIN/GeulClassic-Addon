"""R17: user glossary (2026-10-28), meowdb Korean item names, glued trade posts."""
import unittest
from unittest.mock import patch

from kain_maple_translator.chat_cleanup import split_glued, price_pairs, party_post
from kain_maple_translator.user_glossary import glossary_sentence, glossary_leftover
from kain_maple_translator.classic_item_index import meowdb_pairs, current_index
from kain_maple_translator.translation import Translator


class GlossarySentence(unittest.TestCase):
    def test_chat_lines_from_glossary(self):
        cases = {
            'GG, TYFP. GTG': '수고했어요, 파티 고마웠어요. 이제 가야 해요',
            'CC pls, no KS': '채널 변경 부탁해요, 스틸 금지',
            'BRB, repot': '금방 올게요, 물약 보충',
            "Sry, I dc'd. OMW": '미안해요, 튕겼어요. 가는 중이에요',
            'Pass lead pls': '파티장 넘겨 주세요',
            'Haste pls, ty': '헤이스트 부탁해요, 고마워요',
            'FCFS mesos only, no lowball': '선착순 메소로만 거래, 후려치기 사절',
            'ty 4 the carry, gg': '캐리 고마워요, 수고했어요',
            'AFK 10 min': '10분 동안 자리 비울게요',
            'LF sin for EEC': '이블아이의 굴 갈 어쌔신 구해요',
        }
        for source, expected in cases.items():
            self.assertEqual(glossary_sentence(source), expected, source)

    def test_normal_sentences_and_trades_are_left_alone(self):
        for source in ('where are you going', 'S> kfan PMO', 'B> GFA 60% 500k', 'i love this game'):
            self.assertIsNone(glossary_sentence(source), source)

    def test_leftover_only_unambiguous_and_present_in_source(self):
        self.assertIn('헤네시스 사냥터', glossary_leftover('anyone going HHG?', '누구든지 HHG를 갈까?'))
        # CB has several meanings: never guessed - shown with all of them (R19)
        out = glossary_leftover('need CB', 'CB 필요')
        self.assertIn('CB(', out)
        self.assertIn('콜드 빔', out)
        self.assertIn('크로스보우 부스터', out)
        # a number like '123' is a KPQ platform combo, never swapped
        self.assertEqual(glossary_leftover('Player123', 'Player123'), 'Player123')
        # linked labels stay as typed
        self.assertEqual(glossary_leftover('[kfan] 100k', '[kfan] 10만 메소'), '[kfan] 10만 메소')


class GluedPosts(unittest.TestCase):
    def test_split(self):
        self.assertEqual(split_glued('B> 60%Scrolls Claw140k Dagger135k'), 'B> 60% Scrolls Claw 140k Dagger 135k')
        self.assertEqual(split_glued('B>IronOre200 Bronze50'), 'B>Iron Ore 200 Bronze 50')
        self.assertEqual(split_glued('B>3more whige label rings 450keach'), 'B>3 more whige label rings 450k each')
        self.assertIn('FM CH 37', split_glued('S>Coffin PM or FMchn37'))

    def test_split_keeps_stats_nicknames_links_and_mesos(self):
        self.assertEqual(split_glued('B Blue Arten +8magicatk for 300k'), 'B Blue Arten +8magicatk for 300k')
        self.assertTrue(split_glued('Player123 : S> 60% 2m').startswith('Player123 : '))
        self.assertIn('[IronOre200]', split_glued('S> [IronOre200] 50k'))
        self.assertIn('56meso', split_glued('S> cursed dolls 56meso ea'))

    def test_price_list_keeps_each_price(self):
        out = price_pairs('B> 60% Scrolls Claw 140k Dagger 135k Wand 115k Polearm 60k Bow 70k')
        self.assertEqual(out, '60% 주문서: 아대 14만 메소, 단검 13만 5천 메소, 완드 11만 5천 메소, '
                              '폴암 6만 메소, 활 7만 메소 삽니다')


class PartyPosts(unittest.TestCase):
    def test_lfm_forms(self):
        self.assertEqual(party_post('R> KPQ LF1M'), '커닝 파퀘 1명 구해요')
        self.assertEqual(party_post('LFM KPQ 3/4'), '커닝 파퀘 구해요 (현재 3/4)')
        self.assertEqual(party_post('need 3 more for KPQ, 2/4'), '커닝 파퀘 3명 구해요 (현재 2/4)')
        self.assertEqual(party_post('LF KPQ rush'), '커닝 파퀘 연속 진행 참가 원해요')


class MeowdbNames(unittest.TestCase):
    def test_bundled_names_loaded(self):
        pairs = dict(meowdb_pairs())
        self.assertGreater(len(pairs), 200)
        self.assertEqual(pairs.get('Pure Water'), '맑은 물')
        self.assertEqual(current_index().replace_verified('Pure Water'), '맑은 물')

    def test_names_joined_through_gms_and_kms_ids(self):
        pairs = dict(meowdb_pairs())
        self.assertGreater(len(pairs), 3000)
        self.assertEqual(pairs.get('Red Bean Sundae'), '팥빙수')
        self.assertEqual(pairs.get('Zakum Helmet'), '자쿰의 투구')
        # meowdb's icon number pointed this potion at '통증 완화제': never used
        self.assertNotEqual(pairs.get('Supreme Sniper Potion'), '통증 완화제')


class EndToEnd(unittest.TestCase):
    def test_trade_lines_without_model(self):
        tr = Translator()
        with patch('kain_maple_translator.translation.translate_generic_many',
                   side_effect=AssertionError('AI called')):
            self.assertEqual(tr.translate_fast('B>ALL JUNK NX 10K'), '잡캐시템 전부 삽니다. 가격 1만 메소')
            self.assertIn('2개 삽니다', tr.translate_fast('B> GFA 60% 500k ea need 2'))
            self.assertIn('시작가 30만 메소', tr.translate_fast('S> clean WG s/b 300k c/o 400k a/w 600k'))
            self.assertIn('냄비 뚜껑', tr.translate_fast('S> panlid 100k obo'))


if __name__ == '__main__':
    unittest.main()


class ExpGainSinceStart(unittest.TestCase):
    def test_gain_and_percent_since_start(self):
        from kain_maple_translator.hunt_stats import HuntSession
        s = HuntSession()
        s.start()
        s.observe_exp(30, 10000, 40.0)      # baseline at 시작
        s.observe_exp(30, 10500, 42.0)
        self.assertEqual(s.gained_exp, 500)
        self.assertAlmostEqual(s.gained_percent, 2.0)
        self.assertEqual(s.start_exp, 10000)


class ChatSkin(unittest.TestCase):
    def test_skin_pixmap_sizes(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from kain_maple_translator import classic_ui as CU
        pm = CU.chat_window_pixmap(515, 700, [300], [(55, 290, 0, 100, 10), (360, 648, 100, 100, 10)])
        self.assertEqual((pm.width(), pm.height()), (515, 700))
        small = CU.chat_window_pixmap(200, 150)
        self.assertEqual((small.width(), small.height()), (200, 150))


class ChatScrollbarMouse(unittest.TestCase):
    def test_buttons_and_thumb_move_the_feed(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        app = QApplication.instance() or QApplication([])
        from kain_maple_translator.main import FloatingChat
        w = FloatingChat()
        w.apply_style({}, 98)
        w.set_mode('dock-right')
        w.resize(515, 640)
        w.show()
        for i in range(60):
            w.put({'nickname': f'n{i}', 'translated': f'메시지 {i} ' * 6, 'kind': 'normal',
                   'message_id': i + 1, 'persist': False})
        for _ in range(5):
            app.processEvents()
        w._scroll_to_latest()
        app.processEvents()
        bar = w.general_feed.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        start = bar.value()
        part = [p for p in w._scroll_parts() if p['feed'] is w.general_feed][0]
        QTest.mouseClick(w.card, Qt.MouseButton.LeftButton, pos=part['up'].center())
        self.assertLess(bar.value(), start)
        self.assertFalse(w._auto_follow[w.general_feed])
        after_up = bar.value()
        QTest.mouseClick(w.card, Qt.MouseButton.LeftButton, pos=part['down'].center())
        self.assertGreater(bar.value(), after_up)
        # drag the thumb to the top
        part = [p for p in w._scroll_parts() if p['feed'] is w.general_feed][0]
        thumb = part['thumb'].center()
        QTest.mousePress(w.card, Qt.MouseButton.LeftButton, pos=thumb)
        QTest.mouseMove(w.card, QPoint(thumb.x(), thumb.y() - 2000))
        QTest.mouseRelease(w.card, Qt.MouseButton.LeftButton, pos=QPoint(thumb.x(), 0))
        self.assertEqual(bar.value(), 0)
        w.close()


class R17LiveFixes(unittest.TestCase):
    def test_lines_from_live_chat(self):
        tr = Translator()
        with patch('kain_maple_translator.translation.translate_generic_many',
                   side_effect=AssertionError('AI called')):
            self.assertEqual(tr.translate_fast('L> KPQ LV 27 SIN ②@@@C@②②@@@②@@@@'),
                             '커닝 파퀘 참가 원해요 (27레벨, 어쌔신)')
            self.assertEqual(tr.translate_fast('B> BLUE POTS @ 150 EA @@@@@@@@@@'), '파란 포션 삽니다. 개당 150')


class FastChatR17(unittest.TestCase):
    @staticmethod
    def _frame(lines, top=13, pitch=22, seed=0):
        import numpy as np, cv2
        rng = np.random.default_rng(seed)
        img = (rng.integers(30, 44, (90, 600, 3))).astype(np.uint8)  # moving scenery
        for i, text in enumerate(lines):
            cv2.putText(img, text, (6, top+i*pitch+6), cv2.FONT_HERSHEY_SIMPLEX, .5, (238, 238, 238), 1, cv2.LINE_AA)
        return img

    def test_scrolled_lines_reuse_their_reads(self):
        from kain_maple_translator import fast_vision as FV
        texts = ['Alice : S> Work Gloves 10m', 'Bob : J>PQ RUSH please', 'Cara : B> Pure Water 700 ea',
                 'Dan : anyone selling ilbis']
        eng = FV.IncrementalChatOCR(recognizer=object(), clock=lambda: 0.)
        first, _ = FV.ink_rows(self._frame(texts, seed=1))
        self.assertEqual(len(first), 4)
        for row, text in zip(first, texts):
            eng.cache[row.key] = (text, .95, 0.)
        eng._prev_rows = [(r.rect[1]+r.rect[3]/2, r.key, FV.shift_prep(r.neutral)) for r in first]
        second, _ = FV.ink_rows(self._frame(texts[1:]+['Eve : brand new line here'], seed=2))
        missing = {r.key: r for r in second}
        values = {}
        reused = eng._scroll_reuse(second, missing, values)
        got = [values[k][0] for k in reused]
        self.assertGreaterEqual(len(got), 2)
        for text in got:
            self.assertIn(text, texts[1:])           # never another line's text
        self.assertNotIn('Eve : brand new line here', got)

    def test_spam_rows_skip_extra_reads(self):
        from kain_maple_translator.fast_vision import spam_dominated
        self.assertTrue(spam_dominated('YukiYuki : J>PQ RUSH @@@@@@@@@@@@@@@@@@@@@@'))
        self.assertFalse(spam_dominated('Poorkid : B>Unagi & Pure water S> Wolbies @@'))

    def test_item_link_brackets(self):
        from kain_maple_translator.chat_cleanup import prepare_chat
        self.assertEqual(prepare_chat('[Angel Halol S> 1m'), '[Angel Halo] S> 1m')
        self.assertEqual(prepare_chat('[DIC 号】 S> 10atk 2cri'), '[DIC] S> 10atk 2cri')
        self.assertEqual(prepare_chat('hello [world'), 'hello [world')   # unknown name: untouched

    def test_megaphone_text_stays_readable(self):
        from kain_maple_translator.main import readable_on
        self.assertEqual(readable_on('#ffffb1', '#e6b505'), '#000000')   # pale on yellow
        self.assertEqual(readable_on('#120008', '#e6b505'), '#120008')   # already readable
