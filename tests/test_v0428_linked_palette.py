"""Label preservation, conservative repair, real palette and duplicate regressions."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.linked_ocr import LinkedItemOCR, character_centres, _label
from kain_maple_translator.link_integrity import preserve_link_labels
from kain_maple_translator.translation import Translator
from kain_maple_translator.chat_shorthand import shorthand_translation, expand_shorthand
from kain_maple_translator.chat_render import colored_item_html
from kain_maple_translator.core import ChatFrameTracker, should_translate_body
from kain_maple_translator.recognition_batch import recognize_width_buckets
from kain_maple_translator.source_palette import sample_palette
from kain_maple_translator.row_admission import classified_chat_rows, RowAdmission, _CLASSIFIED_CACHE
from kain_maple_translator.vision import Line


class FakeKorean:
    def __init__(self, *answers): self.answers=list(answers); self.calls=0
    def recognize_txt(self, images):
        self.calls+=1
        text,score=self.answers.pop(0)
        return SimpleNamespace(txts=[text]*len(images),scores=[score]*len(images))


def metadata(text, confidence=.99):
    letters=list(''.join(text.split()))
    return SimpleNamespace(words=[letters],word_cols=[list(range(len(letters)))],
                           line_txt_len=len(letters),confs=[confidence]*len(text))


class ItemRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.text='Alice ; [口口 60%] S> 220k OBO'
        self.image=np.full((20,300,3),255,dtype=np.uint8)
        self.tasks=[(self.image,self.image.copy())]
    def correct(self, engine, text=None, confidence=.99):
        text=text or self.text
        return engine.correct([(text,confidence)],self.tasks,[metadata(text,confidence)])[0]
    def test_high_confidence_wrong_script_gets_item_only_repair(self):
        fake=FakeKorean(('[장갑 공격력 60%]',.98),('[장갑 공격력 60%]',.97))
        result,score=self.correct(LinkedItemOCR(fake))
        self.assertEqual(result,'Alice ; [장갑 공격력 60%] S> 220k OBO')
        self.assertGreater(score,.9);self.assertEqual(fake.calls,2)
    def test_neighbour_glyphs_outside_one_bracket_do_not_reject_correct_label(self):
        fake=FakeKorean(('[장갑 공격력 60%]?',.95),('[장갑 공격력 60%]9',.94))
        self.assertIn('[장갑 공격력 60%]',self.correct(LinkedItemOCR(fake))[0])
    def test_disagreement_inside_label_is_not_guessed(self):
        for second in ('[장갑 공격력 80%]','[장감 공격력 60%]'):
            fake=FakeKorean(('[장갑 공격력 60%]',.98),(second,.98))
            result,score=self.correct(LinkedItemOCR(fake))
            self.assertEqual(result,self.text);self.assertLess(score,.88)
    def test_mixed_hangul_english_and_bonus_survive(self):
        fake=FakeKorean(('[한글 ATT +2]',.97),('[한글 ATT +2]',.96))
        self.assertIn('[한글 ATT +2]',self.correct(LinkedItemOCR(fake))[0])
    def test_low_confidence_korean_is_not_selected(self):
        fake=FakeKorean(('[장갑 공격력 60%]',.65))
        self.assertEqual(self.correct(LinkedItemOCR(fake))[0],self.text)
    def test_item_cache_does_not_cache_surrounding_price(self):
        fake=FakeKorean(('[장갑 공격력 60%]',.98),('[장갑 공격력 60%]',.98))
        engine=LinkedItemOCR(fake);self.correct(engine)
        result,_=self.correct(engine,self.text.replace('220k','330k'))
        self.assertIn('330k',result);self.assertNotIn('220k',result)
        self.assertEqual(fake.calls,2);self.assertEqual(engine.stats['item_ocr_cache_hits'],1)
    def test_missing_ctc_alignment_never_guesses_crop(self):
        info=metadata('Different text')
        self.assertIsNone(character_centres(self.text,info,300))
        fake=FakeKorean();engine=LinkedItemOCR(fake)
        self.assertEqual(engine.correct([(self.text,.99)],self.tasks,[info]),[(self.text,.99)])
        self.assertEqual(fake.calls,0)
    def test_confident_english_skips_extra_model(self):
        fake=FakeKorean();engine=LinkedItemOCR(fake)
        self.correct(engine,'Alice ; [Black Sunglasses] S> 220k')
        self.assertEqual(fake.calls,0);self.assertEqual(engine.stats['item_english_skips'],1)
    def test_english_negative_is_cached(self):
        fake=FakeKorean(('[Black Sunglasses]',.97));engine=LinkedItemOCR(fake)
        for _ in range(2):self.correct(engine,'Alice ; [Black Sunglasses] S> 220k',.95)
        self.assertEqual(fake.calls,1)
    def test_item_bonus_stays_inside_comparison(self):
        self.assertEqual(_label('[한글 +2]9'),'한글 +2')
        self.assertNotEqual(_label('[한글 +2]9'),_label('[한글 +3]9'))
    def test_multiple_brackets_are_not_silently_collapsed(self):
        fake=FakeKorean(('[장갑][모자]',.99))
        self.assertEqual(self.correct(LinkedItemOCR(fake))[0],self.text)


class TranslationIntegrityTests(unittest.TestCase):
    def translate(self,text):
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('unnecessary model')):
            out=Translator(body_only=True).translate_fast(text)
        self.assertIsNotNone(out);return out
    def test_actual_denim_reverse_sell_keeps_item(self):
        out=self.translate('[Denim Wrinkled Skirt] SELLING FOR 30k OBO')
        for part in ('[청 주름 치마]','3만','팝니다','협의'):self.assertIn(part,out)
    def test_long_korean_label_is_still_translation_eligible(self):
        source='[아주 긴 한글 아이템 이름 공격력 주문서 60%] S> 220k OBO'
        self.assertTrue(should_translate_body(source))
        out=self.translate(source)
        self.assertIn(source.split(']')[0]+']',out);self.assertIn('22만',out)
    def test_this_pm_link_template(self):
        out=self.translate('[한글 ATT +2] S> this! pm')
        self.assertIn('[한글 ATT +2]',out);self.assertIn('귓말',out)
    def test_mutated_korean_labels_restored_verbatim(self):
        self.assertEqual(preserve_link_labels('[한글 ATT +2] S>','[엉뚱한 이름] 팝니다'),'[한글 ATT +2] 팝니다')
    def test_missing_label_restored_once(self):
        out=preserve_link_labels('[파란 모자] S> 10k','1만에 팝니다')
        self.assertEqual(out.count('[파란 모자]'),1);self.assertIn('1만',out)
    def test_extra_invented_item_returns_source(self):
        source='[파란 모자] S>'
        self.assertEqual(preserve_link_labels(source,'[파란 모자] [공짜 장갑] 팝니다'),source)
    def test_scroll_attack_link_is_still_localized(self):
        self.assertIn('[공격력:]',self.translate('S> [Attack:] glove att 60%'))
    def test_verified_english_catalog_translation_is_not_undone(self):
        from kain_maple_translator.item_catalog import ItemCatalog
        catalog=ItemCatalog([dict(name_en='Example Hat',name_ko='검증된 모자',aliases_en='')])
        with patch('kain_maple_translator.item_catalog.current_catalog',return_value=catalog):
            out=self.translate('[Example Hat] SELLING FOR 30k OBO')
        self.assertIn('[검증된 모자]',out);self.assertNotIn('[Example Hat]',out)
    def test_exact_abbreviations(self):
        for source,word in [('pmo','귓말'),('lmk','알려'),('TY','고마워'),('np','괜찮아'),('lfm 2 kpq','2명')]:
            self.assertIn(word,shorthand_translation(source))
    def test_expand_keeps_items_and_urls(self):
        self.assertEqual(expand_shorthand('[TY pls Ring] lmk'),'[TY pls Ring] let me know')
        self.assertEqual(expand_shorthand('https://example.com/pls lmk'),'https://example.com/pls lmk')


class PaletteAndTrackingTests(unittest.TestCase):
    def setUp(self): _CLASSIFIED_CACHE.clear()
    def frame(self,bg,fg):
        image=np.full((32,600,3),bg,dtype=np.uint8)
        cv2.putText(image,'Alice ; S> WG 220k',(4,24),cv2.FONT_HERSHEY_SIMPLEX,.6,fg,1,cv2.LINE_AA)
        return image,[Line('Alice ; S> WG 220k',.99,(0,0,600,32),True,'abc',{'body_start':90,'name_end':60})]
    def test_white_body_wins_over_channel_hint_without_band(self):
        image,lines=self.frame((25,25,25),(245,245,245))
        row=classified_chat_rows(lines,image,0,0)[0]
        self.assertEqual(row['kind'],'normal');self.assertTrue(row['source_white_body'])
    def test_colored_band_with_white_body_is_megaphone(self):
        image,lines=self.frame((180,130,60),(245,245,245))
        self.assertNotEqual(classified_chat_rows(lines,image,0,0)[0]['kind'],'normal')
    def test_cached_classification_is_not_mutated_by_consumer(self):
        image,lines=self.frame((25,25,25),(245,245,245))
        first=classified_chat_rows(lines,image,0,0);first[0]['body']='corrupt'
        self.assertNotEqual(classified_chat_rows(lines,image,0,0)[0]['body'],'corrupt')
    def test_previous_mega_does_not_override_actual_white_chat(self):
        gate=RowAdmission();row=dict(nickname='Alice',body='same words',confidence=.99,kind='megaphone',band_color='#ffffff')
        gate.filter([row.copy()],1)
        normal=dict(row,kind='normal',source_white_body=True,band_color='')
        accepted=gate.filter([normal.copy()],1.1)
        self.assertEqual(len(accepted),1)
        self.assertEqual(accepted[0]['kind'],'normal')
    def test_actual_yellow_item_has_different_color_from_body(self):
        path=Path(__file__).parent/'fixtures/user-native-palette-rows.png'
        image=cv2.imread(str(path))[40:64,:578]
        colors=sample_palette(image,'#e5b605',{'body_start':130,'name_end':64,'item_ranges':[(134,352)]})
        self.assertIn('item_color',colors);self.assertNotEqual(colors['item_color'],colors['text_color'])
    def test_escaped_item_color_html(self):
        out=colored_item_html('[<b>&] S>','#fffe99')
        self.assertIn('color:#fffe99',out);self.assertIn('&lt;b&gt;&amp;',out)
        self.assertNotIn('<b>',out)
    def row(self,key,text='hello'): return dict(nickname='Alice',body=text,visual_key=key)
    def test_ocr_text_drift_of_same_pixels_does_not_repeat(self):
        tracker=ChatFrameTracker();tracker.new([self.row('same','장갑')])
        self.assertEqual(tracker.new([self.row('same','장감')]),[])
    def test_changed_price_is_new(self):
        tracker=ChatFrameTracker();tracker.new([self.row('one','220k')])
        self.assertEqual(len(tracker.new([self.row('two','330k')])),1)
    def test_identical_message_after_scroll_is_new(self):
        tracker=ChatFrameTracker();tracker.new([self.row('a'),self.row('b')])
        out=tracker.new([self.row('b'),self.row('b')])
        self.assertEqual(len(out),1)
    def test_obs_receives_all_source_palette_fields(self):
        from kain_maple_translator.obs_source import OBSChatSource
        source=OBSChatSource(port=0)
        record=dict(nickname='Alice',translated='[한글 아이템] 팝니다',kind='item',
                    band_color='#e5b605',text_color='#795506',nickname_color='#634106',item_color='#fffe99')
        source.set_state([record],source_chat_colors=True)
        state=source.state()
        for key in ('band_color','text_color','nickname_color','item_color'):
            self.assertEqual(state['messages'][0][key],record[key])
        self.assertTrue(state['source_chat_colors'])


class BatchTests(unittest.TestCase):
    def test_width_buckets_preserve_result_order(self):
        calls=[]
        def recognize(images):
            widths=[im.shape[1] for im in images];calls.append(widths)
            return SimpleNamespace(txts=[str(w) for w in widths],scores=[.99]*len(widths),word_results=widths)
        images=[np.zeros((20,w,3),dtype=np.uint8) for w in (600,40,50,500,60)]
        out=recognize_width_buckets(SimpleNamespace(recognize_txt=recognize),images)
        self.assertEqual(out.txts,['600','40','50','500','60'])
        self.assertEqual(out.word_results,[600,40,50,500,60])
        self.assertEqual(len(calls),2)
        self.assertTrue(all(max(c)/min(c)<=2 for c in calls))


if __name__=='__main__': unittest.main()
