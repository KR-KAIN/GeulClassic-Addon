import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kain_maple_translator.core import parse_chat_line, load_config, save_config
from kain_maple_translator.game_window import region_to_relative, relative_to_region, find_maple_window
from kain_maple_translator.translation import Translator, TranslationError, archive_folder

ROOT=Path(__file__).resolve().parents[1]

class OfflineTrackingTests(unittest.TestCase):
    def test_real_relative_coordinates_at_different_resolutions(self):
        game=(100,60,1366,768)
        chat={'left':380,'top':676,'width':560,'height':70}
        rel=region_to_relative(game,chat)
        self.assertEqual(relative_to_region(game,rel),chat)
        moved=(450,130,1366,768)
        self.assertEqual(relative_to_region(moved,rel)['left'],730)
        scaled=(100,60,683,384)
        self.assertEqual(relative_to_region(scaled,rel)['width'],280)

    def test_only_pid_image_qualifies_and_linux_returns_none(self):
        # Only non-Windows systems must return None. On Windows, a real
        # MapleStory process MAY be running during a user-initiated build.
        # Do not fail merely because the game's PID/HWND is found.
        with patch('kain_maple_translator.game_window.sys.platform', 'linux'):
            self.assertIsNone(find_maple_window())
        import sys
        if sys.platform == 'win32':
            actual = find_maple_window()
            if actual is not None:
                self.assertGreater(actual.pid, 0)
                self.assertGreater(actual.hwnd, 0)
                self.assertTrue(actual.executable)
                self.assertGreater(actual.rect[2], 0)
                self.assertGreater(actual.rect[3], 0)
        source=(ROOT/'kain_maple_translator/game_window.py').read_text(encoding='utf-8')
        for expected in ('GetWindowThreadProcessId','QueryFullProcessImageNameW','GetClientRect','ClientToScreen'):
            self.assertIn(expected,source)

    def test_only_nick_colon_korean_display(self):
        self.assertEqual(parse_chat_line('Player123 CH09 : hello world'),('Player123','hello world'))
        ui=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('self._records.append(record)',ui)
        self.assertIn('find_maple_window(self.game_pid, self.game_hwnd',ui)

    def test_no_web_client_used_in_translation(self):
        source=(ROOT/'kain_maple_translator/translation.py').read_text(encoding='utf-8')
        self.assertNotIn('urlopen',source)
        self.assertNotIn('mymemory',source.lower())
        self.assertNotIn('papago',source.lower())
        self.assertIn('ctranslate2',source)
        self.assertIn('sentencepiece', source)
        self.assertNotIn('from argostranslate import', source)

    def test_no_model_does_not_fake_output(self):
        with patch('kain_maple_translator.translation.prepare_models',side_effect=TranslationError('missing')):
            with self.assertRaisesRegex(TranslationError,'missing'):
                Translator().translate('Where is the party?', 'en-ko')

    def test_exact_glossary_shortcut_without_model(self):
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('should not call')):
            self.assertEqual(Translator().translate('LFP','en-ko'),'파티 구해요')

    def test_save_relative_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'config.json'
            cfg=load_config(path)
            cfg['relative_chat_region']={'x':.2,'y':.7,'w':.4,'h':.1}
            save_config(cfg,path)
            self.assertEqual(load_config(path)['relative_chat_region']['y'],.7)

    def test_source_files_are_decoded_as_utf8(self):
        # Windows PowerShell 5.1 typically runs with CP949 for Python text I/O.
        # Regression: no implicit locale-based decoding in source-inspection tests.
        test_src = Path(__file__).read_text(encoding='utf-8')
        tree = ast.parse(test_src)
        reads = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'read_text']
        self.assertTrue(reads)
        for call in reads:
            self.assertTrue(any(k.arg == 'encoding' for k in call.keywords),
                            f'Implicit locale decoding at source line {call.lineno}')
        for name in ('main.py', 'translation.py', 'game_window.py'):
            decoded = (ROOT/'kain_maple_translator'/name).read_text(encoding='utf-8')
            self.assertTrue(len(decoded) > 0)

    def test_builder_copies_both_model_archives(self):
        ps=(ROOT/'scripts/BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('MODEL-REPORT.txt',ps)
        self.assertIn('MODEL-TRANSLATION-REPORT.txt',ps)
        self.assertIn('--add-data',ps)
        self.assertIn('en_ko',ps)
        self.assertIn('ko_en',ps)

if __name__=='__main__':
    unittest.main()
