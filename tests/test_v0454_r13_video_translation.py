"""Real lines and OCR variants from 2026-10-27 16-30-42.mp4.

Time references are approximate first visible seconds in the 88.2s recording.
No synthetic phrase corpus is used for the before/after translation results.
"""
import unittest
from kain_maple_translator.translation import Translator


class VideoTranslationTests(unittest.TestCase):
    def setUp(self):
        # The live app caches AI item-name drafts in the user profile
        # ('golden mole' -> '골든 몰'); keep results independent of that file.
        from unittest.mock import patch
        from kain_maple_translator import classic_item_index
        stub=patch.object(classic_item_index,'replace_unverified_item_names',
                          lambda text,translate_fn,max_new=2:text)
        stub.start();self.addCleanup(stub.stop)
        self.tr=Translator(body_only=True)
    def fast(self,text):
        result=self.tr.translate_fast(text)
        self.assertIsNotNone(result,text)
        return result

    def test_12s_party_face_avoids_generic_model(self):
        self.assertEqual(self.fast('J>PQ RUSH ^_^'),'파티 퀘스트 연속 진행 참가 원해요 ^_^')

    def test_video_ocr_clipped_face_does_not_require_model(self):
        for source in ('J>PQ RUSH ^_','J>PQ RUSH ^','J>PQ RUSH^_^','J>PQ RUSH **'):
            self.assertIn('파티 퀘스트 연속 진행 참가 원해요',self.fast(source))

    def test_25s_thanks_heart(self):
        self.assertEqual(self.fast('ty <3'),'고마워 <3')

    def test_32s_link_and_heart(self):
        self.assertEqual(self.fast('[Angel Halo] <3'),'[천사 헤일로] <3')

    def test_0s_tobis(self):
        self.assertIn('토비 표창',self.fast('S>tobis pmo'))

    def test_0s_over_price_not_slippery(self):
        self.assertEqual(self.fast('over 5k is crazy'),'5k 넘는 건 너무하네')

    def test_observed_video_ocr_joined_is_crazy(self):
        self.assertEqual(self.fast('over 5k iscrazy'),'5k 넘는 건 너무하네')

    def test_observed_video_ocr_joined_heart(self):
        self.assertEqual(self.fast('ty<3'),'고마워 <3')

    def test_observed_video_ocr_comma_on_each(self):
        self.assertIn('개당 4만 5천 메소',self.fast('S> founders (11) 300k| 5 slots 45k ea,'))

    def test_44s_currency_not_duplicated(self):
        self.assertEqual(self.fast('looking for 100k meso'),'10만 메소 구하고 있어요')

    def test_2s_and_81s_changed_price(self):
        for value,want in [('50k','5만 메소'),('45k','4만 5천 메소')]:
            result=self.fast('[Mystery Face Coupon] '+value)
            self.assertIn('[Mystery Face Coupon]',result)
            self.assertIn(want,result)
            self.assertNotIn('팝니다',result)
            self.assertNotIn('삽니다',result)

    def test_5s_slot_listing_keeps_all_numbers(self):
        result=self.fast('S> founders (11) 300k | 5 slots 45k ea.')
        for expected in ('founders (11)','30만 메소','5 슬롯','개당 4만 5천 메소','팝니다'):
            self.assertIn(expected,result)

    def test_15s_buy_marker_and_cri(self):
        result=self.fast('B >> WORK GLOVES ATT +6 CRI +2 BUY / OFFER ME')
        for expected in ('노가다 목장갑','공격력 +6','크리티컬 +2','삽니다','가격 제안'):
            self.assertIn(expected,result)
        self.assertNotIn('%',result)
        self.assertNotIn('>',result)

    def test_32s_level_and_two_handed_blunt(self):
        result=self.fast('[Angel Halo] B>Golden Mole Lvl 50 Blunt 2H pmo')
        for expected in ('[천사 헤일로]','골든 모울','레벨 50','양손둔기','삽니다'):
            self.assertIn(expected,result)

    def test_36s_fame_channel_room_patience(self):
        result=self.fast('[Snail] B> FAME 3k EA ch 33 FMroom 15 plese be patient when trading')
        for expected in ('[Snail]','인기도','개당 3천 메소','33채널','15번 방','기다려'):
            self.assertIn(expected,result)

    def test_48s_mixed_buy_sell_offer(self):
        result=self.fast('B>Dollish Pink. S>Panlid -2 50k only. - Pm me w offer')
        # R17: the user glossary names Panlid '냄비 뚜껑'; the '-2' must stay
        for expected in ('Dollish Pink. 삽니다','냄비 뚜껑 -2','팝니다','5만 메소','가격 제안'):
            self.assertIn(expected,result)

    def test_49s_addressed_nickname_kept(self):
        self.assertEqual(self.fast('naw ch3n'),'아니야, ch3n')

    def test_55s_u_shorthand(self):
        self.assertEqual(self.fast('u scammed me'),'너 나한테 사기 쳤잖아')
        self.assertEqual(self.fast('u funny my guy'),'너 웃긴다, 친구야')

    def test_58s_decimal_price_source_and_observed_ocr_variants(self):
        for price in ('6.75m','6,75m','6. 75m'):
            result=self.fast('S> 8 ATK WG 1 Crit A/w '+price)
            self.assertIn('675만 메소',result)
            self.assertNotIn('7500만',result)
            self.assertIn('8 공격력',result)
            self.assertIn('1 크리티컬',result)

    def test_61s_cd_has_no_invented_percent(self):
        result=self.fast('S>Emerald Earrings 8 LUK 2 CD, C/O 600k')
        for expected in ('8 행운','2 크리티컬 데미지','60만 메소'):
            self.assertIn(expected,result)
        self.assertNotIn('%',result)

    def test_80s_hangul_link_matt_offers(self):
        result=self.fast('[크로미] S>101 MATT Taking Offers ~')
        self.assertIn('[크로미]',result)
        self.assertIn('101 마력',result)
        self.assertIn('가격 제안',result)
