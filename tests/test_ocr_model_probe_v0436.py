"""Regression for v0.4.35 Windows OCR build-gate false failures."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from scripts.check_ocr_models import verify_recognizers

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def result(*items):
    return SimpleNamespace(txts=items)


class FakeRecognizer:
    def __init__(self, *, whole_korean=True, item_korean=True, latin=True):
        self.ocr = Mock()
        self.ocr.recognize_txt.return_value = result('KAIN chat 123' if latin else '???')
        self.ocr.return_value = result('KAIN chat 123')
        self.korean_ocr = SimpleNamespace(recognize_txt=Mock(return_value=result(
            '[아대 공격력 주문서 60%]' if whole_korean else 'KAIN chat ?')))
        self.korean_link_ocr = SimpleNamespace(recognize_txt=Mock(return_value=result(
            '[아대 공격력 주문서 60%]' if item_korean else '[?]')))


class OCRModelProbeTests(unittest.TestCase):
    def test_korean_model_does_not_need_english_digits(self):
        reader = FakeRecognizer()
        verify_recognizers(reader, FIXTURES)
        self.assertEqual(reader.korean_ocr.recognize_txt.call_count, 1)
        self.assertEqual(reader.korean_link_ocr.recognize_txt.call_count, 1)

    def test_korean_whole_line_failure_keeps_build_blocked_with_diagnostics(self):
        reader = FakeRecognizer(whole_korean=False)
        with self.assertRaisesRegex(RuntimeError, 'Korean whole-line.*outputs='):
            verify_recognizers(reader, FIXTURES)
        self.assertEqual(reader.korean_ocr.recognize_txt.call_count, 4)

    def test_korean_item_failure_keeps_build_blocked(self):
        with self.assertRaisesRegex(RuntimeError, 'Korean item OCR real inference failed'):
            verify_recognizers(FakeRecognizer(item_korean=False), FIXTURES)

    def test_multilingual_failure_keeps_build_blocked(self):
        with self.assertRaisesRegex(RuntimeError, 'Multilingual OCR real inference failed'):
            verify_recognizers(FakeRecognizer(latin=False), FIXTURES)


if __name__ == '__main__':
    unittest.main()
