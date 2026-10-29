from pathlib import Path
import tempfile
import unittest
from kain_maple_translator.core import (
    load_config, save_config, normalized, RepeatGuard, glossary_exact, likely_english,
    is_valid_region, overlaps,
)
from kain_maple_translator.translation import Translator, TranslationError


class Tests(unittest.TestCase):
    def test_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = load_config(Path(root) / 'empty.json')
            self.assertEqual(cfg['output'], 'overlay')
            self.assertEqual(list(cfg['enabled'].values()), [False, True, False])

    def test_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'settings.json'
            cfg = load_config(path)
            cfg['regions']['bubble'] = {'left': -100, 'top': 200, 'width': 500, 'height': 200}
            save_config(cfg, path)
            self.assertEqual(load_config(path)['regions']['bubble']['left'], -100)

    def test_bad_config(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'bad.json'
            path.write_text('{invalid', encoding='utf-8')
            self.assertEqual(load_config(path)['output'], 'overlay')

    def test_filter(self):
        self.assertTrue(likely_english('Anyone want to join a party?', 0.85))
        self.assertTrue(likely_english('S> 10m', .9))
        self.assertFalse(likely_english('파티 모집해요', .9))
        self.assertFalse(likely_english('!', .9))
        self.assertFalse(likely_english('hello', .2))

    def test_repeat_guard(self):
        guard = RepeatGuard(9.0)
        self.assertTrue(guard.is_new('chat', '  Hello   there! ', 100))
        self.assertFalse(guard.is_new('chat', 'hello there!', 101))
        self.assertTrue(guard.is_new('bubble', 'hello there!', 101))
        self.assertTrue(guard.is_new('chat', 'hello there!', 110.1))

    def test_glossary(self):
        self.assertEqual(glossary_exact('LFP', 'en-ko'), '파티 구해요')
        self.assertEqual(glossary_exact('파티 구해요', 'ko-en'), 'LFP')
        self.assertEqual(Translator().translate('LFP', 'en-ko'), '파티 구해요')

    def test_regions(self):
        self.assertTrue(is_valid_region({'left': -300, 'top': 0, 'width': 200, 'height': 100}))
        self.assertFalse(is_valid_region(None))
        self.assertFalse(is_valid_region({'left': 0, 'top': 0, 'width': 10, 'height': 100}))
        self.assertTrue(overlaps((0,0,10,10), (5,5,10,10)))
        self.assertFalse(overlaps((0,0,10,10), (11,11,10,10)))

    def test_invalid_direction(self):
        with self.assertRaises(ValueError):
            Translator().translate('anything', 'auto')

    def test_invalid_libre_config(self):
        with self.assertRaises(TranslationError):
            Translator(engine='libre').translate('anything', 'en-ko')


if __name__ == '__main__':
    unittest.main()
