from pathlib import Path
import unittest
import subprocess
import tempfile
import sys
import struct
import re

ROOT=Path(__file__).resolve().parents[1]

class BootstrapPackagingTests(unittest.TestCase):
    def test_user_consent_present(self):
        p=(ROOT/'scripts'/'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('Read-Host',p)
        self.assertIn('if ($Consent -notmatch',p)
        self.assertIn('https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe',p)
    def test_signature_and_user_only_install(self):
        p=(ROOT/'scripts'/'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('Get-AuthenticodeSignature',p)
        self.assertIn('Python Software Foundation',p)
        self.assertIn('InstallAllUsers=0',p)
        self.assertIn('PrependPath=0',p)
    def test_rescan_after_installer_and_capture_diagnostics(self):
        p=(ROOT/'scripts'/'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('function Find-PythonCandidates',p)
        self.assertIn('function Write-Python-Diagnostics',p)
        self.assertIn('$Found = Select-Python',p)
        self.assertIn('PYTHON-SETUP-REPORT.txt',p)
        self.assertIn('python-installer.log',p)
    def test_reuse_only_verified_cached_download(self):
        p=(ROOT/'scripts'/'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('if ($ValidCached)',p)
        self.assertIn('Get-AuthenticodeSignature',p)
        self.assertIn('Do not rerun the installer blindly.',p)
    def test_powershell_safe_python_probe(self):
        script=(ROOT/'scripts'/'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        found=re.search(r"\$Probe = '([^'\n]+)'",script)
        self.assertIsNotNone(found)
        code=found.group(1)
        self.assertNotIn('"',code)
        self.assertNotIn("'",code)
        # On Windows, NamedTemporaryFile remains locked while open. A separate
        # Python process then cannot create/overwrite that path (WinError 5).
        # Create an unused path inside a temporary DIRECTORY instead.
        with tempfile.TemporaryDirectory() as folder:
            output_path = Path(folder) / 'python-probe-result.txt'
            result = subprocess.run(
                [sys.executable, '-I', '-c', code, str(output_path)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = str(sys.version_info.major * 10000
                           + sys.version_info.minor * 100
                           + struct.calcsize('P') * 8)
            self.assertTrue(output_path.is_file(), 'Probe did not create result file')
            self.assertEqual(output_path.read_text(encoding='utf-8'), expected)
    def test_probe_writes_diagnostics_and_reuses_local_install(self):
        p=(ROOT/'scripts'/'BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('PYTHON-PROBE-LOG.txt',p)
        self.assertIn('KAINMapleTranslator\\BuildPython312\\python.exe',p)
        self.assertIn("'31164','31264'",p)
        self.assertIn("-I -c $Probe $Marker",p)
    def test_start_source_matches_build_environment(self):
        p=(ROOT/'START-SOURCE.bat').read_text(encoding='ascii')
        self.assertIn('BuildVenv0418',p)
        self.assertNotIn('.venv-win-build\\',p)
    def test_scripts_encoding(self):
        bat=(ROOT/'BUILD-WINDOWS.bat').read_bytes()
        ps=(ROOT/'scripts'/'BUILD-WINDOWS.ps1').read_bytes()
        self.assertTrue(bat.isascii())
        self.assertIn(b'\r\n',bat)
        self.assertTrue(ps.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n',ps)
if __name__=='__main__': unittest.main()
