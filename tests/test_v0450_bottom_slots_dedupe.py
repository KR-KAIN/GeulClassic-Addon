"""v0.4.50: four bottom slots + full-frame physical-message deduplication."""
import unittest
from pathlib import Path
import cv2
from kain_maple_translator.visual_message_ledger import FrameMessageLedger
from kain_maple_translator.hunt_capture import potion_crops,icon_snapshot,locate_keyboard
from kain_maple_translator.hunt_aux import SlotCountGate

ROOT=Path(__file__).resolve().parents[1]


def row(body, y=20, nick='User', kind='normal', confidence=.96):
    return {'nickname':nick,'body':body,'rect':(0,y,240,17),'kind':kind,
            'confidence':confidence,'source_white_body':kind=='normal'}

class BottomSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame=cv2.imread(str(ROOT/'tests/fixtures/hunt-keyboard-real.png'))
        assert cls.frame is not None
        cls.rect=locate_keyboard(cls.frame)
        assert cls.rect is not None
    def test_only_four_bottom_keys(self):
        self.assertEqual(list(potion_crops(self.frame,self.rect)),['Ctrl','Del','End','PgDn'])
        self.assertEqual(len(potion_crops(self.frame,self.rect,all_slots=True)),12)
    def test_all_icons_are_uncropped_and_rgba(self):
        for key,crop in potion_crops(self.frame,self.rect).items():
            pic=icon_snapshot(crop)
            self.assertIsNotNone(pic,key)
            self.assertEqual(pic.shape[2],4,key)
            self.assertGreater(pic.shape[1],round(crop.shape[1]*.65),key)
            self.assertGreater(pic.shape[0],round(crop.shape[0]*.65),key)
            self.assertTrue((pic[:,:,3]==0).any(),key)
    def test_display_current_count_not_spent(self):
        source=(ROOT/'kain_maple_translator/hunt_widget.py').read_text('utf-8')
        self.assertIn("label=f'{record.last_count:,}'",source)
        self.assertNotIn("label=f'{key} {record.spent}개'",source)
        self.assertIn("('Ctrl','Del','End','PgDn')",source)
    def test_aux_uses_only_bottom_four(self):
        source=(ROOT/'kain_maple_translator/hunt_aux.py').read_text('utf-8')
        self.assertIn('potion_crops(frame,keyboard).items()',source)
        self.assertIn('pending_counts',source)

class MessageIdentityTests(unittest.TestCase):
    def test_stationary_chat_does_not_repeat_after_many_seconds(self):
        d=FrameMessageLedger()
        a=[row('Buying 60% scroll 2m',40)]
        self.assertEqual(d.filter(a,a,0),a)
        for t in [0.15,.5,2.,7.,12.]:
            b=[row('Buying 60% scroll 2m',40)]
            self.assertEqual(d.filter(b,b,t),[])
    def test_scroll_one_line_only_new_bottom(self):
        d=FrameMessageLedger()
        a=[row('A',20),row('B',40),row('C',60)]
        d.filter(a,a,1.)
        b=[row('B',20),row('C',40),row('D',60)]
        self.assertEqual([r['body'] for r in d.filter(b,b,1.15)],['D'])
    def test_burst_three_lines(self):
        d=FrameMessageLedger()
        a=[row('A',20),row('B',40),row('C',60),row('D',80)]
        d.filter(a,a,1)
        b=[row('D',20),row('E',40),row('F',60),row('G',80)]
        self.assertEqual([r['body'] for r in d.filter(b,b,1.5)],['E','F','G'])
    def test_same_text_reposted_on_new_bottom_slot(self):
        d=FrameMessageLedger()
        a=[row('S> GFA 60% 3m',40),row('kk',60)]
        d.filter(a,a,1)
        b=[row('kk',40),row('S> GFA 60% 3m',60)]
        self.assertEqual([r['body'] for r in d.filter(b,b,1.1)],['S> GFA 60% 3m'])
    def test_same_text_two_simultaneous_instances(self):
        d=FrameMessageLedger()
        a=[row('ㅋㅋㅋ',20)]
        d.filter(a,a,1)
        b=[row('ㅋㅋㅋ',20),row('ㅋㅋㅋ',40)]
        self.assertEqual([r['body'] for r in d.filter(b,b,1.25)],['ㅋㅋㅋ'])
    def test_ocr_one_frame_gap_not_rebroadcast(self):
        d=FrameMessageLedger()
        a=[row('same text',20),row('another line',40)]
        d.filter(a,a,1)
        self.assertEqual(d.filter([],[],1.1),[])
        b=[row('same text',20),row('another line',40)]
        self.assertEqual(d.filter(b,b,1.4),[])
    def test_partial_ocr_dropout_not_rebroadcast(self):
        d=FrameMessageLedger()
        a=[row('a',20),row('b',40),row('c',60)]
        d.filter(a,a,1)
        b=[row('b',40)]
        self.assertEqual(d.filter(b,b,1.2),[])
        c=[row('a',20),row('b',40),row('c',60)]
        self.assertEqual(d.filter(c,c,1.4),[])
    def test_pending_ocr_admitted_on_later_frame_once(self):
        d=FrameMessageLedger()
        a=[row('WTS 1m',20)]
        self.assertEqual(d.filter([],a,1.0),[])
        b=[row('WTS 1m',20)]
        self.assertEqual(d.filter(b,b,1.2),b)
        c=[row('WTS 1m',20)]
        self.assertEqual(d.filter(c,c,1.4),[])
    def test_classification_flip_preserves_identity(self):
        d=FrameMessageLedger()
        a=[row('S> item 1m',20,kind='megaphone')]
        d.filter(a,a,1)
        b=[row('S> item 1m',20,kind='normal')]
        self.assertEqual(d.filter(b,b,1.2),[])
    def test_ocr_one_glyph_drifts_not_retranslate(self):
        d=FrameMessageLedger()
        a=[row('Selling white scroll 5m',20)]
        d.filter(a,a,1)
        b=[row('Selling white scrolI 5m',20)]
        self.assertEqual(d.filter(b,b,1.2),[])
    def test_changed_price_is_a_new_message(self):
        d=FrameMessageLedger()
        a=[row('Selling scroll 5m',20)]
        d.filter(a,a,1)
        b=[row('Selling scroll 6m',20)]
        self.assertEqual(d.filter(b,b,1.3),b)
    def test_duplicate_megaphone_repeated_frames_suppressed(self):
        d=FrameMessageLedger()
        for i in range(8):
            r=[row('전신갑옷 ARMOR 행운 60 300K 팝니다',20,kind='megaphone')]
            result=d.filter(r,r,i*.5)
            self.assertEqual(len(result),1 if i==0 else 0)
    def test_worker_uses_full_visible_message_ledger(self):
        source=(ROOT/'kain_maple_translator/worker.py').read_text('utf-8')
        self.assertIn('visual_ledger.filter(admitted, rows, captured.captured_at)',source)

if __name__=='__main__':unittest.main()
