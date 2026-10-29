"""R11: unique-frame preservation, translucent chat, paired OCR, row recovery."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from kain_maple_translator.capture_stream import ChatCaptureStream, CapturedChat, covered_middle_frame
from kain_maple_translator.source_palette import white_body_ink
from kain_maple_translator.row_admission import RowAdmission
from kain_maple_translator.ocr_recall import merge_recovery_lines, same_read, cache_ttl
from kain_maple_translator.vision import Line
from kain_maple_translator.core import merge_chat_ocr
from kain_maple_translator.fast_vision import IncrementalChatOCR, InkRow


def frame(n, keys=(), width=100, hwnd=3):
    return CapturedChat(np.full((30,width,3),n,np.uint8),
                        dict(left=0,top=0,width=width,height=30),float(n),
                        window_hwnd=hwnd,row_signature=tuple(keys))


class CaptureRecallTests(unittest.TestCase):
    def test_old_unique_burst_is_not_expired(self):
        stream=ChatCaptureStream(lambda:{},lambda _:None)
        for n in range(30):stream.publish(frame(n))
        with patch('time.monotonic',return_value=1000.):
            got=[int(stream.get(timeout=0).image[0,0,0]) for _ in range(30)]
        self.assertEqual(got,list(range(30)))
        self.assertEqual(stream.expired_drops+stream.stale_drops,0)

    def test_covered_scrolling_middle_can_be_compacted(self):
        self.assertTrue(covered_middle_frame(frame(0,'abcd'),frame(1,'bcde'),frame(2,'cdef')))

    def test_one_frame_only_message_must_survive(self):
        self.assertFalse(covered_middle_frame(frame(0,'abcd'),frame(1,'bcXe'),frame(2,'cdef')))

    def test_no_overlap_does_not_prove_coverage(self):
        self.assertFalse(covered_middle_frame(frame(0,'abcd'),frame(1,'efgh'),frame(2,'ijkl')))

    def test_repeated_ink_is_ambiguous(self):
        self.assertFalse(covered_middle_frame(frame(0,'aabc'),frame(1,'abcd'),frame(2,'bcde')))

    def test_unknown_segmentation_keeps_frame(self):
        self.assertFalse(covered_middle_frame(frame(0),frame(1,'abcd'),frame(2,'bcde')))

    def test_other_window_keeps_frame(self):
        self.assertFalse(covered_middle_frame(frame(0,'abcd'),frame(1,'bcde'),frame(2,'cdef',hwnd=4)))

    def test_other_dimensions_keep_frame(self):
        self.assertFalse(covered_middle_frame(frame(0,'abcd'),frame(1,'bcde'),frame(2,'cdef',width=120)))

    def test_compacted_burst_retains_every_unique_row_in_order(self):
        stream=ChatCaptureStream(lambda:{},lambda _:None)
        for n in range(30):stream.publish(frame(n,range(n,n+4)))
        all_keys=[];times=[]
        while not stream.frames.empty():
            item=stream.get(timeout=0);all_keys.extend(item.row_signature);times.append(item.captured_at)
        self.assertEqual(set(all_keys),set(range(33)))
        self.assertEqual(times,sorted(times))
        self.assertGreater(stream.covered_frames,15)
        self.assertEqual(stream.overflows,0)

    def test_true_capacity_overflow_still_reports(self):
        stream=ChatCaptureStream(lambda:{},lambda _:None,capacity=2)
        for n in range(3):stream.publish(frame(n))
        self.assertEqual(stream.overflows,1)

    def test_confirmation_does_not_evict_change(self):
        stream=ChatCaptureStream(lambda:{},lambda _:None,capacity=1)
        stream.publish(frame(1));refresh=frame(2);refresh.changed=False
        self.assertFalse(stream.publish(refresh))
        self.assertEqual(stream.get(timeout=0).captured_at,1.)


class TranslucentWhiteTests(unittest.TestCase):
    def test_white_over_brown_scene(self):
        self.assertTrue(white_body_ink([165,178,195],[35,57,85]))

    def test_generated_alpha_white_over_multiple_backgrounds(self):
        for bg in ([20,20,20],[30,50,90],[90,30,20],[20,80,50]):
            for alpha in (.55,.65,.8):
                with self.subTest(bg=bg,alpha=alpha):
                    bg=np.array(bg);color=alpha*255+(1-alpha)*bg
                    self.assertTrue(white_body_ink(color,bg))

    def test_coloured_ink_stays_coloured(self):
        for fg in ([30,220,240],[230,80,160],[240,110,30],[40,210,50]):
            self.assertFalse(white_body_ink(fg,[25,25,25]))

    def test_coloured_band_has_no_alpha_white_shortcut(self):
        self.assertFalse(white_body_ink([165,178,195],[35,57,85],'#553923'))

    def test_bright_background_and_low_contrast_do_not_pass(self):
        self.assertFalse(white_body_ink([160,170,180],[150,160,170]))
        self.assertFalse(white_body_ink([90,100,110],[35,57,85]))

    def test_original_opaque_white_passes(self):
        self.assertTrue(white_body_ink([230,230,230],[25,25,25]))


def chat(confidence=.88,paired=True,white=True,body='need help please'):
    return dict(nickname='Alice',body=body,kind='normal',confidence=confidence,
                rect=(0,0,200,20),source_white_body=white,source_meta={'paired_read':paired})


class PairedAdmissionTests(unittest.TestCase):
    def test_agreeing_preprocessings_admit_same_frame(self):
        self.assertEqual(len(RowAdmission().filter([chat()],1.)),1)

    def test_unconfirmed_read_still_waits(self):
        self.assertEqual(RowAdmission().filter([chat(paired=False)],1.),[])

    def test_weak_agreement_still_waits(self):
        self.assertEqual(RowAdmission().filter([chat(confidence=.7)],1.),[])

    def test_no_white_evidence_still_waits(self):
        self.assertEqual(RowAdmission().filter([chat(white=False)],1.),[])

    def test_short_reply_can_use_pair(self):
        self.assertEqual(len(RowAdmission().filter([chat(body='hi')],1.)),1)

    def test_prices_case_and_direction_must_agree(self):
        self.assertTrue(same_read('Alice:  hi','Alice: hi'))
        for a,b in [('S> 10k','S> 100k'),('S> 10k','B> 10k'),('Nick: hi','Niek: hi')]:
            self.assertFalse(same_read(a,b))

    def test_merged_fragment_cannot_inherit_other_fragment_confirmation(self):
        out=merge_chat_ocr([Line('Alice:',.9,(0,0,45,20),source_meta={'paired_read':True}),
                            Line('need help',.9,(50,0,140,20))])
        self.assertFalse(out[0]['source_meta']['paired_read'])


class RecoveryPreservationTests(unittest.TestCase):
    def line(self,text,confidence=.95,y=0):return Line(text,confidence,(0,y,200,18),ink_key='primary')

    def test_partial_detector_does_not_erase_good_other_rows(self):
        good=self.line('Alice: hello');bad=self.line('garbled',.4,25)
        recovered=self.line('Bob: buying potions',.98,25)
        self.assertEqual(merge_recovery_lines([good,bad],[recovered]),[good,recovered])

    def test_equivalent_recovery_keeps_primary_metadata(self):
        good=self.line('Alice: S> 100k',.94)
        self.assertIs(merge_recovery_lines([good],[self.line(good.text,.99)])[0],good)

    def test_numeric_recovery_keeps_legacy_detector_choice(self):
        primary=self.line('Alice: S> 10k',.97)
        recovered=self.line('Alice: S> 100k',.98)
        self.assertEqual(merge_recovery_lines([primary],[recovered]),[recovered])

    def test_unrelated_detector_row_is_added(self):
        first=self.line('Alice: hello');second=self.line('Bob: hi',.95,25)
        self.assertEqual(merge_recovery_lines([first],[second]),[first,second])

    def test_weaker_recovery_cannot_replace_good_line(self):
        good=self.line('Alice: hello')
        self.assertEqual(merge_recovery_lines([good],[self.line('Alice: he',.6)]),[good])

    def test_fragmented_recovery_replaces_one_weak_baseline_once(self):
        fragments=[Line('Bob:',.99,(0,0,40,18)),Line('hello',.99,(45,0,100,18))]
        out=merge_recovery_lines([self.line('garbled',.4)],fragments)
        self.assertEqual(len(out),2)
        self.assertEqual(len(merge_chat_ocr(out)),1)

    def test_empty_recovery_retains_input(self):
        lines=[self.line('Alice: hi')]
        self.assertEqual(merge_recovery_lines(lines,[]),lines)


class StableCacheTests(unittest.TestCase):
    def test_two_matching_high_confidence_reads_reuse_longer(self):
        self.assertEqual(cache_ttl('Alice: hello',.96,2),30.)
        self.assertEqual(cache_ttl('Alice: hello',.96,1),2.5)

    def test_medium_confidence_confirmation_reuses_boundedly(self):
        self.assertEqual(cache_ttl('Alice: hello',.86,2),8.)

    def test_weak_and_empty_results_still_retry(self):
        self.assertLess(cache_ttl('',.0,5),.3)
        self.assertLess(cache_ttl('Alice: uncertain',.5,5),.3)

    def test_corrupt_item_does_not_get_long_reuse(self):
        self.assertLess(cache_ttl('Alice: S> [ ] 100k',.99,3),8.)


class ActualPipelineContracts(unittest.TestCase):
    def make(self, texts=('Alice: need help',), score=.88):
        self.now=0.;self.calls=0;self.detectors=0
        def recognize(images):
            text=texts[min(self.calls,len(texts)-1)];self.calls+=1
            return SimpleNamespace(txts=[text]*len(images),scores=[score]*len(images),word_results=[])
        def detect(*args):
            self.detectors+=1;return []
        reader=SimpleNamespace(ocr=SimpleNamespace(recognize_txt=recognize),detect=detect)
        engine=IncrementalChatOCR(reader,clock=lambda:self.now)
        engine.badges=SimpleNamespace(split=lambda *a:None,split_plain=lambda *a:None,locate_rows=lambda *a:[])
        original=np.full((18,220,3),30,np.uint8)
        neutral=np.full_like(original,255);neutral[4:12,10:150]=0
        original[4:12,10:150]=220
        row=InkRow((0,0,220,18),original,neutral,b'unique-row')
        return engine,row

    def test_actual_two_preprocessing_results_propagate_confirmation(self):
        engine,row=self.make()
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry',return_value=([row],False,0)):
            lines=engine.detect(row.original,0,0)
        self.assertEqual(self.calls,2)
        self.assertTrue(lines[0].source_meta['paired_read'])
        rows=merge_chat_ocr(lines);rows[0]['source_white_body']=True
        self.assertEqual(len(RowAdmission().filter(rows,1.)),1)

    def test_disagreeing_two_views_do_not_confirm(self):
        engine,row=self.make(('Alice: need help','Alice: need potion'))
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry',return_value=([row],False,0)):
            lines=engine.detect(row.original,0,0)
        self.assertFalse(lines[0].source_meta['paired_read'])

    def test_confirmed_pixel_cache_skips_model_but_changed_ink_does_not(self):
        engine,row=self.make(score=.96)
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry',return_value=([row],False,0)):
            engine.detect(row.original,0,0);self.now=3.
            engine.detect(row.original,0,0);calls=self.calls;self.now=6.
            engine.detect(row.original,0,0)
            self.assertEqual(self.calls,calls)
        # A real price change alters glyph pixels (here: one more digit).
        neutral=row.neutral.copy();neutral[4:12,160:166]=0
        changed=InkRow(row.rect,row.original,neutral,b'changed-price')
        self.now=7.
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry',return_value=([changed],False,0)):
            engine.detect(row.original,0,0)
        self.assertGreater(self.calls,calls)

    def test_readable_border_rescue_does_not_repeat_full_detection(self):
        engine,row=self.make(score=.96)
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry',return_value=([row],True,1)):
            engine.detect(row.original,0,0)
        self.assertEqual(self.detectors,0)

    def test_numeric_border_rescue_retains_detector_verification(self):
        engine,row=self.make(('Alice: B> scroll 100k',),score=.96)
        with patch('kain_maple_translator.fast_vision.ink_rows_border_retry',return_value=([row],True,1)):
            engine.detect(row.original,0,0)
        self.assertEqual(self.detectors,1)


if __name__=='__main__':unittest.main()
