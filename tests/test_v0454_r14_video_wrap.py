"""Actual R13 OCR at 1.27s of the 17:40 recording, no invented sentences."""
import json
import unittest
from pathlib import Path

from kain_maple_translator.core import merge_chat_ocr
from kain_maple_translator.vision import Line


class VideoWrapTests(unittest.TestCase):
    def test_failed_separate_prefix_is_not_added_to_previous_speaker(self):
        data = json.loads((Path(__file__).parent / 'fixtures/r14/wrapped-prefix.json').read_text())
        lines = [Line(**entry) for entry in data['lines']]
        rows = merge_chat_ocr(lines)
        dustin = next(row for row in rows if row['nickname'] == 'DUSTIN')
        assert dustin['body'] == 'GRATZ ON MADY LVL 31 BEST GUILD LEA DER EVER PLS BUY ME MOLLY'
        assert 'bihh' not in dustin['body']
        assert '[라이징]' not in dustin['body']
        assert next(row for row in rows if row['nickname'] == 'yumigo')['body'] == (
            'B Blue Arten +8magicatk for 300k +12magicatk for600k')


if __name__ == "__main__":
    unittest.main()
