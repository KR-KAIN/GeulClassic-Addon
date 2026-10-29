"""Exercise model archive -> local extraction -> CT2 inference without a real 240MB model.

Mocked inference is NOT proof of actual translation quality. The builder runs real
inference against both downloaded models as a separate mandatory stage.
"""
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from kain_maple_translator import translation as t


class FakeResult:
    def __init__(self, tokens):
        self.hypotheses = [tokens]


class MockSP:
    def __init__(self, model_file):
        assert Path(model_file).is_file()
        self.model_file = model_file

    def encode(self, text, out_type=str):
        return ['▁' + text]

    def decode(self, tokens):
        return ''.join(tokens).replace('▁', ' ').strip()


class MockCT2:
    calls = []
    def __init__(self, model_path, **kwargs):
        assert Path(model_path, 'model.bin').is_file()
        self.model_path = model_path
        MockCT2.calls.append(('init', model_path, kwargs))

    def translate_batch(self, batches, **kwargs):
        MockCT2.calls.append(('translate', batches, kwargs))
        if any('어디' in str(t) for b in batches for t in b):
            return [FakeResult(['▁Where', '▁is', '▁it?'])]
        prefix = kwargs.get('target_prefix', [['']])[0][0]
        return [FakeResult(([prefix] if prefix else []) + ['▁안녕하세요'])]


class DirectCT2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archives = self.root / 'resources' / 'models'
        self.archives.mkdir(parents=True)
        self.dest = self.root / 'installed'
        for from_code, to_code in (('en', 'ko'), ('ko', 'en')):
            with zipfile.ZipFile(self.archives / f'translate-{from_code}_{to_code}.argosmodel', 'w') as z:
                prefix = f'{from_code}_{to_code}/'
                z.writestr(prefix + 'metadata.json', json.dumps({'from_code': from_code,
                    'to_code': to_code, 'target_prefix': '<to>' if from_code == 'en' else ''}))
                z.writestr(prefix + 'sentencepiece.model', 'spm' * 64)
                # Old official en_ko model omits config.json. Keep the other
                # language pair with one to verify both supported layouts.
                if from_code == 'ko':
                    z.writestr(prefix + 'model/config.json', '{"model_type":"Transformer"}')
                z.writestr(prefix + 'model/model.bin', os.urandom(110_000), compress_type=zipfile.ZIP_STORED)
                z.writestr(prefix + '../../bad.txt', 'unsafe')
        t._ENGINES.clear(); t._READY.clear(); MockCT2.calls.clear()
        patchers = [patch.object(t, 'archive_folder', return_value=self.archives),
                    patch.object(t, 'direct_model_folder', return_value=self.dest),
                    patch.dict(sys.modules, {
                        'ctranslate2': types.SimpleNamespace(Translator=MockCT2, get_supported_compute_types=lambda device: {'int8','float32'}),
                        'sentencepiece': types.SimpleNamespace(SentencePieceProcessor=MockSP)})]
        for p in patchers:
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(t._ENGINES.clear)
        self.addCleanup(t._READY.clear)

    def test_extract_and_translate_both_directions(self):
        a = t.translate_generic('Hello', 'en-ko')
        b = t.translate_generic('어디로 가세요?', 'ko-en')
        self.assertEqual(a, '안녕하세요')
        self.assertEqual(b, 'Where is it?')
        self.assertFalse((self.root / 'bad.txt').exists())
        self.assertTrue((self.dest / 'en_ko' / 'model' / 'model.bin').exists())
        self.assertFalse((self.dest / 'en_ko' / 'model' / 'config.json').exists())
        self.assertTrue((self.dest / 'ko_en' / 'model' / 'config.json').exists())
        self.assertTrue(any(c[0]=='translate' and c[2].get('target_prefix') == [['<to>']] for c in MockCT2.calls))

    def test_optional_config_is_not_required_for_cached_model(self):
        # Check that a config-less model stays ready across multiple loads.
        t.prepare_models()
        en_dir = self.dest / 'en_ko'
        self.assertFalse((en_dir / 'model' / 'config.json').exists())
        self.assertTrue(t._model_ready(en_dir))
        with patch.object(t, '_unpack_model', side_effect=AssertionError('unexpected re-extraction')):
            t.prepare_models()
        self.assertEqual(t.translate_generic('Hello', 'en-ko'), '안녕하세요')

    def test_missing_actual_model_binary_is_still_rejected(self):
        t.prepare_models()
        folder = self.dest / 'en_ko'
        (folder / 'model' / 'model.bin').unlink()
        self.assertFalse(t._model_ready(folder))
        t._READY.clear()
        t.prepare_models()
        self.assertTrue(t._model_ready(folder))

    def test_caches_local_models_and_engines(self):
        t.translate_generic('Hello', 'en-ko')
        t.translate_generic('Hello again', 'en-ko')
        self.assertEqual(sum(x[0]=='init' for x in MockCT2.calls), 1)

    def test_missing_archive_returns_real_error(self):
        (self.archives / 'translate-en_ko.argosmodel').unlink()
        with self.assertRaisesRegex(t.TranslationError, '압축 파일이 없습니다'):
            t.prepare_models()

    def test_model_invalid_metadata_does_not_succeed(self):
        archive = self.archives / 'translate-en_ko.argosmodel'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('metadata.json',json.dumps({'from_code':'xx','to_code':'ko'}))
        with self.assertRaises(t.TranslationError):
            t.prepare_models()

    def test_zero_model_bytes_never_count_as_success(self):
        self.assertFalse(t._model_ready(self.root / 'unknown'))
        with self.assertRaises(ValueError):
            t.translate_generic('Some chat', 'wrong-direction')


if __name__ == '__main__':
    unittest.main()
