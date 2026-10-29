"""Translation assertions from 2026-10-27 17-40-36.mp4 source pixels.

The reference retains timestamps and names. Unknown English item titles are
kept: successful deterministic parsing is not a claim of complete localization.
No generated phrase corpus or altered-price simulations are used here.
"""
import json
from pathlib import Path
import unittest

from kain_maple_translator.translation import Translator
from kain_maple_translator.trade_stats import alternative_stat_offers

REFERENCE=json.loads((Path(__file__).parent/'fixtures/r14/translation-reference.json').read_text())


class VideoTranslationTests(unittest.TestCase):
    def setUp(self):
        self.tr=Translator(body_only=True)

    def source(self,nick):
        return next(row['body'] for row in REFERENCE if row['nickname']==nick)

    def translated(self,nick):
        text=self.tr.translate_fast(self.source(nick))
        self.assertIsNotNone(text,nick)
        return text

    def test_1s_magic_options_preserve_separate_price_pairs(self):
        self.assertEqual(self.translated('yumigo'),
            # R19: Classic World's official Korean name (resources/item-info)
            '블루 아르텐 삽니다. 마력 +8: 30만 메소 / 마력 +12: 60만 메소')

    def test_9s_attack_options_preserve_level_and_both_prices(self):
        self.assertEqual(self.translated('Ylina'),
            '40레벨 스틸 보닌 삽니다. 공격력 +7: 40만 메소 / 공격력 +8: 55만 메소')

    def test_option_parser_does_not_claim_other_video_sentences(self):
        for row in REFERENCE:
            if row['nickname'] in ('yumigo','Ylina'):
                continue
            with self.subTest(body=row['body']):
                self.assertIsNone(alternative_stat_offers(row['body']))

    def test_5s_join_kpq_without_arrow(self):
        self.assertEqual(self.translated('AzZerak'),'커닝 파퀘 참가 원해요')

    def test_15s_channel_range_not_negative_number(self):
        self.assertEqual(self.translated('Yawaradi'),'3~12채널이야')

    def test_34s_cc_question_is_not_change_channel_command(self):
        row=next(r for r in REFERENCE if r['second']==34 and r['nickname']=='AzZerak')
        self.assertEqual(self.tr.translate_fast(row['body']),
            '3~12채널에서만 파티 퀘스트 할 수 있어요?')

    def test_36s_yes_shorthand(self):
        row=next(r for r in REFERENCE if r['second']==36)
        self.assertEqual(self.tr.translate_fast(row['body']),'응 응')

    def test_42s_acknowledgement(self):
        row=next(r for r in REFERENCE if r['second']==42)
        self.assertEqual(self.tr.translate_fast(row['body']),'아')

    def test_28s_class_gear_list_with_contact(self):
        result=self.translated('ONEGOAL')
        for required in ('40레벨','어쌔신','상의','하의','삽니다','귓말 주세요'):
            self.assertIn(required,result)

    def test_31s_pet_scroll_keeps_rate_and_parenthesized_number(self):
        self.assertEqual(self.translated('Yakise'),'펫 장비 이동속도 60% 주문서 (1) 팝니다')

    def test_34s_actual_typo_scrools_and_decoration(self):
        result=self.translated('DarkMen')
        # R15: '@@@' spam is removed before translation instead of copied.
        self.assertEqual(result,'60% 주문서 팝니다')

    def test_46s_comma_before_pm_does_not_hide_price(self):
        self.assertEqual(self.translated('vayoz'),'천사 헤일로 삽니다. 가격 22만 메소. 귓말 주세요')

    def test_52s_plural_kumbi_count_and_unqualified_price(self):
        result=self.translated('HolyRatty')
        for required in ('금비 표창','10개','33만 메소','개당 여부 미표기'):
            self.assertIn(required,result)

    def test_57s_pmo_after_market_room_does_not_block_location(self):
        result=self.translated('Corrupy')
        for required in ('두손검 공격력 60% 주문서','33채널 자유시장 19번 방','귓말 주세요'):
            self.assertIn(required,result)

    def test_0s_celebration_does_not_drop_second_request(self):
        result=self.translated('DUSTIN')
        for required in ('[동료의 마법 상자]','MADY','31레벨','길드장','MOLLY 사주세요'):
            self.assertIn(required,result)

    def test_59s_award_retains_unknown_link_and_player(self):
        result=self.translated(None)
        for required in ('Cheeta','[사르르 초코퐁듀 스틱]','Aurora Mystery Fashion Crate','획득'):
            self.assertIn(required,result)

    def test_63s_repeated_buy_markers_keep_both_items(self):
        self.assertEqual(self.translated('Cloud9'),'잡캐시템 삽니다 · 천사 헤일로 삽니다')

    def test_0s_wishlist_keeps_unknown_names(self):
        self.assertEqual(self.translated('APPEALING'),'Jangpalsamo 또는 Guryongdo 삽니다')

    def test_40s_uncertain_trade_ratio_is_not_invented(self):
        self.assertIn('700k/2 Halos',self.translated('Biot'))
