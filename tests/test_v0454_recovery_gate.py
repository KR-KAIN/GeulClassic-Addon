"""Detector gate safety and metadata-only diagnostics regression tests."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from kain_maple_translator.fast_vision import (
    IncrementalChatOCR, InkRow, RecoveryGate, ink_recovery_key,
)
from kain_maple_translator.vision import Line
from scripts.summarize_ocr_trace import summarize


class Clock:
    def __init__(self):
        self.value=100.0
    def __call__(self):
        self.value+=0.0001
        return self.value
    def advance(self,seconds):
        self.value+=seconds


class Reader:
    def __init__(self, lines=None):
        self.ocr=self
        self.calls=0
        self.lines=lines or []
    def detect(self,*args):
        self.calls+=1
        return list(self.lines)
    def recognize_txt(self,images):
        return SimpleNamespace(txts=['Nick: hi']*len(images),scores=[.99]*len(images))


class GateUnitTests(unittest.TestCase):
    def test_failed_backoff_and_duty_after_completion(self):
        gate=RecoveryGate()
        key=b'same'
        self.assertEqual(gate.block_reason(key,100,True),'')
        gate.record(key, [],100,101,True)
        self.assertEqual(gate.block_reason(key,102,True),'global_duty')
        self.assertEqual(gate.block_reason(key,103.2,True),'')
        gate.record(key, [],104,104.5,True)
        self.assertEqual(gate.block_reason(key,105.6,True),'failed_backoff')
        self.assertEqual(gate.block_reason(key,106.51,True),'')
        gate.record(key, [],107,107.2,True)
        self.assertEqual(gate.block_reason(key,110,True),'failed_backoff')
        self.assertEqual(gate.block_reason(key,115.3,True),'')
        self.assertEqual(gate.items[key]['fails'],3)

    def test_lru_bounded_and_success_resets_failures(self):
        gate=RecoveryGate(max_items=2)
        for k in (b'a',b'b',b'c'):
            gate.record(k,[],1.,1.1,True)
        self.assertNotIn(b'a',gate.items)
        gate.record(b'b',[('read',.9,(1,1,20,16))],2.,2.3,True)
        self.assertEqual(gate.items[b'b']['fails'],0)
        self.assertEqual(gate.items[b'b']['rows'][0][0],'read')

    def test_foreground_key_ignores_background_when_neutral_is_stable(self):
        neutral=np.full((23,96,3),255,np.uint8)
        neutral[8:13,10:76]=0
        row_a=InkRow((6,7,96,23),np.zeros_like(neutral),neutral,b'a')
        row_b=InkRow((6,7,96,23),np.full_like(neutral,230),neutral,b'b')
        frame_a=np.full((90,540,3),17,np.uint8)
        frame_b=np.full((90,540,3),175,np.uint8)
        self.assertEqual(ink_recovery_key(frame_a,[row_a]),
                         ink_recovery_key(frame_b,[row_b]))
        # Scroll position must NOT replay stale cached coordinates.
        row_scrolled=InkRow((6,34,96,23),row_b.original,neutral,b'c')
        self.assertNotEqual(ink_recovery_key(frame_a,[row_a]),
                            ink_recovery_key(frame_b,[row_scrolled]))


class GateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.frame=np.zeros((80,400,3),np.uint8)
        self.clock=Clock()

    def test_no_ink_is_rate_limited_and_never_replays_cached_ghost(self):
        reader=Reader([Line('Nick: once',.95,(5,5,95,16))])
        engine=IncrementalChatOCR(reader,clock=self.clock)
        with patch('kain_maple_translator.fast_vision.ink_rows',return_value=([],False)):
            first=engine.detect(self.frame,0,0)
            self.assertEqual(first[0].text,'Nick: once')
            self.assertEqual(reader.calls,1)
            self.clock.advance(.8)
            second=engine.detect(self.frame,0,0)
            self.assertEqual(second,[])
            self.assertEqual(engine.stats['recovery_gate_blocked'],1)
            self.assertEqual(engine.stats['recovery_gate_block_reason'],'no_ink_interval')
            self.assertEqual(reader.calls,1)
            self.clock.advance(5.1)
            engine.detect(self.frame,0,0)
            self.assertEqual(reader.calls,2)

    def test_one_repeated_lowconfidence_line_can_not_trigger_every_frame(self):
        reader=Reader([])
        engine=IncrementalChatOCR(reader,clock=self.clock)
        neutral=np.full((20,250,3),255,np.uint8)
        neutral[5:14,5:220]=0
        row=InkRow((5,10,250,20),neutral.copy(),neutral,b'ink-key')
        with (patch('kain_maple_translator.fast_vision.ink_rows',return_value=([row],False)),
              patch.object(engine,'_read_rows',return_value=[('@@@@',.41)])):
            engine.detect(self.frame,0,0)
            self.assertEqual(reader.calls,1)
            self.clock.advance(.15)
            engine.detect(np.full_like(self.frame,50),0,0)
            self.assertEqual(reader.calls,1)
            self.assertEqual(engine.stats['recovery_gate_blocked'],1)
            self.assertIn('lowconf',engine.stats['recovery_reasons'])
            self.clock.advance(.7)
            engine.detect(np.full_like(self.frame,60),0,0)
            self.assertEqual(reader.calls,2)
            self.clock.advance(.7)
            engine.detect(np.full_like(self.frame,70),0,0)
            self.assertEqual(reader.calls,2)  # 2-second backoff

    def test_success_recovery_cache_reuses_without_detector(self):
        reader=Reader([Line('Nick: recovered',.98,(5,7,90,18))])
        engine=IncrementalChatOCR(reader,clock=self.clock)
        neutral=np.full((20,100,3),255,np.uint8)
        neutral[5:14,9:90]=0
        row=InkRow((3,5,100,20),neutral.copy(),neutral,b'k')
        with (patch('kain_maple_translator.fast_vision.ink_rows',return_value=([row],False)),
              patch.object(engine,'_read_rows',return_value=[('@@@@',.40)])):
            first=engine.detect(self.frame,0,0)
            self.assertEqual(first[0].text,'Nick: recovered')
            self.assertEqual(reader.calls,1)
            self.clock.advance(.2)
            second=engine.detect(np.full_like(self.frame,25),0,0)
            self.assertEqual(second[0].text,'Nick: recovered')
            self.assertEqual(reader.calls,1)
            self.assertEqual(engine.stats['recovery_cache_hit'],1)

    def test_detector_exception_is_recorded_and_primary_output_kept(self):
        class BrokenReader(Reader):
            def detect(self,*args):
                self.calls+=1
                raise RuntimeError('temporary detector error')
        reader=BrokenReader()
        engine=IncrementalChatOCR(reader,clock=self.clock)
        with patch('kain_maple_translator.fast_vision.ink_rows',return_value=([],False)):
            self.assertEqual(engine.detect(self.frame,0,0),[])
        self.assertEqual(reader.calls,1)
        self.assertEqual(engine.stats['detector_recoveries'],1)
        self.assertEqual(engine.stats['recognition_errors'],1)

    def test_jsonl_worker_contains_new_gate_metadata_fields(self):
        root=Path(__file__).resolve().parents[1]
        worker=(root/'kain_maple_translator/worker.py').read_text('utf-8')
        for field in ('recovery_reasons','recovery_rows_found',
                      'recovery_gate_blocked','recovery_cache_hit',
                      'recovery_gate_block_reason'):
            self.assertIn("'"+field+"'", worker)

    def test_reason_summary_reports_calls_blocked_and_ms(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'profile.jsonl'
            source.write_text('\n'.join(json.dumps(x) for x in [
                {'schema':1,'recovery_reasons':'empty','detector_recoveries':1,
                 'recovery_rows_found':0,'stage_recovery_detector_ms':700.,'stage_total_ms':720.},
                {'schema':1,'recovery_reasons':'lowconf+uncertain','detector_recoveries':1,
                 'recovery_rows_found':1,'stage_recovery_detector_ms':500.,'stage_total_ms':550.},
                {'schema':1,'recovery_reasons':'empty','detector_recoveries':0,
                 'recovery_gate_blocked':1,'recovery_gate_block_reason':'no_ink_interval',
                 'stage_recovery_detector_ms':0.,'stage_total_ms':10.},
            ])+'\n',encoding='utf-8')
            report=summarize(source)
            self.assertIn('exact empty: requested=2, calls=1, blocked=1',report)
            self.assertIn('component lowconf: requested=1, calls=1',report)
            self.assertIn('blocks_by_gate: no_ink_interval=1',report)
            self.assertIn('detector_ms_sum=700.00',report)


if __name__=='__main__':
    unittest.main()
