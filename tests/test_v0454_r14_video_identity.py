"""Identity tests from the supplied 17:40 recording's pixels and OCR."""
import copy
import json
import unittest
from pathlib import Path

from kain_maple_translator.visual_message_ledger import FrameMessageLedger, _slot_same


DATA = json.loads((Path(__file__).parent / 'fixtures/r14/identity-video-rows.json').read_text())


def observed(second):
    return copy.deepcopy(next(f['rows'] for f in DATA['ocr_frames'] if f['second'] == second))


class VideoIdentityTests(unittest.TestCase):
    def test_printed_channel_range_dash_drift_keeps_one_physical_identity(self):
        ledger = FrameMessageLedger()
        results = []
        for second in (16., 16.5):
            rows = observed(second)
            results.extend(ledger.filter(rows, rows, second))
        outputs = [r for r in results if r['nickname'] == 'Yawaradi']
        assert len(outputs) == 1
        assert outputs[0]['body'] == 'its ch 3 -12 brotheer'

    def test_terminal_attention_glyph_is_not_a_new_price(self):
        ledger = FrameMessageLedger()
        results = []
        for second in (28., 28.27):
            rows = observed(second)
            results.extend(ledger.filter(rows, rows, second))
        outputs = [r for r in results if r['nickname'].startswith('Pikachibi')]
        assert len(outputs) == 1
        # Keep the source OCR string unchanged; only identity is normalized.
        assert outputs[0]['body'].endswith('@' * 20)

    def test_uncertain_price_read_stays_distinct(self):
        first = next(r for r in observed(19.) if r['nickname'] == 'Pikachibi')
        second = next(r for r in observed(20.) if r['nickname'] == 'Pikachibi')
        assert '2KC' in first['body']
        assert '2K ' in second['body']
        assert not _slot_same(first, second)

    def test_both_actual_darkmen_reposts_are_preserved(self):
        ledger = FrameMessageLedger()
        results = []
        for frame in DATA['manual_frames']:
            rows = copy.deepcopy(frame['rows'])
            results.extend(ledger.filter(rows, rows, frame['second']))
        outputs = [r for r in results if r['nickname'] == 'DarkMen']
        assert len(outputs) == 2
        assert outputs[0]['body'] == outputs[1]['body']
        assert outputs[0]['_visual_event_id'] != outputs[1]['_visual_event_id']


if __name__ == "__main__":
    unittest.main()
