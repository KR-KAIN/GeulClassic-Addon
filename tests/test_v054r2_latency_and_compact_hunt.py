"""R2 regression: bounded live-chat latency and meso-free compact tracker."""
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from kain_maple_translator.capture_stream import ChatCaptureStream, CapturedChat
from kain_maple_translator.translation_queue import TranslationQueue
from kain_maple_translator import translation

ROOT = Path(__file__).resolve().parents[1]


class BacklogRecoveryTests(unittest.TestCase):
    def frame(self, value):
        return CapturedChat(np.full((8, 32, 3), value, dtype='uint8'),
                            {'left': 0, 'top': 0, 'width': 32, 'height': 8},
                            time.monotonic(), changed=True)

    def test_default_capacity_preserves_a_bounded_burst(self):
        s = ChatCaptureStream(lambda: {}, lambda message: None)
        self.assertEqual(s.max_frames, 48)

    def test_busy_stream_skips_obsolete_frames_but_keeps_five_recent_events(self):
        # R11 live capture is loss-aware; retain the explicit legacy mode's
        # old behaviour for comparison and external replay callers.
        s = ChatCaptureStream(lambda: {}, lambda message: None,max_age_s=60.)
        for i in range(11):
            s.publish(self.frame(i))
        obtained = [s.get().image[0,0,0] for _ in range(5)]
        self.assertEqual(obtained, [6,7,8,9,10])
        self.assertEqual(s.stale_drops, 6)
        self.assertEqual(s.overflows, 0)

    def test_sparse_stream_still_preserves_every_frame(self):
        s = ChatCaptureStream(lambda: {}, lambda message: None)
        for i in range(4): s.publish(self.frame(i))
        self.assertEqual([s.get().image[0,0,0] for _ in range(4)], list(range(4)))
        self.assertEqual(s.stale_drops, 0)


class FastTranslationQueueTests(unittest.TestCase):
    def test_batch_size_eight_and_dequeue_delay_are_measured(self):
        outputs=[]
        entered=threading.Event()
        release=threading.Event()
        batches=[]
        class ControlledTranslator:
            def translate_many(self, keys, direction):
                batches.append(list(keys))
                entered.set()
                if len(batches)==1: release.wait(3)
                return ['번역:'+v for v in keys]
        q=TranslationQueue(ControlledTranslator(), outputs.append, lambda msg: None)
        try:
            self.assertTrue(q.submit('first', {'tag': 0}))
            self.assertTrue(entered.wait(2))
            for i in range(9):q.submit(f'message-{i}', {'tag': i+1})
            release.set()
            deadline=time.monotonic()+5
            while len(outputs)<10 and time.monotonic()<deadline: time.sleep(.01)
            self.assertEqual(len(outputs), 10)
            # R12: one CTranslate2 batch holds up to 8 waiting messages.
            self.assertEqual([len(b) for b in batches], [1,8,1])
            self.assertTrue(all('translation_wait_ms' in o for o in outputs))
        finally:
            release.set()
            q.close()

    def test_incoming_warmup_does_not_stage_unused_reverse_direction(self):
        called=[]
        with patch.object(translation,'prepare_models',side_effect=called.append), \
             patch.object(translation,'translate_generic_many',return_value=['ok']), \
             patch.dict(translation._ENGINE_STATE,{'en-ko':{}},clear=True):
            translation.warmup_models(directions=('en-ko',))
        self.assertEqual(called, [('en-ko',)])


class CompactWidgetContractTests(unittest.TestCase):
    def test_legacy_meso_read_is_disabled_without_breaking_potions(self):
        panel=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        aux=(ROOT/'kain_maple_translator/hunt_aux.py').read_text('utf-8')
        self.assertIn('NATIVE_W=248;NATIVE_H=122',panel)  # R15: compact classic stat-window skin
        self.assertNotIn("metric('메소 증감'", panel)
        self.assertNotIn('self.meso_label',panel)
        self.assertNotIn('read_meso(', aux)
        self.assertIn('read_potion_amounts(recognizer,selected)',aux)
        self.assertIn("('Ctrl','Del','End','PgDn')",panel)


if __name__ == '__main__': unittest.main()
