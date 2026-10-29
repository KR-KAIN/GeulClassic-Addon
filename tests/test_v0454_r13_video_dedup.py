"""Identity regressions grounded in the supplied 88.2-second recording.

The JSON stores actual R12 OCR observations. PhysicalArrivalTests uses a
manual transcription of six visible frames (13.0–19.0 seconds), including
every genuine repeated party post. No invented translation input is used.
"""
import copy
import json
from pathlib import Path
import unittest
import cv2
from kain_maple_translator.row_admission import RowAdmission, starts_inside_verified_badge
from kain_maple_translator.visual_message_ledger import FrameMessageLedger, _slot_same

ROOT=Path(__file__).parent/'fixtures/r13'
FRAMES=json.loads((ROOT/'dedup-video-rows.json').read_text(encoding='utf-8'))['frames']

def frame(second):
    return copy.deepcopy(next(f['rows'] for f in FRAMES if f['second']==second))

def replay(start,end):
    ledger=FrameMessageLedger();admission=RowAdmission();events=[]
    for f in FRAMES:
        if not start<=f['second']<=end:continue
        rows=copy.deepcopy(f['rows'])
        events.extend(ledger.filter(admission.filter(rows,100+f['second']),rows,100+f['second']))
    return events

class ObservedOCRDriftTests(unittest.TestCase):
    def test_yes_sender_drift_is_one_physical_post(self):
        yes=[r for r in replay(47.5,51) if r['body']=='yes']
        self.assertEqual(len(yes),1)
        self.assertEqual(yes[0]['nickname'],'Hunnii')

    def test_blade_leading_i_l_drift_is_not_new_post(self):
        rows=[r for r in replay(59.5,61) if 'Emerald Earrings' in r['body']]
        self.assertEqual(len(rows),1)

    def test_same_price_shape_required(self):
        old=next(r for r in frame(3.) if r['nickname']=='Sioo')
        new=next(r for r in frame(81.) if 'Mystery Face Coupon' in r['body'])
        self.assertIn('50k',old['body']);self.assertIn('45k',new['body'])
        self.assertFalse(_slot_same(old,new))

    def test_no_neighbour_evidence_does_not_guess_sender_identity(self):
        a=[next(r for r in frame(47.73) if r['body']=='yes')]
        b=[next(r for r in frame(48.27) if r['body']=='yes')]
        ledger=FrameMessageLedger()
        self.assertEqual(len(ledger.filter(a,a,47.73)),1)
        self.assertEqual(len(ledger.filter(b,b,48.27)),1)

    def test_ch_badge_is_not_a_sender_name(self):
        row=frame(6.)[0]
        self.assertEqual(row['nickname'],'Ho3')
        image=cv2.imread(str(ROOT/'clipped-ch-badge-06s.png'))
        self.assertTrue(starts_inside_verified_badge(row,image,0,0))

    def test_full_sioo_sender_survives(self):
        row=frame(3.)[0]
        image=cv2.imread(str(ROOT/'valid-sioo-03s.png'))
        self.assertFalse(starts_inside_verified_badge(row,image,0,0))


class PhysicalArrivalTests(unittest.TestCase):
    # Transcribed from the visible game chat, not the translated overlay.
    messages={
        's':('Sioo','[Black Cardigan Set] 25k'),
        'm':('MochiThief','S> founders (11) 300k| 5 slots 45k ea..'),
        'o':('Outplayed','use maplefind to find your old maplestory friends'),
        'a':('Hipp0Crit','J>PQ RUSH ^_^'),
        'b':('Hipp0Crit','J>PQ RUSH'),
        'g':('biggochuman','B >> WORK GLOVES ATT +6 CRI +2 BUY / OFFER ME'),
    }
    observed=((13.,'smoa'),(13.5,'moab'),(15.,'oabg'),
              (15.5,'abgb'),(17.,'bgba'),(19.,'gbab'))

    def rows(self,keys):
        return [{'nickname':self.messages[k][0],'body':self.messages[k][1],
                 'rect':(0,8+i*18,600,16)} for i,k in enumerate(keys)]

    def test_all_five_actual_party_arrivals_are_retained(self):
        ledger=FrameMessageLedger();party=[]
        for second,keys in self.observed:
            rows=self.rows(keys)
            party.extend(r for r in ledger.filter(rows,rows,second)
                         if r['nickname']=='Hipp0Crit')
        self.assertEqual(len(party),5)
        self.assertEqual(len({r['_visual_event_id'] for r in party}),5)

    def test_missing_old_party_row_cannot_steal_later_real_repost(self):
        ledger=FrameMessageLedger();party=[]
        for second,keys in self.observed:
            rows=self.rows(keys)
            # Ablate the first old party row after 13s to model an OCR
            # dropout. These are the same recorded frames and source words.
            if second in (13.5,15.,15.5):
                rows=[r for r in rows if r['body']!='J>PQ RUSH ^_^']
            party.extend(r for r in ledger.filter(rows,rows,second)
                         if r['nickname']=='Hipp0Crit')
        self.assertEqual(len(party),5)
        self.assertEqual(len({r['_visual_event_id'] for r in party}),5)

if __name__=='__main__':unittest.main()
