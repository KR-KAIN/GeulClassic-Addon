"""Real-time WGC/MSS event transport, OCR admission, recovery regressions."""
import unittest
from unittest.mock import patch
import numpy as np
from kain_maple_translator.capture_stream import CapturedChat,ChatCaptureStream
from kain_maple_translator.row_admission import RowAdmission
from kain_maple_translator.core import ChatFrameTracker

class StreamTests(unittest.TestCase):
    def frame(self,n,changed=True):
        return CapturedChat(np.zeros((12,50,3),np.uint8),
                            dict(left=0,top=0,width=50,height=12),float(n),0,changed)
    def test_pending_change_not_delayed_by_periodic_refresh(self):
        s=ChatCaptureStream(lambda:{},lambda e:None,capacity=4)
        self.assertTrue(s.publish(self.frame(1,True)))
        self.assertFalse(s.publish(self.frame(1.1,False)))
        self.assertTrue(s.publish(self.frame(2,True)))
        self.assertEqual([s.get().captured_at for _ in range(2)],[1.,2.])
        self.assertEqual(s.skipped_refreshes,1)
    def test_idle_refresh_still_confirms_a_faint_line(self):
        s=ChatCaptureStream(lambda:{},lambda e:None,capacity=4)
        self.assertTrue(s.publish(self.frame(1,False)))
        self.assertEqual(s.get().captured_at,1.)
    def test_unchanged_pending_refresh_is_never_evicted_for_another(self):
        s=ChatCaptureStream(lambda:{},lambda e:None,capacity=2)
        s.publish(self.frame(1,False))
        self.assertFalse(s.publish(self.frame(2,False)))
        self.assertEqual(s.overflows,0)
    def test_backlogged_changes_preserve_chronology(self):
        s=ChatCaptureStream(lambda:{},lambda e:None,capacity=5)
        for n in (1,2,3,4):self.assertTrue(s.publish(self.frame(n,True)))
        self.assertEqual([s.get().captured_at for _ in range(4)],[1.,2.,3.,4.])

class AdmissionTests(unittest.TestCase):
    def row(self,body='S> 60% scroll 2m',score=.89,white=True):
        return dict(nickname='Maple',body=body,kind='normal',
                    confidence=score,source_white_body=white,rect=(4,8,240,15))
    def test_verified_trade_survives_one_frame(self):
        self.assertEqual(len(RowAdmission().filter([self.row()],1.)),1)
    def test_ambiguous_white_chat_waits_for_confirmation(self):
        self.assertEqual(RowAdmission().filter([self.row('I think so',.89)],1.),[])
    def test_low_confidence_trade_waits_for_second_frame(self):
        self.assertEqual(RowAdmission().filter([self.row(score=.60)],1.),[])
    def test_coloured_chat_cannot_gain_fast_white_admission(self):
        self.assertEqual(RowAdmission().filter([self.row(white=False)],1.),[])
    def test_repeated_trade_without_screen_change_not_duplicated(self):
        gate=RowAdmission();tracker=ChatFrameTracker();row=self.row()
        self.assertEqual(len(tracker.new(gate.filter([row],1.))),1)
        self.assertEqual(tracker.new(gate.filter([row],1.15)),[])
    def test_new_trade_on_bottom_is_preserved(self):
        gate=RowAdmission();tracker=ChatFrameTracker()
        a=self.row('S> glove 2m');b=self.row('S> GFA 60% 5m')
        self.assertEqual(len(tracker.new(gate.filter([a],1.))),1)
        self.assertEqual(len(tracker.new(gate.filter([a,b],1.1))),1)

if __name__=='__main__':unittest.main()
