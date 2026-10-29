"""Regressions found in the user's 2026-10-27 11-50-15 recording."""
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from kain_maple_translator.translation import Translator
from kain_maple_translator.chat_patterns import mixed_trade_parts,party_intent,attention_tail
from kain_maple_translator.core import merge_chat_ocr
from kain_maple_translator.vision import Line
from kain_maple_translator.fast_vision import ink_rows_border_retry,supplement_white_rows,_stable_piece
from kain_maple_translator.badge_split import BadgeSplitter
from kain_maple_translator.ocr_recall import merge_recovery_lines
from kain_maple_translator.ocr_validation import needs_critical_retry,price_read_resolves


class VideoTranslationTests(unittest.TestCase):
    def setUp(self):self.tr=Translator(body_only=True)
    def fast(self,text):
        out=self.tr.translate_fast(text)
        self.assertIsNotNone(out)
        return out
    def test_short_party_not_intelligence_stat(self):
        for text in ('JPT','Jpt','jpt','J>PT'):
            self.assertEqual(self.fast(text),'파티 참가 원해요')
    def test_pq_rush_compact_and_spaced(self):
        for text in ('JPQ rush~','JPQrush~','J>PQ rush'):
            self.assertIn('연속 진행',self.fast(text))
    def test_pq_attention_does_not_invent_email(self):
        self.assertEqual(self.fast('J>PQ @@@@@@@@@'),'파티 퀘스트 참가 원해요')
    def test_elongated_congratulations(self):
        self.assertEqual(self.fast('GZZZZ *****'),'축하해요!')
        self.assertEqual(self.fast('gz'),'축하해')
    def test_unknown_short_spelling_not_silently_guessed(self):
        for text in ('IPT','UPT','JPI','JPEG','JPT 60k'):
            self.assertIsNone(party_intent(text))
    def test_real_email_is_unchanged(self):
        self.assertEqual(self.fast('email info@simply.com'),'email info@simply.com')
        self.assertIsNone(attention_tail('ask @Alice'))
    def test_invented_email_rejected(self):
        with patch('kain_maple_translator.translation.translate_generic',return_value='이메일 info@simply.com'):
            self.assertEqual(self.tr.translate('mysterious invitation','en-ko'),'mysterious invitation')
    def test_mixed_buy_and_exchange_are_separate(self):
        # The live app caches AI item-name drafts in the user profile
        # ('blue starlight' -> '파란 별빛'); keep this test independent of it.
        from kain_maple_translator import classic_item_index
        with patch.object(classic_item_index,'replace_unverified_item_names',
                          lambda text,translate_fn,max_new=2:text):
            out=self.fast('B>Blue Starlight T> Cherubs Bow for Orange Toy Hammer!')
        self.assertIn('블루 스타라이트 삽니다',out);self.assertIn('교환',out)
        self.assertIn('Cherubs Bow',out);self.assertNotIn('망치! 삽니다',out)
    def test_two_korean_links_survive(self):
        out=self.fast('[DEX +3 장갑] S> 150k; [별빛 모자] B> 220k')
        self.assertIn('[DEX +3 장갑]',out);self.assertIn('[별빛 모자]',out)
        self.assertIn('15만',out);self.assertIn('22만',out)
    def test_marker_inside_link_is_not_a_split(self):
        self.assertIsNone(mixed_trade_parts('[B> Edition] S> 50k'))
    def test_ratio_and_wrapped_contact(self):
        out=self.fast('[White Label Ring] T> THIS FOR INK WASH BUBBLE 1:1. DM M E')
        self.assertIn('[하얀 명찰 반지]',out);self.assertIn('(1:1)',out)
        self.assertIn('귓말',out);self.assertNotIn('메소',out)
    def test_quantity_exchange_preserves_both_quantities(self):
        out=self.fast('[Ink-and-Wash Painting Name Tag Ring] T>5 ink and wash name rings for 1 white label, firm')
        # R19: '1 white label' is now the Korean item name, the quantity stays
        self.assertIn('5 ink',out);self.assertIn('1 하얀 명찰',out)
        self.assertIn('교환',out);self.assertIn('조건 고정',out)
    def test_sale_price_and_dm(self):
        out=self.fast('[Pink Bunny Sweater] S>50K! DM ME!')
        self.assertIn('[핑크바니 스웨터]',out);self.assertIn('5만 메소',out);self.assertIn('귓말',out)
    def test_per_unit_currency_and_channel(self):
        out=self.fast('S> cursed dolls 56meso ea, in fm ch10')
        self.assertIn('개당 56 메소',out);self.assertIn('10채널 자유시장',out)
        self.assertNotIn('10번 방',out)
    def test_unstated_currency_not_invented(self):
        out=self.fast('WTB Fragment of magic, 60 ea@@@@@')
        self.assertIn('개당 60',out);self.assertNotIn('메소',out);self.assertNotIn('단위 미표기',out)  # R16: no awkward note
    def test_immediate_purchase_price(self):
        out=self.fast('B> White Label Ring 180k right away')
        self.assertIn('18만 메소',out);self.assertIn('바로 거래',out)
    def test_compound_stat_does_not_gain_percent(self):
        out=self.fast('S>Emerald Earrings +6 Dex +3 Crit Dmg PMO')
        self.assertIn('+6 민첩',out);self.assertIn('+3 크리티컬 데미지',out)
        self.assertNotIn('%',out)


class VideoOCRTests(unittest.TestCase):
    def test_real_mixed_frame_recovers_both_white_rows(self):
        image=cv2.imread(str(Path(__file__).parent/'fixtures/r12/mixed-yellow-white.png'))
        rows=ink_rows_border_retry(image)[0]
        merged,count=supplement_white_rows(image,rows)
        # R13: the 1080p bright-glyph pass may already add both white rows;
        # either path must leave both baselines present.
        self.assertGreaterEqual(count+sum(bool(getattr(r,'bright',False)) for r in rows),2)
        for baseline in (52,68):
            self.assertTrue(any(abs(r.rect[1]+r.rect[3]/2-baseline)<5 for r in merged))
        self.assertEqual(supplement_white_rows(image,merged)[1],0)
    def test_three_real_channel_badges_anchor_missing_row(self):
        image=cv2.imread(str(Path(__file__).parent/'fixtures/r12/three-pink-white.png'))
        found=BadgeSplitter().locate_rows(image)
        self.assertEqual(len(found),3)
        for baseline in (14,32,50):
            self.assertTrue(any(abs(y+h/2-baseline)<4 for y,h in found))
    def test_plain_background_cannot_manufacture_badge(self):
        for color in ((20,20,20),(210,160,190),(30,210,230)):
            image=np.full((80,620,3),color,np.uint8)
            self.assertEqual(BadgeSplitter().locate_rows(image),[])
    def test_recovery_does_not_append_badge_inside_full_row(self):
        whole=Line('Carnitas: B> White Label Ring 180k',.97,(0,0,395,20))
        badge=Line('CR30',.7,(65,2,30,14))
        recovered=merge_recovery_lines([whole],[whole,badge])
        self.assertEqual([r.text for r in recovered],[whole.text])
    def test_far_character_label_is_not_chat_tail(self):
        rows=merge_chat_ocr([Line('samiez: JPQ rush',.95,(0,0,150,18)),
                             Line('tennis is FUN',.99,(295,0,100,18))])
        self.assertEqual(rows[0]['body'],'JPQ rush')
    def test_close_body_fragments_still_join(self):
        rows=merge_chat_ocr([Line('Alice: need',.95,(0,0,90,18)),Line('help',.95,(95,0,30,18))])
        self.assertEqual(rows[0]['body'],'need help')
    def test_attention_continuation_does_not_reject_readable_trade(self):
        rows=merge_chat_ocr([Line('Alice: WTB Fragment of magic, 60 ea@@@@',.98,(0,0,590,18)),
                             Line('@@@@@②@②@@@',.51,(27,18,310,18))])
        self.assertEqual(rows[0]['confidence'],.98)
        self.assertEqual(rows[0]['body'],'WTB Fragment of magic, 60 ea@@@@')
    def test_digit_continuation_is_never_discarded(self):
        rows=merge_chat_ocr([Line('Alice: Elixer 50',.98,(0,0,590,18)),Line('0@@@@',.9,(27,18,70,18))])
        self.assertIn('0@@@@',rows[0]['body'])
    def test_isolated_mask_survives_nickname_split(self):
        source=np.full((18,120,3),90,np.uint8)
        neutral=np.full_like(source,255);neutral[5:13,15:70]=0
        (kept,_),_= _stable_piece(source,with_offset=True,neutral=neutral)
        self.assertTrue(np.any(kept==0))
    def test_price_ocr_requires_actual_corresponding_alternate(self):
        self.assertTrue(needs_critical_retry('S> 5OK',[]))
        self.assertTrue(price_read_resolves(('S> 5OK',.96),('S> 50K',.97)))
        for other in ('S> 500K','B> 50K','S> 5K','S> 60K'):
            self.assertFalse(price_read_resolves(('S> 5OK',.96),(other,.99)))
        self.assertFalse(price_read_resolves(('S> 5OK',.96),('S> 50K',.6)))

class MalformedLinkTests(unittest.TestCase):
    def test_unclosed_bracket_does_not_recurse(self):
        from kain_maple_translator.chat_shorthand import expand_shorthand
        for text in ('[White Label Ring','hello [','[] trailing [broken','[valid] ty [broken'):
            result=expand_shorthand(text)
            self.assertIsInstance(result,str)
            self.assertIn('[',result)
    def test_intact_link_still_keeps_its_contents(self):
        from kain_maple_translator.chat_shorthand import expand_shorthand
        self.assertEqual(expand_shorthand('[ty] idk'),'[ty] I do not know')
