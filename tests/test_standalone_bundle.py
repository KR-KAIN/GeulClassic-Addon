from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class IndependentBundleTests(unittest.TestCase):
    def test_all_entry_files_in_same_folder(self):
        for rel in ('BUILD-WINDOWS.bat','START-SOURCE.bat','launch.py','requirements.txt',
                    'scripts/BUILD-WINDOWS.ps1','kain_maple_translator/main.py',
                    'kain_maple_translator/vision.py','kain_maple_translator/glossary.py',
                    'tests/test_core.py'):
            with self.subTest(file=rel):
                self.assertTrue((ROOT/rel).is_file())
    def test_no_previous_version_folder_dependency(self):
        batch=(ROOT/'BUILD-WINDOWS.bat').read_text(encoding='ascii')
        ps=(ROOT/'scripts/BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('set "ROOT=%~dp0"',batch)
        self.assertIn("$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))",ps)
        self.assertIn('Source bundle self-check PASS',ps)
        self.assertNotIn('KAIN-Maple-Translator-v0.2.4', batch + ps)
        self.assertNotIn('FIX-AND-BUILD.bat',batch+ps)
    def test_reusable_python_without_global_path(self):
        ps=(ROOT/'scripts/BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('KAINMapleTranslator\\BuildPython312\\python.exe',ps)
        self.assertIn("'-m','PyInstaller'",ps)
        self.assertIn('Install dependencies',ps)
        self.assertIn('dist\\글클메 애드온\\글클메 애드온.exe',ps)
