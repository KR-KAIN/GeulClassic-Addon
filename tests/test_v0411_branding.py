"""Branding and item import opt-in smoke tests; run without Qt or Windows."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class RebrandingTests(unittest.TestCase):
    def test_visible_windows_uses_requested_name_and_creator(self):
        ui=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn("app.setApplicationName('글클메 애드온')", ui)
        self.assertIn("self.setWindowTitle('글클메 애드온 · 설정')", ui)
        self.assertIn('제작자 KAIN',ui)
    def test_obs_brand_and_build_exe_are_consistent(self):
        obs=(ROOT/'kain_maple_translator/obs_source.py').read_text(encoding='utf-8')
        ps=(ROOT/'scripts/BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('<title>글클메 애드온 - OBS · 제작자 KAIN</title>',obs)
        self.assertIn("'--name','글클메 애드온'",ps)
        self.assertIn('dist\\글클메 애드온\\글클메 애드온.exe',ps)
    def test_catalog_import_is_local_and_opt_in(self):
        imp=(ROOT/'kain_maple_translator/item_catalog.py').read_text(encoding='utf-8')
        self.assertIn('def install_catalog(',imp)
        self.assertNotIn('requests.get(',imp)
        self.assertNotIn('urlopen(',imp)
if __name__=='__main__': unittest.main()
