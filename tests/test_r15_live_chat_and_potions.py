"""R15: fixes grounded in the user's live chat history and quickslot (2026-10-27)."""
import unittest
from pathlib import Path

import cv2

from kain_maple_translator.chat_cleanup import (clean_spam, prepare_chat, party_post,
                                                polish_leftover, recruit_as_buy)
from kain_maple_translator.chat_slang import slang_sentence
from kain_maple_translator.hunt_capture import potion_crops
from kain_maple_translator.stack_digits import match_stack_digits

ROOT = Path(__file__).resolve().parents[1]


class SpamCleanupTests(unittest.TestCase):
    def test_spam_runs_and_crumbs_are_removed(self):
        self.assertEqual(clean_spam('J>PQ RUSH@@@@@@@@@@@@@@@@@QQ@@@c@@@@@'), 'J>PQ RUSH')
        self.assertEqual(clean_spam('B> White potions ea 270 @@@@@@@@@@@@@@@@@@@@@'),
                         'B> White potions ea 270')

    def test_crumb_after_spam_is_not_a_price(self):
        # '@@@@3m' was translated as '가격 300만 메소'.
        value = clean_spam('B>White Potion 240 ea @@@@@@@@ @@@@@@@@ @@@@@@@@3m')
        self.assertNotIn('3m', value)

    def test_real_words_after_spam_survive(self):
        value = clean_spam('Selling > Signature Hair Coupon!! offer!!@@@@@@@@@@@@@ im h ere beside.')
        self.assertIn('im h ere beside', value)

    def test_mentions_and_plain_text_are_untouched(self):
        self.assertEqual(clean_spam('@tonta'), '@tonta')
        self.assertEqual(clean_spam('see you @ henesys'), 'see you @ henesys')

    def test_keyboard_mash_digits_removed(self):
        self.assertNotIn('4444', clean_spam('R>1 RUsH 30+@@@@@44444555555666666@@@@@@@@'))


class OcrWordTests(unittest.TestCase):
    def test_common_market_misreads(self):
        self.assertIn('white potion', prepare_chat('B> PURE WATER ~600 MESO~ WHITEF OTION ~200 MESO~').lower())
        self.assertIn('iron ore', prepare_chat('B>lron ore 200 mesos ea').lower())
        self.assertIn('blue potion', prepare_chat('S>blue poion@@@@').lower())
        self.assertIn('pure water', prepare_chat('R) nure water 750 ea').lower())
        self.assertIn('blue potion', prepare_chat('B- BLUE P 210, ORANGE P 130').lower())
        self.assertTrue(prepare_chat('buy>> white potion 250!').startswith('B> '))


class PartyPostTests(unittest.TestCase):
    def check(self, text, *parts):
        result = party_post(prepare_chat(text))
        self.assertIsNotNone(result, text)
        for part in parts:
            self.assertIn(part, result, text)
        self.assertNotIn('가입을', result)

    def test_join_variants(self):
        self.check('J>PQ 30+ BONUS 1', '파티 퀘스트', '보너스', '참가', '30레벨 이상')
        self.check('j>pa!!!', '파티 퀘스트 참가')
        self.check('I>pq@@@@@@@@', '파티 퀘스트 참가')
        self.check('J> Rush', '연속 진행', '참가')
        self.check('IPO RUSH', '연속 진행', '참가')
        self.check('J>KPQ ~ any ~ LYL25', '커닝 파퀘', '25레벨')
        self.check('JPQ 31 page rush++', '31레벨', '페이지')
        self.check('J>PQ@', '파티 퀘스트 참가')

    def test_recruit_variants(self):
        self.check('R>1 SUPER RUSH 30+@@@@@@@@@', '1명 모집', '30레벨 이상')
        self.check('R>2 more for BoNUs @@@@', '보너스', '2명 모집')

    def test_non_party_lines_are_not_party_posts(self):
        self.assertIsNone(party_post('R>nure water 650 ea'))
        self.assertIsNone(party_post('j>pq Farming mushrooms for XP, add me!'))
        self.assertIsNone(party_post('jpq CaoTaMaDe my boii'))

    def test_r_with_price_is_buy(self):
        self.assertTrue(recruit_as_buy('R >Meha 8k').startswith('B> '))
        self.assertEqual(recruit_as_buy('R> Bonus'), 'R> Bonus')


class LeftoverWordTests(unittest.TestCase):
    def test_potions_and_each_prices(self):
        self.assertEqual(polish_leftover('White potions ea 270 삽니다'), '하얀 포션 개당 270 메소 삽니다')
        self.assertIn('개당 100 메소', polish_leftover('a lot of leather 100 mesos ea 삽니다'))

    def test_gear_words_only_on_trade_lines(self):
        self.assertIn('마법사 모자', polish_leftover('레벨 40 Mage hat (brown) 삽니다'))
        self.assertEqual(polish_leftover('top 10 guild'), 'top 10 guild')

    def test_linked_labels_untouched(self):
        self.assertIn('[White Potion]', polish_leftover('[White Potion] 팝니다'))


class SlangTests(unittest.TestCase):
    def test_leech_means_carry(self):
        self.assertEqual(slang_sentence('dont leech ur friends'), '친구한테 쩔 받지 마세요')
        self.assertEqual(slang_sentence('lowkey wanna quit'), '은근 접고 싶어')




class UsedPotionDisplayTests(unittest.TestCase):
    def test_used_count_shows_under_each_slot(self):
        from unittest.mock import MagicMock, patch
        from PySide6.QtWidgets import QApplication
        from kain_maple_translator.hunt_widget import HuntWindow
        app = QApplication.instance() or QApplication([])
        window = HuntWindow({})
        try:
            def slots(count):
                return {'found_keyboard': True, 'slots': [
                    {'slot': 'Ctrl', 'icon': 'potion:2000000', 'potion_id': '2000000', 'count': count}]}
            with patch('kain_maple_translator.hunt_widget.HuntCaptureThread', return_value=MagicMock()):
                window.redetect_btn.click()
                window.receive(slots(100))
                self.assertEqual(window.slot_used['Ctrl'].text(), '')  # nothing before 시작
                window.start_session()
            self.assertEqual(window.slot_used['Ctrl'].text(), '사용 0개')
            window.receive(slots(94))
            self.assertEqual(window.slot_labels['Ctrl'].text(), '94')
            self.assertEqual(window.slot_used['Ctrl'].text(), '사용 6개')
            window.receive(slots(150))  # bought more: a refill, not negative use
            self.assertEqual(window.slot_used['Ctrl'].text(), '사용 6개')
            window.receive(slots(145))
            self.assertEqual(window.slot_used['Ctrl'].text(), '사용 11개')
        finally:
            window.close(); window.deleteLater()
        self.assertIsNotNone(app)


class LiveR16TranslationTests(unittest.TestCase):
    """Mistakes seen in the 2026-10-28 live 3-minute check."""

    def test_bare_each_price_is_mesos(self):
        from kain_maple_translator.chat_patterns import explicit_trade
        value = explicit_trade('S> IRON ORE 250 EA!')
        self.assertIsNotNone(value)
        self.assertIn('개당 250', value)
        self.assertNotIn('단위 미표기', value)

    def test_leftover_words(self):
        self.assertIn('행운', polish_leftover('60% 귀고리 luck 55k 삽니다'))
        self.assertIn('맑은 물', polish_leftover('pure water 삽니다. 개당 710'))
        self.assertIn('전부', polish_leftover('327 빨간 포션 9K FOR All 팝니다'))
        self.assertEqual(polish_leftover('top 10 guild'), 'top 10 guild')

    def test_nx_is_not_mesos(self):
        self.assertEqual(polish_leftover('17,500 메소 캐시 공짜 지금 일어나기'), '17,500 캐시 나눔 지금 진행 중')

    def test_item_name_kept(self):
        from kain_maple_translator.chat_cleanup import keep_item_names
        self.assertEqual(keep_item_names('B> Dollish Pink 60K', '인형 핑크 6만 메소 삽니다'),
                         'Dollish Pink 6만 메소 삽니다')
        self.assertEqual(keep_item_names('I love my doll', '인형 핑크'), '인형 핑크')


class LiveR16SecondPassTests(unittest.TestCase):
    def test_party_rush_or_normal(self):
        self.assertEqual(party_post(prepare_chat('J>PQ rush or norm')),
                         '파티 퀘스트 연속 진행 또는 일반 진행 참가 원해요')

    def test_bare_kpq_rush_and_ocr(self):
        self.assertEqual(party_post(prepare_chat('KPToRusH@@@@@@@@@@@@@@@e@@@@@@@@@a @@@')),
                         '커닝 파퀘 연속 진행 참가 원해요')
        self.assertIsNone(party_post('PQ is fun'))

    def test_split_price_and_shorthand(self):
        self.assertIn('2.7m', prepare_chat('S> 6 ATT 2 Crit 2. 7m @ pmo'))
        self.assertIn('work gloves', prepare_chat('S> 10 att wg'))

    def test_stats_and_offers(self):
        self.assertIn('6 공격력 2 크리티컬', polish_leftover('6 att 2 crit 2.7m 팝니다'))
        self.assertEqual(polish_leftover('가격 제안 팝니다. 가격 제안 받습니다. 귓말 주세요'),
                         '가격 제안 받습니다. 귓말 주세요')

    def test_taking_offers_line(self):
        from kain_maple_translator.chat_cleanup import offer_post
        self.assertEqual(offer_post('S>Taking offers PMO'), '가격 제안 받습니다 · 귓말 주세요')
        self.assertIsNone(offer_post('S> Taking offers on my claw 2m'))

    def test_and_inside_compound_kept(self):
        self.assertIn('Ink-And-Wash', polish_leftover('Ink-And-Wash Chat and Name Plate Rings 삽니다'))
        self.assertIn('Chat · Name', polish_leftover('Ink-And-Wash Chat and Name Plate Rings 삽니다'))


class RecoveryThrottleTests(unittest.TestCase):
    def test_detector_probe_is_rarer_and_smaller(self):
        from kain_maple_translator.fast_vision import IncrementalChatOCR
        engine = IncrementalChatOCR(recognizer=object())
        self.assertEqual(engine.recovery_gate.duty, 12.0)  # R17: rarer still
        self.assertLessEqual(engine.recovery_scale_cap, 1.5)


class MeterButtonsTests(unittest.TestCase):
    def test_only_everyday_buttons_on_the_meter(self):
        from PySide6.QtWidgets import QApplication
        from kain_maple_translator.hunt_widget import HuntWindow
        app = QApplication.instance() or QApplication([])
        window = HuntWindow({})
        try:
            window._compose()
            self.assertIn('start', window._hotspots)
            self.assertIn('stop', window._hotspots)
            self.assertIn('scan', window._hotspots)
            self.assertNotIn('auto', window._hotspots)  # right-click menu
            self.assertNotIn('area', window._hotspots)
            self.assertTrue(hasattr(window, 'contextMenuEvent'))
        finally:
            window.close(); window.deleteLater()
        self.assertIsNotNone(app)


class ChatTabTests(unittest.TestCase):
    def test_megaphone_and_general_tabs(self):
        from PySide6.QtWidgets import QApplication, QLabel
        from kain_maple_translator.main import FloatingChat
        app = QApplication.instance() or QApplication([])
        chat = FloatingChat()
        try:
            self.assertIs(chat.splitter.widget(0), chat.mega_tab)
            self.assertIs(chat.splitter.widget(1), chat.general_tab)
            top = [w.accessibleName() for w in chat.mega_tab.findChildren(QLabel)]
            bottom = [w.accessibleName() for w in chat.general_tab.findChildren(QLabel)]
            self.assertIn('확성기 채팅', top)
            self.assertIn('일반 채팅', bottom)
        finally:
            chat.close(); chat.deleteLater()
        self.assertIsNotNone(app)


class ClassicPiecesTests(unittest.TestCase):
    def test_pieces_load_from_a_korean_folder(self):
        # The exe lives in '글클메 애드온'; cv2.imread fails on such paths.
        import shutil, tempfile
        from kain_maple_translator import classic_ui as CU
        src = ROOT / 'resources' / 'classic_ui'
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / '글클메 애드온' / 'resources' / 'classic_ui'
            shutil.copytree(src, dst)
            old = CU._root
            CU._root = lambda: dst
            CU.piece.cache_clear()
            try:
                for name in ('frame', 'chat_tab', 'pill_pink_clean', 'btn_lime', 'btn_close', 'cell'):
                    self.assertEqual(CU.piece(name).shape[2], 4, name)
            finally:
                CU._root = old
                CU.piece.cache_clear()


class LiveKeyboardFixtureTests(unittest.TestCase):
    def test_live_counts_on_every_key(self):
        from kain_maple_translator.image_io import read_image
        from kain_maple_translator.hunt_capture import locate_keyboard
        image = read_image(ROOT / 'tests/fixtures/r15/live-keyboard-1080p.png')
        box = locate_keyboard(image)
        self.assertIsNotNone(box)
        want = {'1': 9, '2': 15, 'Shift': 28, 'Ctrl': 100, 'Del': 1, 'PgDn': 34}
        for dy in (-2, 0, 2):
            x, y, w, h = box
            crops = potion_crops(image, (x, y + dy, w, h), all_slots=True)
            got = {k: (match_stack_digits(c) or [None])[0] for k, c in crops.items()}
            for name, value in want.items():
                self.assertEqual(got[name], value, (name, dy))
            for name in set(got) - set(want):
                self.assertIsNone(got[name], name)
        self.assertEqual(list(potion_crops(image, box)), ['Ctrl', 'Del', 'End', 'PgDn'])


if __name__ == '__main__':
    unittest.main()
