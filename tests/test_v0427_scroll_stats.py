"""Attack/scroll fragments from the translated screenshot, plus stat guards.

The source game chat is absent from that screenshot. The reconstructed inputs
below are translation regressions, not proof of its original OCR contents.
"""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.translation import Translator
from kain_maple_translator.trade_stats import localize_stat_terms,numeric_signature
from kain_maple_translator.ocr_validation import critical_floor,needs_critical_retry,prefer_critical_read,same_numeric_fields
from kain_maple_translator.ocr_validation import loses_known_terms
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.scroll_context import scroll_reference


class StatTradeTests(unittest.TestCase):
    def translate(self,source):
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('stat was sent to AI')):
            result=Translator(body_only=True).translate_fast(source)
        self.assertIsNotNone(result,source)
        return result

    def test_screenshot_glove_kfan_and_two_percentages(self):
        out=self.translate('S> [Attack: ] glove att 60% Kfan +1 100% scrolls')
        for part in ('[공격력:]','장갑 공격력 60% 주문서','태극부채 +1','100%','팝니다'):
            self.assertIn(part,out)
        self.assertNotIn('glove',out.lower());self.assertNotIn(' att',out.lower())
        self.assertEqual(out.count('60%'),1);self.assertEqual(out.count('100%'),1)

    def test_second_screenshot_fragment_does_not_assign_bonus_to_attack(self):
        out=self.translate('S> [Attack: Claw] Claw Att Kfan +2 clean')
        self.assertIn('아대 공격력',out);self.assertIn('태극부채 +2',out)
        self.assertNotIn('공격력 +2',out)

    def test_all_compound_scrolls_are_localized(self):
        out=self.translate('S> glove att60% / claw att100% / cape luk60%')
        for fragment in ('장갑 공격력 60% 주문서','아대 공격력 100% 주문서','망토 행운 60% 주문서'):
            self.assertIn(fragment,out)

    def test_explicit_attack_bonus_success_rate_and_price_are_separate(self):
        out=self.translate('S> claw att +2 60% scroll 220k')
        self.assertIn('공격력 +2',out);self.assertIn('60%',out);self.assertIn('22만',out)
        self.assertNotIn('260%',out)

    def test_attack_before_or_after_numeric_value(self):
        for source,required in [('S> Korean Fan 64 ATK, PMO',('64','공격력','태극부채','귓말')),
                                ('S> 8att WG 2m',('8','공격력','노가다 목장갑','200만')),
                                ('S> WG ATK+8 2m',('+8','공격력','노가다 목장갑','200만'))]:
            with self.subTest(source=source):
                out=self.translate(source)
                for part in required:self.assertIn(part,out)

    def test_magic_never_becomes_weapon_attack(self):
        for stat in ('M.ATT','MATT','MATK','magic attack','magic att'):
            out=self.translate('S> wand '+stat+' +12 500k')
            self.assertIn('마력',out);self.assertIn('+12',out);self.assertNotIn('공격력',out)

    def test_weapon_attack_spelling_variants(self):
        for stat in ('ATT','ATK','ATTK','WATK','W.ATT','weapon attack'):
            out=self.translate('S> claw '+stat+' +2 60% scroll')
            self.assertIn('아대 공격력',out);self.assertIn('+2',out);self.assertIn('60%',out)

    def test_other_stats_in_scroll_list(self):
        for source,expected in [('B> overall dex60% and cape str100%',('전신갑옷 민첩 60%','망토 힘 100%')),
                                ('S> earring int10% / shoes jump60%',('귀고리 지력 10%','신발 점프력 60%')),
                                ('S> helmet hp100% / pet equip speed60%',('투구 체력 100%','펫 장비 이동속도 60%'))]:
            out=self.translate(source)
            for part in expected:self.assertIn(part,out)

    def test_attached_ocr_spacing_does_not_change_digits(self):
        out=self.translate('S> gloveATT60% Kfan+2 100% scrolls')
        self.assertIn('공격력 60%',out);self.assertIn('태극부채+2',out);self.assertIn('100%',out)

    def test_gfa_and_gma_mixed_list(self):
        out=self.translate('B> GFA 60% / GMA 100%')
        self.assertIn('장갑 공격력 60% 주문서',out)
        self.assertIn('장갑 마력 100% 주문서',out)

    def test_unknown_success_rate_is_not_rewritten_to_known_one(self):
        out=self.translate('S> glove att 88% Kfan+2')
        self.assertIn('88%',out);self.assertNotIn('60%',out)

    def test_unknown_item_and_all_korean_links_stay_literal(self):
        for label in ('[Unknown Attack Wing]','[한글 ATT +2 장갑]','[공격력 60% 장갑]'):
            out=self.translate('S> '+label+' 64 ATK 220k')
            self.assertIn(label,out);self.assertIn('64',out);self.assertIn('공격력',out)

    def test_no_missing_scroll_parts_are_invented(self):
        out=self.translate('S> claw att Kfan+2')
        self.assertIn('아대 공격력',out);self.assertNotIn('%',out)
        self.assertNotIn('60',out);self.assertNotIn('공격력 +2',out)

    def test_a_downstream_formatter_cannot_drop_the_actual_attack_value(self):
        with patch('kain_maple_translator.natural_trade.trade_override',return_value='태극부채 공격력 팝니다. 가격 22만 메소'):
            out=self.translate('S> Korean Fan 64 ATK 220k')
        self.assertIn('64',out);self.assertIn('공격력',out)

    def test_joined_item_and_attack_value_is_also_protected(self):
        with patch('kain_maple_translator.natural_trade.trade_override',return_value='태극부채 공격력 팝니다. 가격 22만 메소'):
            out=self.translate('S> Kfan64ATK 220k')
        self.assertIn('64',out);self.assertIn('공격력',out)

    def test_a_downstream_formatter_cannot_swap_magic_and_attack_values(self):
        with patch('kain_maple_translator.natural_trade.trade_override',return_value='완드 마력 64 공격력 12 팝니다'):
            out=self.translate('S> wand 마력 12 공격력 64')
        self.assertIn('마력 12 공격력 64',out)

    def test_known_english_scroll_link_can_be_localized(self):
        out=self.translate('S> [Glove for ATT 60%] Kfan 64ATK')
        self.assertIn('[장갑 공격력 60% 주문서]',out);self.assertIn('64 공격력',out)

    def test_linked_scroll_with_pmo_is_localized_without_explicit_sale_tag(self):
        out=self.translate('[Glove for ATT 60%] PMO')
        self.assertIn('[장갑 공격력 60% 주문서]',out)
        self.assertIn('귓말',out)

    def test_known_link_with_joined_ocr_spacing_is_still_a_scroll(self):
        out=self.translate('S> [gloveATT60%] 220k')
        self.assertIn('[장갑 공격력 60% 주문서]',out)
        self.assertIn('22만',out)

    def test_nickname_and_linked_name_are_not_treated_as_stat_words(self):
        out=Translator().translate('AttackMaster ; S> [Attack Wing] 64 ATK','en-ko')
        self.assertTrue(out.startswith('AttackMaster : '));self.assertIn('[Attack Wing]',out)

    def test_ordinary_attack_sentence_does_not_enter_trade_rules(self):
        from kain_maple_translator.trade_stats import translate_stat_trade
        self.assertIsNone(translate_stat_trade('attack the monster please'))
        self.assertIsNone(translate_stat_trade('Matthew attacked the boss'))
        self.assertIsNone(translate_stat_trade('S> Magic Attack Potion 2m'))

    def test_percent_and_enhancement_signatures_preserved(self):
        source='glove att+2 60% Kfan+1 100% scrolls'
        localized=localize_stat_terms(source)
        self.assertEqual(numeric_signature(source),numeric_signature(localized))

    def test_chaos_has_no_invented_ten_percent(self):
        out=scroll_reference('Glove ATT Chaos')
        self.assertIn('혼돈',out);self.assertNotIn('10%',out)


class CriticalConfidenceTests(unittest.TestCase):
    def test_high_average_with_one_weak_attack_letter_requests_retry(self):
        text='Alice : S> glove alt 60% Kfan +2'
        conf=[.99]*len(text);conf[text.index('alt')+1]=.40
        self.assertTrue(needs_critical_retry(text,conf))

    def test_fully_confident_scroll_needs_no_extra_inference(self):
        text='Alice : S> glove att 60%'
        self.assertFalse(needs_critical_retry(text,[.99]*len(text)))

    def test_ordinary_chat_and_missing_confidence_are_not_retried(self):
        self.assertFalse(needs_critical_retry('Alice: hi there',[.2]*15))
        self.assertFalse(needs_critical_retry('glove att 60%',[]))

    def test_better_attack_letters_can_win_with_same_numbers(self):
        a='glove alt 60%';b='glove att 60%'
        ac=[.99]*len(a);ac[a.index('alt')+1]=.4
        self.assertTrue(prefer_critical_read((a,.97),(b,.96),ac,[.99]*len(b)))

    def test_retry_cannot_break_a_recognized_weapon_stat_or_scroll_word(self):
        for a,b in [('claw ATT+2 60% scroll','clow ATT+2 60% scroll'),
                    ('glove att 60%','glove ott 60%'),
                    ('Kfan +1 100% scrolls','Kfan +1 100% sorolls')]:
            self.assertTrue(loses_known_terms(a,b))
            self.assertFalse(prefer_critical_read((a,.95),(b,.99),[.3]*len(a),[.99]*len(b)))

    def test_attached_spacing_and_attack_alias_do_not_lose_terms(self):
        self.assertFalse(loses_known_terms('clawATT+2 60% scroll','claw ATK +2 60% scrolls'))

    def test_price_rate_plus_minus_or_level_conflict_cannot_win(self):
        source='glove att+2 60% 220k'
        for alternate in ('glove att+3 60% 220k','glove att+2 80% 220k','glove att+2 60% 230k','glove att-2 60% 220k','glove att+2 60 220k'):
            self.assertFalse(same_numeric_fields(source,alternate),alternate)
            self.assertFalse(prefer_critical_read((source,.95),(alternate,.99),[.2]*len(source),[.99]*len(alternate)))

    def test_confidence_never_indexes_an_unaligned_word_result(self):
        self.assertIsNone(critical_floor('glove att60%',[.99]))

    def test_unicode_percent_and_plus_are_equivalent(self):
        self.assertTrue(same_numeric_fields('ATT＋2 60％','ATT+2 60%'))

    def test_separate_bonus_and_percent_are_not_joined_by_whitespace_normalization(self):
        signature=numeric_signature('Kfan +1 100% scrolls 220k')
        self.assertEqual(signature[1],('100%',))
        self.assertEqual(signature[2],('+1',))


class RealStageSelection(unittest.TestCase):
    def run_ocr(self,first,second):
        calls=[]
        class OCR:
            def recognize_txt(self,images):
                calls.append(len(images));text,confs,score=(first if len(calls)==1 else second)
                return SimpleNamespace(txts=[text],scores=[score],word_results=[SimpleNamespace(confs=confs)])
        recognizer=SimpleNamespace(ocr=OCR(),korean_ocr=None,detect=lambda *args:[])
        image=np.full((35,500,3),25,dtype=np.uint8)
        cv2.putText(image,'Alice: S> glove att 60%',(5,23),cv2.FONT_HERSHEY_SIMPLEX,.5,(245,245,245),1)
        engine=IncrementalChatOCR(recognizer)
        # This OCR double returns a whole line, rather than two split pieces.
        with patch.object(engine.badges,'split_plain',return_value=None):
            lines=engine.detect(image,0,0)
        return calls,lines,engine

    def test_actual_candidate_pipeline_uses_character_confidence(self):
        a='Alice: S> glove alt 60%';b='Alice: S> glove att 60%'
        conf=[.99]*len(a);conf[a.index('alt')+1]=.4
        calls,lines,engine=self.run_ocr((a,conf,.97),(b,[.99]*len(b),.96))
        self.assertEqual(len(calls),2);self.assertIn('glove att',lines[0].text)
        self.assertEqual(engine.stats['critical_retry_rows'],1)

    def test_actual_candidate_pipeline_rejects_invented_rate(self):
        a='Alice: S> glove att 60%';b='Alice: S> glove att 80%'
        conf=[.99]*len(a);conf[a.index('60')]=.4
        calls,lines,engine=self.run_ocr((a,conf,.97),(b,[.99]*len(b),.99))
        self.assertIn('60%',lines[0].text);self.assertNotIn('80%',lines[0].text)
        self.assertLess(lines[0].confidence,.88)
        self.assertEqual(engine.stats['numeric_retry_disagreements'],1)


if __name__=='__main__':unittest.main()
