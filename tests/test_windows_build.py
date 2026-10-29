"""Regression tests for the Windows entrypoint package."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildScriptsTests(unittest.TestCase):
    def test_no_pytest_dependency_in_build_tests(self):
        # The Windows builder installs requirements.txt and runs stdlib
        # unittest. A local developer's pytest installation must not hide
        # a dependency missing from the independent Windows build.
        imports = []
        for path in (ROOT / 'tests').glob('test*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                if isinstance(node, ast.Import):
                    names = [entry.name for entry in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or '']
                else:
                    continue
                imports.extend((path.name, name) for name in names
                               if name.split('.')[0] in ('pytest', '_pytest'))
        self.assertEqual(imports, [], 'Build tests require an undeclared test runner')

    def test_all_top_level_tests_have_unittest_discovery_adapter(self):
        missing = []
        for path in (ROOT / 'tests').glob('test*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            functions = [node.name for node in tree.body
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if 'load_tests' not in functions:
                missing.extend((path.name, name) for name in functions
                               if name.startswith('test_'))
        self.assertEqual(missing, [], 'These tests would be silently skipped by unittest')

    def test_batch_is_ascii_crlf(self):
        for name in ('BUILD-WINDOWS.bat', 'START-SOURCE.bat', 'OPEN-BUILD-CONSOLE.bat'):
            with self.subTest(name=name):
                raw = (ROOT / name).read_bytes()
                self.assertTrue(raw.isascii())
                self.assertIn(b'\r\n', raw)
                self.assertEqual(raw.replace(b'\r\n', b'').count(b'\n'), 0)
                self.assertNotIn(b'chcp', raw.lower())

    def test_powershell_utf8_bom_for_windows_5(self):
        raw = (ROOT / 'scripts' / 'BUILD-WINDOWS.ps1').read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n', raw)

    def test_all_build_paths_quoted_and_source_self_contained(self):
        raw = (ROOT / 'BUILD-WINDOWS.bat').read_text(encoding='ascii')
        self.assertIn('"%ROOT%scripts\\BUILD-WINDOWS.ps1"',raw)
        self.assertIn('set "ROOT=%~dp0"',raw)
        self.assertIn('BUILD-STARTUP-LOG.txt',raw)
        self.assertIn('FULL WINDOWS EXE BUILDER',raw)
        self.assertIn('PowerShell exit code:',raw)
        self.assertIn('findstr /C:',raw)
        self.assertIn('goto END',raw)
        self.assertIn('pause',raw.lower())
        self.assertFalse((ROOT/'BUILD-ITEM-DB.bat').exists())
        self.assertIn('BuildVenv0418', (ROOT/'START-SOURCE.bat').read_text(encoding='ascii'))
        self.assertTrue((ROOT/'launch.py').is_file())
        self.assertTrue((ROOT/'requirements.txt').is_file())
        self.assertTrue((ROOT/'kain_maple_translator'/'main.py').is_file())


if __name__ == '__main__':
    unittest.main()
