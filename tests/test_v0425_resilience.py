"""Regression for the supplied CP949 build failure and latency/data guards."""
import copy
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.trade_memory import (TradeMemory,protect_values,safe_slot_translation,
                                               normalize_chat_input,split_clauses)
from kain_maple_translator.translation import Translator,TranslationError
from kain_maple_translator import translation as translation
from kain_maple_translator.fast_vision import ink_rows,IncrementalChatOCR
from kain_maple_translator.frame_context import inspect_scrollbar,without_scrollbar
from kain_maple_translator.badge_split import BadgeSplitter
from kain_maple_translator.timings import LatencyBook
from kain_maple_translator.core import ChatFrameTracker

ROOT=Path(__file__).resolve().parents[1]


class ConsoleTests(unittest.TestCase):
    def test_real_cp949_redirect_does_not_crash_on_en_dash(self):
        env={**os.environ,'PYTHONIOENCODING':'cp949','PYTHONUTF8':'0'}
        code="from kain_maple_translator.console_io import configure_utf8_console; configure_utf8_console(); print('20–29 테스트 😀')"
        out=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True)
        self.assertEqual(out.returncode,0,out.stderr)
        self.assertIn('20–29 테스트 😀',out.stdout.decode('utf-8'))
    def test_powershell_forces_utf8_for_all_native_python_stages(self):
        script=(ROOT/'scripts/BUILD-WINDOWS.ps1').read_text('utf-8-sig')
        self.assertIn("$env:PYTHONIOENCODING = 'utf-8:backslashreplace'",script)
        self.assertIn("@('-X', 'utf8', '-u') + $Arguments",script)


class MemoryTests(unittest.TestCase):
    def test_item_and_price_changes_reuse_template_without_stale_values(self):
        tr=Translator()
        with patch.object(translation,'translate_generic',side_effect=AssertionError('model called')):
            a=tr.translate('S> [Unique Unlisted A] 220k OBO','en-ko')
            b=tr.translate('S> [Unique Unlisted B] 1.5m OBO','en-ko')
        self.assertIn('[Unique Unlisted A]',a);self.assertIn('22만',a)
        self.assertIn('[Unique Unlisted B]',b);self.assertIn('150만',b)
        self.assertNotIn('Unique Unlisted A',b)
        self.assertGreaterEqual(tr.trade_memory.hits,1)
    def test_both_requested_reverse_item_offer_examples_share_template(self):
        m=TradeMemory()
        a=m.translate('[Kitty Chat Ring] S>Pm Offers')
        b=m.translate('[Ink-and-Wash Painting Name Tag Ring] S>Pm Offers')
        self.assertIn('[Kitty Chat Ring]',a)
        self.assertIn('[수묵화 명찰 반지]',b)
        self.assertEqual(m.compiled,1);self.assertEqual(m.hits,1)
    def test_decimal_conversion_is_exact_not_model_output(self):
        m=TradeMemory()
        for price,want in [('220k','22만'),('1.5m','150만'),('0.001m','1,000'),('2b','20억')]:
            self.assertIn(want,m.translate('S> [Unlisted] '+price))
        self.assertIn('0.1 메소',m.translate('S> [Unlisted] 0.0001k'))
    def test_template_cache_is_bounded(self):
        m=TradeMemory(capacity=1)
        m.translate('S> [One] 220k');m.translate('B> [Two] 220k')
        self.assertEqual(len(m.cache),1)
    def test_arbitrary_unknown_grammar_is_not_a_guessed_template(self):
        self.assertIsNone(TradeMemory().translate('[Sword] makes me happy 220k'))
    def test_masked_template_rejects_missing_duplicate_and_invented_numbers(self):
        p=protect_values('I saw [Unlisted Sword] for 220k')
        self.assertIsNone(p.restore('아이템 999'))
        self.assertIsNone(p.restore(p.masked+' '+p.slots[0].marker))
        self.assertIsNone(p.restore(p.masked+' 123'))
        r=p.restore(p.masked)
        self.assertIn('[Unlisted Sword]',r);self.assertIn('22만',r)
    def test_failed_placeholder_does_not_resubmit_real_values_to_model(self):
        p=protect_values('Please inspect [Unlisted Sword] for 220k')
        calls=[]
        def model(text):
            calls.append(text)
            return '자리표시자가 사라짐' if 'KAINITEM' in text else '확인해 주세요'
        result=safe_slot_translation(p,model)
        self.assertIn('[Unlisted Sword]',result);self.assertIn('22만',result)
        self.assertFalse(any('Unlisted Sword' in c or '220k' in c for c in calls))
    def test_masked_model_failure_still_uses_safe_anchored_fallback(self):
        p=protect_values('Please inspect [Unlisted Sword]')
        def model(text):
            if 'KAINITEM' in text:raise TranslationError('unknown token')
            return '확인해 주세요'
        self.assertIn('[Unlisted Sword]',safe_slot_translation(p,model))
    def test_only_evidenced_start_prefixes_are_repaired(self):
        self.assertEqual(normalize_chat_input('5> [Sword] 220k'),'S> [Sword] 220k')
        self.assertEqual(normalize_chat_input('S) WG 2m'),'S> WG 2m')
        self.assertEqual(normalize_chat_input('5>4'),'5>4')
        self.assertEqual(normalize_chat_input('hello S) friend'),'hello S) friend')
    def test_known_elongation_and_capitals_leave_items_unchanged(self):
        self.assertEqual(normalize_chat_input('PLEASEEE HELP ME [PLEASEEE HAT]'),'please help me [PLEASEEE HAT]')
    def test_split_does_not_break_links_price_labels_or_fractions(self):
        self.assertEqual(split_clauses('S> [A | B] 220k a/w 2m'),['S> [A | B] 220k a/w 2m'])
        self.assertEqual(split_clauses('one clause | another clause'),['one clause','another clause'])
        self.assertEqual(split_clauses('1/2 of this'),['1/2 of this'])
    def test_known_chat_slang_and_tiny_fragments_do_not_hallucinate(self):
        tr=Translator()
        self.assertEqual(tr.translate_fast('pleaseee where r u rn'),'지금 어디 있어요?')
        with patch.object(translation,'translate_generic',side_effect=AssertionError('AI called')):
            self.assertEqual(tr.translate('zz','en-ko'),'zz')
            self.assertEqual(tr.translate('!!!','en-ko'),'!!!')
    def test_sender_name_is_not_normalized_as_an_english_word(self):
        self.assertEqual(Translator().translate('HELP : hi','en-ko'),'HELP : 안녕')
    def test_plain_level_context_is_kept_when_numbers_match(self):
        calls=[]
        def model(text,pair):
            calls.append(text);return '레벨 20~29 플레이어'
        with patch.object(translation,'translate_generic',side_effect=model):
            result=Translator().translate('All players at level 20-29','en-ko')
        self.assertIn('20~29',result)
        self.assertEqual(len(calls),1)
        self.assertNotIn('KAIn'.upper(),calls[0])
    def test_purchase_template_preserves_item_and_amount(self):
        out=Translator().translate_fast('I bought [Unlisted Item] for 1.5m yesterday.')
        self.assertEqual(out,'어제 [Unlisted Item] 150만 메소에 샀어요')


class EnginePolicyTests(unittest.TestCase):
    def _load(self,supported,broken=False):
        calls=[]
        class Engine:
            def __init__(self,path,**kwargs):
                calls.append(kwargs)
                if broken:raise RuntimeError('corrupt model path')
                self.compute_type=kwargs['compute_type']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'metadata.json').write_text('{}')
            module=types.SimpleNamespace(Translator=Engine,get_supported_compute_types=lambda device:supported)
            sp=types.SimpleNamespace(SentencePieceProcessor=lambda **kwargs:object())
            with patch.dict(translation._READY,{'en-ko':root}),patch.dict(translation._ENGINES,{},clear=True),patch.dict(sys.modules,{'ctranslate2':module,'sentencepiece':sp}):
                if broken:
                    with self.assertRaisesRegex(TranslationError,'corrupt model path'):translation._engine_for('en-ko')
                else:translation._engine_for('en-ko')
        return calls
    def test_int8_support_selected_explicitly(self):
        self.assertEqual(self._load({'int8','float32'})[0]['compute_type'],'int8')
    def test_fp32_only_when_capability_requires_it(self):
        self.assertEqual(self._load({'float32'})[0]['compute_type'],'float32')
    def test_int8_float32_is_preferred_over_full_fp32(self):
        self.assertEqual(self._load({'int8_float32','float32'})[0]['compute_type'],'int8_float32')
    def test_model_load_error_does_not_silently_retry_fp32(self):
        self.assertEqual(len(self._load({'int8','float32'},True)),1)
    def test_dynamic_limit_and_repeat_guard(self):
        calls=[]
        engine=types.SimpleNamespace(translate_batch=lambda tokens,**kw:(calls.append(kw) or [types.SimpleNamespace(hypotheses=[['안녕','</s>']])]))
        tokenizer=types.SimpleNamespace(encode=lambda text,out_type:['a','b'],decode=lambda tokens:'안녕')
        with patch.object(translation,'prepare_models'),patch.object(translation,'_engine_for',return_value=(engine,tokenizer,'')):
            self.assertEqual(translation.translate_generic('some text','en-ko'),'안녕')
        self.assertLess(calls[0]['max_decoding_length'],180)
        self.assertEqual(calls[0]['no_repeat_ngram_size'],3)
        self.assertFalse(calls[0]['replace_unknowns'])
        self.assertEqual(calls[0]['beam_size'],2)
    def test_capped_output_is_rejected_instead_of_displayed_truncated(self):
        engine=types.SimpleNamespace(translate_batch=lambda tokens,**kw:[types.SimpleNamespace(hypotheses=[['x']*kw['max_decoding_length']])])
        tokenizer=types.SimpleNamespace(encode=lambda text,out_type:['a'],decode=lambda tokens:'잘린 결과')
        with patch.object(translation,'prepare_models'),patch.object(translation,'_engine_for',return_value=(engine,tokenizer,'')):
            with self.assertRaisesRegex(TranslationError,'길이 제한'):translation.translate_generic('some text','en-ko')


class PixelAndHistoryTests(unittest.TestCase):
    def scrollbar(self,top):
        f=np.full((150,600,3),25,dtype=np.uint8);f[:,580:]=(240,220,200)
        f[top:top+30,583:597]=(180,100,40)
        return f
    def test_scrollbar_bottom_and_history_positions(self):
        self.assertIs(inspect_scrollbar(self.scrollbar(95)).at_bottom,True)
        self.assertIs(inspect_scrollbar(self.scrollbar(25)).at_bottom,False)
    def test_ordinary_blue_text_does_not_become_a_scrollbar(self):
        f=np.full((150,600,3),25,dtype=np.uint8)
        cv2.putText(f,'Alice: blue',(425,25),cv2.FONT_HERSHEY_SIMPLEX,.5,(200,100,40),1)
        self.assertIsNone(inspect_scrollbar(f).at_bottom)
    def test_repeated_saturated_blue_chat_ink_is_not_a_scrollbar_rail(self):
        f=np.full((150,600,3),25,dtype=np.uint8)
        for y in range(20,150,25):
            cv2.putText(f,'XXX',(555,y),cv2.FONT_HERSHEY_SIMPLEX,.5,(220,160,50),2)
        self.assertIsNone(inspect_scrollbar(f).at_bottom)
    def test_actual_supplied_scrollbar_is_detected_at_bottom(self):
        f=cv2.imread(str(ROOT/'tests/fixtures/partial-coloured-chat.png'))
        self.assertIs(inspect_scrollbar(f).at_bottom,True)
    def test_scrollbar_pixels_are_removed_from_ocr_input(self):
        f=self.scrollbar(95);c=inspect_scrollbar(f);clean=without_scrollbar(f,c)
        self.assertTrue(np.all(clean[:,-10:]==25))
    def test_tightly_merged_double_line_triggers_height_guard(self):
        f=np.full((60,400,3),25,dtype=np.uint8)
        cv2.putText(f,'Alice: first',(5,22),cv2.FONT_HERSHEY_SIMPLEX,.5,(240,240,240),1)
        cv2.putText(f,'Bob: second',(5,35),cv2.FONT_HERSHEY_SIMPLEX,.5,(240,240,240),1)
        rows,uncertain=ink_rows(f,height_hint=8)
        self.assertTrue(uncertain or len(rows)>=2)
    def test_low_contrast_coloured_text_is_segmented(self):
        f=np.full((35,500,3),(30,190,230),dtype=np.uint8)
        cv2.putText(f,'Alice: S> 220k',(5,23),cv2.FONT_HERSHEY_SIMPLEX,.5,(38,173,213),1,cv2.LINE_AA)
        rows,_=ink_rows(f)
        self.assertGreaterEqual(len(rows),1)
    def test_exact_pixel_hash_changes_with_one_price_digit(self):
        def draw(text):
            f=np.full((35,500,3),25,dtype=np.uint8)
            cv2.putText(f,text,(5,23),cv2.FONT_HERSHEY_SIMPLEX,.5,(240,240,240),1)
            return ink_rows(f)[0][0].key
        self.assertNotEqual(draw('Alice: 220k'),draw('Alice: 221k'))
    def test_same_message_new_occurrence_is_not_lost_to_ocr_cache(self):
        t=ChatFrameTracker()
        def row(text):return {'nickname':'Alice','body':text}
        t.new([row('one'),row('same')])
        out=t.new([row('same'),row('same')])
        self.assertEqual([(r['nickname'],r['body']) for r in out],[('Alice','same')])
    def test_badge_missing_or_clipped_name_uses_whole_line_path(self):
        splitter=BadgeSplitter()
        f=np.full((25,400,3),25,dtype=np.uint8)
        self.assertIsNone(splitter.split(f,f))
        real=cv2.imread(str(ROOT/'tests/fixtures/partial-coloured-chat.png'))[91:115,:350]
        self.assertIsNone(splitter.split(real,real))
    def test_real_sprite_with_full_name_has_confirmed_separator(self):
        f=cv2.imread(str(ROOT/'tests/fixtures/calibrated-badge-full-prefix.png'))
        row=ink_rows(f)[0][0]
        self.assertIsNotNone(BadgeSplitter().split(row.original,row.neutral))


class TimingTests(unittest.TestCase):
    def test_process_preinit_optout_is_forced_before_ort_import(self):
        env={**os.environ,'ORT_DISABLE_TELEMETRY':'0'}
        code="import os; import kain_maple_translator; print(os.environ['ORT_DISABLE_TELEMETRY'])"
        out=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True)
        self.assertEqual(out.returncode,0,out.stderr)
        self.assertEqual(out.stdout.strip(),b'1')
    @unittest.skipUnless(importlib.util.find_spec('onnxruntime') is not None,
                         'ONNX Runtime is not installed in this QA environment')
    def test_telemetry_is_disabled_before_any_ocr_session(self):
        from kain_maple_translator.vision import TextRecognizer
        events=[]
        with (patch('onnxruntime.disable_telemetry_events',side_effect=lambda:events.append('disable')),
              patch('rapidocr.RapidOCR',side_effect=lambda **kw:events.append('session'))):
            TextRecognizer()
        self.assertEqual(events,['disable','session','session','session'])
    def test_p95_max_and_bounded_window(self):
        b=LatencyBook(capacity=3)
        for x in [100,10,20,30]:b.observe('ocr',x)
        stats=b.snapshot()
        self.assertEqual(stats['ocr_p50_ms'],20)
        self.assertEqual(stats['ocr_p95_ms'],30)
        self.assertEqual(stats['ocr_max_ms'],30)
        self.assertEqual(stats['ocr_lifetime_max_ms'],100)
        self.assertEqual(stats['ocr_samples'],4)


if __name__=='__main__':unittest.main()
