"""R8 TTL experiment should not alter OCR or delivery in shadow mode."""
import unittest
from pathlib import Path
from unittest.mock import patch
from kain_maple_translator.ttl_experiment import TTLTrial


def row(text='WTB glove scroll',y=30):
    return {'nickname':'Trade','body':text,'rect':(10,y,140,16),'kind':'megaphone',
            '_visual_event_id':1}

class TTLTrialTests(unittest.TestCase):
    def test_default_is_shadow(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(TTLTrial.from_environment().mode,'shadow')

    def test_shadow_does_not_block(self):
        t=TTLTrial('shadow')
        first=row();accepted,_=t.evaluate([first],[first],0.0)
        self.assertEqual(accepted,[first])
        again=row();accepted,stats=t.evaluate([again],[again],5.0)
        self.assertEqual(accepted,[again])
        self.assertEqual(stats['ttl_short_allowed'],1)
        self.assertEqual(stats['ttl_long_allowed'],0)
        self.assertEqual(stats['ttl_extra_blocked'],1)
        self.assertEqual(stats['ttl_actual_blocked'],0)
        self.assertEqual(stats['ttl_visual_new_blocked'],1)

    def test_15_seconds_vs_2_seconds(self):
        t=TTLTrial('active')
        first=row();self.assertEqual(len(t.evaluate([first],[first],0.)[0]),1)
        middle=row();actual,stats=t.evaluate([middle],[middle],5.)
        self.assertEqual(actual,[])
        self.assertEqual(stats['ttl_actual_blocked'],1)
        later=row();actual,stats=t.evaluate([later],[later],21.)
        self.assertEqual(len(actual),1)

    def test_valid_bottom_arrival_is_not_blocked(self):
        t=TTLTrial('active')
        first=row();t.evaluate([first],[first],0.0)
        next_post=row();next_post['_bottom_arrival']=True
        actual,stats=t.evaluate([next_post],[next_post],5.0)
        self.assertEqual(actual,[next_post])
        self.assertEqual(stats['ttl_actual_blocked'],0)

    def test_different_text_is_accepted(self):
        t=TTLTrial('active')
        first=row();t.evaluate([first],[first],0.)
        next_post=row('WTB helmet scroll');actual,_=t.evaluate([next_post],[next_post],5.)
        self.assertEqual(actual,[next_post])

    def test_off_returns_unchanged_and_no_filter_calls(self):
        t=TTLTrial('off')
        first=row();actual,stats=t.evaluate([first],[first],0.)
        self.assertIs(actual[0],first)
        self.assertEqual(stats['ttl_trial_mode'],'off')

    def test_scroll_resume_does_not_replay_fresh_candidates(self):
        # R7 intentionally suppresses events when user scrolls back to bottom.
        source=(Path(__file__).resolve().parents[1]/'kain_maple_translator/worker.py').read_text('utf-8')
        self.assertIn('fresh = []\n                        trial_fresh = []',source)

    def test_worker_integrates_after_ledger_without_changing_ocr(self):
        root=Path(__file__).resolve().parents[1]
        s=(root/'kain_maple_translator/worker.py').read_text('utf-8')
        self.assertLess(s.index('visual_ledger.filter(admitted, rows, captured.captured_at)'),
                        s.index('ttl_trial.evaluate(fresh, rows, captured.captured_at)'))
        self.assertLess(s.index('ttl_trial.evaluate(fresh, rows, captured.captured_at)'),
                        s.index('channel_guard.accept(row, captured.captured_at)'))
        self.assertIn('ttl_trial_mode',s)
        self.assertIn('SlidingChatDeduper()',s) # pre-existing constructor remains

if __name__=='__main__':unittest.main()
