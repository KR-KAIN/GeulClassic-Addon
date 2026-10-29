"""Targeted regression tests for the small-four-row-chat fast path."""
import unittest
import numpy as np
import sys
import types
from unittest.mock import patch
from kain_maple_translator.fast_vision import InkRow

from kain_maple_translator.capture_stream import ChatCaptureStream, CapturedChat
from kain_maple_translator.row_admission import RowAdmission
from kain_maple_translator.channel_guard import ChannelGuard


class SmallChatCaptureTests(unittest.TestCase):
    def frame(self, n, changed=True):
        return CapturedChat(np.zeros((8, 12, 3), dtype=np.uint8),
                            dict(left=0,top=0,width=12,height=8), n, 0, changed)

    def test_periodic_refresh_does_not_evict_new_unread_chat(self):
        stream = ChatCaptureStream(lambda:{},lambda msg:None,capacity=2)
        stream.publish(self.frame(1,True))
        stream.publish(self.frame(2,True))
        self.assertFalse(stream.publish(self.frame(3,False)))
        self.assertEqual(stream.skipped_refreshes,1)
        self.assertEqual(stream.overflows,0)
        self.assertEqual(stream.get().captured_at,1)
        self.assertEqual(stream.get().captured_at,2)

    def test_real_change_can_preempt_oldest_frame_and_counts_warning(self):
        stream = ChatCaptureStream(lambda:{},lambda msg:None,capacity=2)
        for i in range(3): stream.publish(self.frame(i,True))
        self.assertEqual(stream.overflows,1)
        self.assertEqual([stream.get().captured_at for _ in range(2)],[1,2])

    def test_animated_background_does_not_enqueue_duplicate_text(self):
        stream=ChatCaptureStream(lambda:{'enabled':{'chat':True},'regions':{
            'chat':dict(left=0,top=0,width=200,height=50)},
            'capture_interval':.035},lambda msg:None,capacity=12)
        state={'n':0}
        class Screenshotter:
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def grab(self,_region):
                state['n']+=1
                frame=np.zeros((50,200,4),dtype=np.uint8)
                frame[:,:,:3]=100+state['n']*6  # simulated moving scenery
                if state['n']>=5:stream.stop_event.set()
                return frame
        def rows(_bgr):
            neutral=np.full((12,110,3),255,dtype=np.uint8)
            neutral[:,1:7,:]=0
            if state['n']>=4: neutral[:,40:46,:]=0  # new text
            return [InkRow((2,8,110,12),neutral.copy(),neutral,b'ink')],False
        with patch.dict(sys.modules,{'mss':types.SimpleNamespace(mss=Screenshotter)}), \
             patch('kain_maple_translator.fast_vision.ink_rows',side_effect=rows):
            stream._run()
        self.assertEqual(stream.events,2)
        self.assertEqual(stream.overflows,0)
        self.assertLessEqual(stream.refreshes,1)

    def row(self,kind='normal',white=False, confidence=.96, body='shops here'):
        return dict(nickname='Neux',body=body,kind=kind,rect=(5,15,180,18),
                    confidence=confidence,source_white_body=white)

    def test_certain_white_chat_needs_only_one_frame(self):
        gate=RowAdmission()
        out=gate.filter([self.row(white=True)],1.0)
        self.assertEqual(len(out),1)

    def test_unconfirmed_generic_and_low_confidence_need_recheck(self):
        self.assertEqual(RowAdmission().filter([self.row()],1.0),[])
        self.assertEqual(RowAdmission().filter([self.row(white=True,confidence=.72)],1.0),[])
        self.assertEqual(RowAdmission().filter([self.row(white=True,body='?')],1.0),[])

    def test_switching_class_does_not_show_duplicate(self):
        g=ChannelGuard()
        self.assertTrue(g.accept(self.row(kind='normal'),1.0))
        self.assertFalse(g.accept(self.row(kind='super'),1.3))

    def test_true_repeated_message_same_kind_is_not_text_deduped(self):
        g=ChannelGuard()
        self.assertTrue(g.accept(self.row(kind='super'),1.0))
        self.assertTrue(g.accept(self.row(kind='super'),1.3))

    def test_same_body_new_offer_or_different_y_not_suppressed(self):
        g=ChannelGuard()
        self.assertTrue(g.accept(self.row(kind='normal'),1.0))
        item=self.row(kind='super');item['rect']=(5,90,180,18)
        self.assertTrue(g.accept(item,1.2))
        item=self.row(kind='normal',body='shops there')
        self.assertTrue(g.accept(item,1.3))


if __name__=='__main__': unittest.main()
