import unittest
from pathlib import Path
import cv2
import numpy as np
from types import SimpleNamespace
from kain_maple_translator.hunt_capture import (locate_keyboard,potion_crops,
    icon_snapshot,_digit_region,read_potion_amounts)
from kain_maple_translator.visual_message_ledger import FrameMessageLedger
from kain_maple_translator.hunt_aux import SlotCountGate
ROOT=Path(__file__).resolve().parents[1]

class NewRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.im=cv2.imread(str(ROOT/'tests/fixtures/hunt-keyboard-counts-user.png'))
        assert cls.im is not None
        cls.box=locate_keyboard(cls.im)
        assert cls.box is not None
        cls.slots=potion_crops(cls.im,cls.box)

    def test_four_bottom_keys_and_full_width_crops(self):
        self.assertEqual(list(self.slots),['Ctrl','Del','End','PgDn'])
        self.assertGreaterEqual(self.slots['Ctrl'].shape[1],45)
        self.assertEqual(self.slots['Ctrl'].shape[1],self.slots['Del'].shape[1])

    def test_digit_roi_reaches_left_border_and_keeps_both_glyphs(self):
        crop=self.slots['Ctrl']
        number=_digit_region(crop)
        self.assertGreaterEqual(number.shape[1],25)
        self.assertLess(number.shape[1],crop.shape[1])
        self.assertLess(number.shape[0],crop.shape[0])
        self.assertGreater(int(number.std()),12)

    def test_icon_snapshot_preserves_full_sprite_and_masks_key_chrome(self):
        for key in ['Ctrl','Del','PgDn']:
            crop=self.slots[key]
            icon=icon_snapshot(crop)
            self.assertEqual(icon.shape[2],4)
            self.assertGreater(icon.shape[1],int(crop.shape[1]*.90))
            self.assertGreater(icon.shape[0],int(crop.shape[0]*.85))
            self.assertGreater(int((icon[:,:,3]>0).sum()),70)
            self.assertGreater(int((icon[:,:,3]==0).sum()),70)

    def test_amount_one_confident_pass_is_temporally_confirmed(self):
        class Fake:
            def recognize_lines(self,images):
                return SimpleNamespace(txts=['40','','',''],scores=[.73,0,0,0])
        amt=read_potion_amounts(Fake(),{'Ctrl':self.slots['Ctrl']})
        self.assertEqual(amt['Ctrl'],40)
        gate=SlotCountGate()
        crop=self.slots['Ctrl']
        self.assertIsNone(gate.reuse('Ctrl','red',crop,1.))
        gate.record('Ctrl','red',crop,40,1.)
        self.assertEqual(gate.reuse('Ctrl','red',crop,1.2),40)

    def test_visual_event_identity_retained_for_emission(self):
        ledger=FrameMessageLedger()
        def msg(t,y):return {'body':t,'nickname':'P','rect':(0,y,200,16),'kind':'megaphone'}
        old=[msg('S> helmet 5m',30)]
        first=ledger.filter(old,old,1.)
        self.assertEqual(len(first),1)
        self.assertIsInstance(first[0].get('_visual_event_id'),int)
        repeat=[msg('S> helmet 5m',30)]
        self.assertEqual(ledger.filter(repeat,repeat,1.2),[])
        newer=[msg('S> helmet 5m',15),msg('S> helmet 5m',35)]
        got=ledger.filter(newer,newer,1.3)
        self.assertEqual(len(got),1)
        self.assertNotEqual(got[0]['_visual_event_id'],first[0]['_visual_event_id'])

    def test_worker_has_last_output_idempotence(self):
        s=(ROOT/'kain_maple_translator/worker.py').read_text('utf-8')
        self.assertIn("row['_visual_event_id']=item['id']",(ROOT/'kain_maple_translator/visual_message_ledger.py').read_text('utf-8'))
        self.assertIn('if event in self._emitted_visual_ids:return',s)
        self.assertIn('self._visual_epoch+=1',s)

if __name__=='__main__':unittest.main()
