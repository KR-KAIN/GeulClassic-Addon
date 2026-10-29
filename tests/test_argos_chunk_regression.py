"""Regression for the real-translation failure: invalid Argos sentence splitter."""
import os
import unittest
from unittest.mock import patch
from pathlib import Path
from kain_maple_translator.translation import configure_offline_environment, model_folder


class ArgosChunkRegression(unittest.TestCase):
    def test_force_supported_segmenter_even_when_none_was_persisted(self):
        with patch.dict(os.environ, {'ARGOS_CHUNK_TYPE': 'NONE'}):
            configure_offline_environment()
            self.assertEqual(os.environ['ARGOS_CHUNK_TYPE'], 'DEFAULT')

    def test_supported_chunk_selector_on_clean_machine(self):
        # A clean Windows process may have neither LOCALAPPDATA nor HOME.
        # The builder must not fail just because this test clears os.environ.
        with patch.dict(os.environ, {}, clear=True):
            configure_offline_environment()
            self.assertEqual(os.environ['ARGOS_CHUNK_TYPE'], 'DEFAULT')
            self.assertEqual(os.environ['ARGOS_PACKAGES_DIR'], str(model_folder()))

    def test_no_home_or_localappdata_falls_back_safely(self):
        # Reproduce 'Could not determine home directory' on Windows.
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(Path, 'home', side_effect=RuntimeError('Could not determine home directory')):
                configure_offline_environment()
                package_dir = Path(os.environ['ARGOS_PACKAGES_DIR'])
                self.assertEqual(package_dir.name, 'argos-packages')
                self.assertIn('KAINMapleTranslator', package_dir.parts)

    def test_localappdata_has_priority(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': r'C:\KAINTest\UserData'}, clear=True):
            path = str(model_folder())
            self.assertIn('KAINMapleTranslator', path)
            self.assertIn('argos-packages', path)
            self.assertTrue(path.startswith(os.environ['LOCALAPPDATA']))


if __name__ == '__main__':
    unittest.main()
