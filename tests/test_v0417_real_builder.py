
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class RealEXEBuilderRegression(unittest.TestCase):
    def test_no_confusing_item_index_batch_at_zip_root(self):
        self.assertFalse((ROOT / 'BUILD-ITEM-DB.bat').exists())
        self.assertTrue((ROOT / 'scripts' / 'build_classic_index.py').exists())

    def test_entrypoint_starts_full_powershell_build(self):
        batch = (ROOT / 'BUILD-WINDOWS.bat').read_text(encoding='ascii')
        self.assertIn('FULL WINDOWS EXE BUILDER', batch)
        self.assertIn('powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File', batch)
        self.assertIn('scripts\\BUILD-WINDOWS.ps1', batch)
        self.assertNotIn('scripts.build_classic_index', batch)
        self.assertIn('BUILD-REPORT.txt', batch)
        self.assertIn('pause', batch.lower())

    def test_real_exe_required_before_success(self):
        batch = (ROOT / 'BUILD-WINDOWS.bat').read_text(encoding='ascii')
        ps = (ROOT / 'scripts' / 'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('BUILD PASS - EXE and EN/KO models packaged', batch)
        self.assertIn('Build standalone Windows EXE', ps)
        self.assertIn('PyInstaller reported success but the executable is missing', ps)
        self.assertIn('foreach ($Direction', ps)

    def test_source_bat_venv_matches_actual_builder(self):
        batch = (ROOT / 'START-SOURCE.bat').read_text(encoding='ascii')
        ps = (ROOT / 'scripts' / 'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('BuildVenv0418', batch)
        self.assertIn("'KAINMapleTranslator\\BuildVenv0418'", ps)
