"""Behaviour regressions for scrolling, bursts, phantom normal chat and slang."""
import copy
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import types
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from kain_maple_translator.fast_vision import IncrementalChatOCR, ink_rows
from kain_maple_translator.vision import Line
from kain_maple_translator.core import ChatFrameTracker, merge_chat_ocr, parse_chat_line
from kain_maple_translator.row_admission import RowAdmission, classified_chat_rows
from kain_maple_translator.translation import Translator
from kain_maple_translator.translation_queue import TranslationQueue
from kain_maple_translator.capture_stream import ChatCaptureStream, CapturedChat
from kain_maple_translator.megaphone import row_appearance
from kain_maple_translator.chat_shorthand import shorthand_translation, expand_shorthand


def image(lines, height=130, width=620):
    frame = np.full((height,width,3),28,dtype=np.uint8)
    for text,y in lines:
        cv2.putText(frame,text,(8,y),cv2.FONT_HERSHEY_SIMPLEX,.5,(245,245,245),1,cv2.LINE_AA)
    return frame


class FakeOCR:
    def __init__(self):
        self.calls=[]
    def recognize_txt(self, images):
        self.calls.append(len(images))
        return types.SimpleNamespace(txts=tuple(f'Nick: message number {i}' for i in range(len(images))),scores=[.99]*len(images))


class FakeReader:
    def __init__(self):
        self.ocr=FakeOCR()
        self.recoveries=0
    def detect(self,*args):
        self.recoveries+=1
        return [Line('Nick: recovered text',.95,(5,8,210,18))]


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        # This fake always returns a complete chat line. Isolate full-row
        # caching here; real prefix/body recognition has its own replay tests.
        self.splitter=patch('kain_maple_translator.badge_split.BadgeSplitter.split_plain',return_value=None)
        self.splitter.start()
        self.addCleanup(self.splitter.stop)
    def test_repeat_frame_has_no_new_model_inference(self):
        reader=FakeReader(); engine=IncrementalChatOCR(reader)
        frame=image([('Alice: hello',25),('Bob: see you',55)])
        first=engine.detect(frame,0,0);second=engine.detect(frame,0,0)
        self.assertEqual(first,second)
        self.assertEqual(reader.ocr.calls,[2])
        self.assertEqual(engine.stats['cache_hits'],2)
    def test_scroll_moves_old_ink_without_ocr(self):
        reader=FakeReader();engine=IncrementalChatOCR(reader)
        a=engine.detect(image([('Alice: hello',25)]),0,0)
        b=engine.detect(image([('Alice: hello',55)]),200,300)
        self.assertEqual(reader.ocr.calls,[1])
        self.assertEqual(a[0].text,b[0].text)
        self.assertEqual(b[0].rect[1]-a[0].rect[1],330)
    def test_one_added_line_only_recognizes_new_line(self):
        r=FakeReader();e=IncrementalChatOCR(r)
        e.detect(image([('Alice: hello',25)]),0,0)
        e.detect(image([('Alice: hello',25),('Bob: 15m',55)]),0,0)
        self.assertEqual(r.ocr.calls,[1,1])
    def test_changed_price_never_reuses_old_ink(self):
        r=FakeReader();e=IncrementalChatOCR(r)
        e.detect(image([('Alice: S> 10m',25)]),0,0)
        e.detect(image([('Alice: S> 11m',25)]),0,0)
        self.assertEqual(r.ocr.calls,[1,1])
    def test_incomplete_stage_output_recovers_instead_of_losing_rows(self):
        r=FakeReader();r.ocr.recognize_txt=lambda _: types.SimpleNamespace(txts=[],scores=[])
        e=IncrementalChatOCR(r);out=e.detect(image([('Alice: hello',25)]),0,0)
        self.assertIn('recovered',out[0].text)
        self.assertEqual(e.stats['recognition_errors'],1)
    def test_recovery_itself_is_cached(self):
        r=FakeReader();r.ocr.recognize_txt=lambda _: types.SimpleNamespace(txts=[],scores=[])
        e=IncrementalChatOCR(r);frame=image([('Alice: hello',25)])
        e.detect(frame,0,0);e.detect(frame,0,0)
        self.assertEqual(r.recoveries,1)
    def test_three_coloured_backgrounds_produce_three_ink_rows(self):
        f=np.full((100,600,3),20,dtype=np.uint8)
        for (y,col) in [(0,(190,210,60)),(32,(34,194,247)),(64,(184,160,227))]:
            f[y:y+31]=col
            cv2.putText(f,'Alice: hello',(8,y+23),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1,cv2.LINE_AA)
        rows,_=ink_rows(f)
        self.assertEqual(len(rows),3)


class ClassificationTests(unittest.TestCase):
    def test_clipped_channel_badge_is_not_an_invented_nickname(self):
        self.assertIsNone(parse_chat_line('cHos : S> Korean Fan 64 ATK, PMO'))
        self.assertIsNotNone(parse_chat_line('CH9Player : S> GFA 60%'))
    def test_megaphone_in_wide_selection_does_not_become_normal(self):
        f=np.full((80,1600,3),25,dtype=np.uint8);f[8:39,:600]=(184,160,227)
        cv2.putText(f,'Alice: S> 10m',(8,29),cv2.FONT_HERSHEY_SIMPLEX,.6,(5,5,5),1)
        self.assertEqual(row_appearance(f,(8,12,220,20),(0,0),'S> 10m')['kind'],'super')
    def test_channel_badge_is_never_unlabelled_general(self):
        f=np.full((50,600,3),25,dtype=np.uint8)
        out=classified_chat_rows([Line('Alice CH09 : S> 10m',.95,(8,8,300,20))],f,0,0)
        self.assertEqual(out[0]['kind'],'unknown')
    def test_body_channel_mention_does_not_fake_a_megaphone(self):
        f=np.full((50,600,3),25,dtype=np.uint8)
        out=classified_chat_rows([Line('Alice: meet at CH09',.95,(8,8,300,20))],f,0,0)
        self.assertEqual(out[0]['kind'],'normal')
    def test_red_system_acquisition_notice_is_excluded(self):
        f=np.full((55,700,3),(45,70,160),dtype=np.uint8)
        lines=[Line('Nikc obtained [Splash Choco Girl] from the Aurora Mystery Fashion Crate! Con',.97,(1,2,690,18)),Line('grats!',.96,(34,25,70,18))]
        self.assertEqual(classified_chat_rows(lines,f,0,0),[])
    def test_red_player_chat_is_kept(self):
        f=np.full((45,700,3),(45,70,160),dtype=np.uint8)
        out=classified_chat_rows([Line('Alice: S> GFA 60% 2m',.96,(5,5,300,18))],f,0,0)
        self.assertEqual(out[0]['nickname'],'Alice')
        self.assertNotEqual(out[0]['kind'],'normal')
    def test_continuation_does_not_cross_background_type(self):
        lines=[Line('Alice: S> item',.96,(5,5,200,16)),Line('unrelated text',.95,(8,24,220,16))]
        rows=merge_chat_ocr(lines,lambda rect: 'pink' if rect[1]<20 else 'none')
        self.assertEqual(rows[0]['body'],'S> item')


class AdmissionTests(unittest.TestCase):
    def row(self,body='hello',kind='normal'):
        return {'nickname':'Alice','body':body,'kind':kind,'confidence':.96,'rect':(5,5,200,18)}
    def test_one_frame_fragment_is_not_emitted(self):
        gate=RowAdmission()
        self.assertEqual(gate.filter([self.row()],1),[])
    def test_two_independent_frames_confirm_general(self):
        gate=RowAdmission();gate.filter([self.row()],1)
        out=gate.filter([self.row()],1.2)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['first_observed_at'],1)
    def test_megaphones_are_immediate(self):
        self.assertEqual(len(RowAdmission().filter([self.row(kind='super')],1)),1)
    def test_new_general_chat_never_inherits_old_megaphone_by_matching_text(self):
        g=RowAdmission();g.filter([self.row(kind='super')],1)
        row=self.row();g.filter([row],1.2)
        self.assertEqual(row['kind'],'normal')
    def test_identical_messages_at_two_positions_survive(self):
        g=RowAdmission();g.filter([self.row(),self.row()],1)
        self.assertEqual(len(g.filter([self.row(),self.row()],1.2)),2)
    def test_low_confidence_is_not_confirmed_as_real_general(self):
        g=RowAdmission();row=self.row();row['confidence']=.44
        g.filter([row],1)
        self.assertEqual(g.filter([row],1.2),[])
    def test_changed_price_remains_new(self):
        t=ChatFrameTracker()
        t.new([self.row('S> item 10m')])
        self.assertEqual(len(t.new([self.row('S> item 11m')])),1)
    def test_ocr_punctuation_drift_does_not_replay_old_history(self):
        t=ChatFrameTracker();t.new([self.row('hello everyone, welcome')])
        self.assertEqual(t.new([self.row('hello everyone. welcome')]),[])


class SlangAndBatchTests(unittest.TestCase):
    def test_known_slang_avoids_neural_model(self):
        tr=Translator()
        with patch('kain_maple_translator.translation.translate_generic_many',side_effect=AssertionError('AI called')):
            self.assertEqual(tr.translate_fast('lfm 2 kpq'),'커닝 파퀘 2명 구해요')
            self.assertEqual(tr.translate_fast('brb 3 mins'),'3분 정도 자리 비울게')
            self.assertEqual(tr.translate_fast('cc ch20 pls'),'20채널로 옮겨주세요')
    def test_general_slang_expands_in_sentence(self):
        self.assertEqual(expand_shorthand('idk where u r rn'),'I do not know where you are right now')
    def test_prices_items_and_urls_are_not_fuzzy_rewritten(self):
        for text in ['S> [Rn Sword] 2.5m OBO','https://example.com/rn','GFA 60% 2m','[Any1 Hat]']:
            self.assertEqual(expand_shorthand(text),text)
    def test_obo_and_price_are_both_translated_without_model(self):
        result=Translator().translate_fast('S> GFA 60% 2m OBO')
        self.assertIn('200만',result)
        self.assertIn('가격 협의 가능',result)
        self.assertIn('60%',result)
    def test_neural_batch_is_actually_multiple_messages(self):
        tr=Translator();calls=[]
        def fake(texts,pair):
            calls.append(list(texts));return ['그 문장을 알아들었어요']*len(texts)
        with patch('kain_maple_translator.translation.translate_generic_many',side_effect=fake):
            out=tr.translate_many(['The lantern fell over yesterday','The goblin stole my lunch'],'en-ko')
        self.assertEqual(len(out),2)
        self.assertEqual(len(calls[0]),2)


class QueueTests(unittest.TestCase):
    def test_burst_over_twelve_keeps_every_sender(self):
        started=threading.Event();release=threading.Event();done=threading.Event()
        output=[]
        class Engine:
            def translate_many(self,texts,pair):
                started.set();release.wait(2)
                return ['번역 '+text for text in texts]
        def emit(row):
            output.append(row)
            if len(output)==41:done.set()
        queue=TranslationQueue(Engine(),emit,lambda error:None)
        try:
            queue.submit('same text',{'nickname':'first'})
            self.assertTrue(started.wait(1))
            queue.submit('same text',{'nickname':'second'})
            for i in range(39):queue.submit('message '+str(i),{'nickname':str(i)})
            release.set();self.assertTrue(done.wait(3))
            self.assertEqual(len(output),41)
            self.assertEqual({x['nickname'] for x in output},{'first','second'}|{str(i) for i in range(39)})
        finally:release.set();queue.close()
    def test_a_failed_batch_does_not_erase_other_messages(self):
        done=threading.Event();out=[]
        class Engine:
            def translate_many(self,*args):raise RuntimeError('broken batch')
            def translate(self,text,pair):return '개별 복구'
        q=TranslationQueue(Engine(),lambda row:(out.append(row),done.set()),lambda err:None)
        try:
            q.submit('test',{'nickname':'first'})
            self.assertTrue(done.wait(1));self.assertEqual(out[0]['translated'],'개별 복구')
        finally:q.close()
    def test_queue_overload_is_explicit_with_original_text(self):
        started=threading.Event();release=threading.Event();out=[]
        class Engine:
            def translate_many(self,texts,pair):
                started.set();release.wait(2);return ['번역']*len(texts)
        q=TranslationQueue(Engine(),out.append,lambda err:None,max_pending=1)
        try:
            q.submit('first',{});self.assertTrue(started.wait(1))
            q.submit('second',{})
            self.assertIn('second',out[0]['translated']);self.assertTrue(out[0]['translation_error'])
        finally:release.set();q.close()
    def test_capture_overflow_is_counted_and_preserves_recent_frame(self):
        stream=ChatCaptureStream(lambda:{},lambda err:None,capacity=1)
        a=CapturedChat(np.zeros((5,5,3),dtype=np.uint8),{},1)
        b=CapturedChat(a.image,{},2)
        stream.publish(a);stream.publish(b)
        self.assertEqual(stream.overflows,1)
        self.assertEqual(stream.get().captured_at,2)
    def test_capture_capacity_shrink_does_not_stop_capture(self):
        stream=ChatCaptureStream(lambda:{},lambda err:None,capacity=4)
        for i in range(4):stream.publish(CapturedChat(np.zeros((5,5,3),dtype=np.uint8),{},i))
        stream.frames.maxsize=1
        stream.publish(CapturedChat(np.zeros((5,5,3),dtype=np.uint8),{},5))
        self.assertEqual(stream.get().captured_at,5)
        self.assertEqual(stream.overflows,4)


if __name__=='__main__':unittest.main()
