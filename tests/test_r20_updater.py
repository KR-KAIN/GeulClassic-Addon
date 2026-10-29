"""R20.2: update check against the GitHub releases page (no network in tests)."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kain_maple_translator import updater

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b'fake setup bytes' * 1000


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


NOTES = ('새 기능 버전입니다.\n\n## 설치\n\n설치 파일을 받으세요.\n\n## 바뀐 점: 패널\n\n'
         '- 번역기 X 버튼\n\n## 파일 확인\n\n`ABC`\n\n---\nMapleStory © NEXON.')


def release_json(tag='v0.4.54-R20.3', digest=None, asset_url=None, name=None):
    if digest is None:
        digest = 'sha256:' + hashlib.sha256(PAYLOAD).hexdigest()
    version = tag[1:]
    return json.dumps({
        'tag_name': tag, 'name': f'글클메 애드온 {tag}', 'draft': False, 'prerelease': False,
        'body': NOTES,
        'html_url': f'https://github.com/KR-KAIN/GeulClassic-Addon/releases/tag/{tag}',
        'assets': [{'name': name or f'GeulClassic-Addon-Setup-{tag}.exe', 'size': len(PAYLOAD),
                    'digest': digest,
                    'browser_download_url': asset_url or
                    f'https://github.com/KR-KAIN/GeulClassic-Addon/releases/download/{tag}/GeulClassic-Addon-Setup-v{version}.exe'}],
    }).encode('utf-8')


def opener_for(api: bytes, payload: bytes = PAYLOAD):
    def opener(req, timeout=0):
        url = req.full_url
        return FakeResponse(api if 'api.github.com' in url else payload)
    return opener


class Versions(unittest.TestCase):
    def test_order(self):
        self.assertEqual(updater.parse_version('v0.4.54-R20.2'), (0, 4, 54, 20, 2))
        self.assertEqual(updater.parse_version('v0.4.54-R19'), (0, 4, 54, 19, 0))
        self.assertTrue(updater.is_newer('v0.4.54-R20.3', '0.4.54-R20.2'))
        self.assertTrue(updater.is_newer('v0.4.54-R21', '0.4.54-R20.9'))
        self.assertTrue(updater.is_newer('v0.4.55-R1', '0.4.54-R20.2'))
        self.assertFalse(updater.is_newer('v0.4.54-R20.2', '0.4.54-R20.2'))
        self.assertFalse(updater.is_newer('v0.4.54-R20.1', '0.4.54-R20.2'))
        self.assertFalse(updater.is_newer('nonsense', '0.4.54-R20.2'))

    def test_app_version_matches_installer_default(self):
        iss = (ROOT / 'installer' / 'GeulClassic-Addon.iss').read_text(encoding='utf-8-sig')
        self.assertIn(f'#define AppVersion "{updater.APP_VERSION}"', iss)


class Check(unittest.TestCase):
    def test_newer_release_found_with_digest(self):
        with patch.object(updater, 'APP_VERSION', '0.4.54-R20.2'):
            rel = updater.check(opener=opener_for(release_json()))
        self.assertIsNotNone(rel)
        self.assertEqual(rel.version, '0.4.54-R20.3')
        self.assertEqual(rel.sha256, hashlib.sha256(PAYLOAD).hexdigest())

    def test_notes_show_what_changes_not_the_install_steps(self):
        rel = updater.latest_release(opener=opener_for(release_json()))
        self.assertIn('## 바뀐 점: 패널', rel.notes)
        self.assertIn('번역기 X 버튼', rel.notes)
        self.assertIn('새 기능 버전입니다.', rel.notes)
        for gone in ('## 설치', '설치 파일을 받으세요', '파일 확인', 'ABC', 'NEXON'):
            self.assertNotIn(gone, rel.notes)

    def test_same_or_older_is_not_offered(self):
        with patch.object(updater, 'APP_VERSION', '0.4.54-R20.3'):
            self.assertIsNone(updater.check(opener=opener_for(release_json())))

    def test_only_this_repository_and_setup_files(self):
        other = release_json(asset_url='https://evil.example/GeulClassic-Addon-Setup-v0.4.54-R20.3.exe')
        self.assertIsNone(updater.latest_release(opener=opener_for(other)))
        zipped = release_json(name='source.zip')
        self.assertIsNone(updater.latest_release(opener=opener_for(zipped)))


class Download(unittest.TestCase):
    def test_good_file_is_kept(self):
        rel = updater.latest_release(opener=opener_for(release_json()))
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            path = updater.download(rel, Path(tmp), progress=lambda d, t: seen.append((d, t)),
                                    opener=opener_for(release_json()))
            self.assertEqual(path.read_bytes(), PAYLOAD)
        self.assertEqual(seen[-1], (len(PAYLOAD), len(PAYLOAD)))

    def test_changed_file_is_refused(self):
        rel = updater.latest_release(opener=opener_for(release_json()))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(updater.UpdateError):
                updater.download(rel, Path(tmp), opener=opener_for(release_json(), b'tampered'))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_no_digest_no_install(self):
        rel = updater.latest_release(opener=opener_for(release_json(digest='')))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(updater.UpdateError):
            updater.download(rel, Path(tmp), opener=opener_for(release_json()))


class Window(unittest.TestCase):
    """The game-style UPDATE window: notes first, then 지금 업데이트 / 나중에."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_notes_and_the_two_choices(self):
        from kain_maple_translator.classic_windows import UpdateWindow
        rel = updater.latest_release(opener=opener_for(release_json()))
        win = UpdateWindow(rel, '0.4.54-R20.2', can_install=True)
        self.assertIn('번역기 X 버튼', win.notes.toPlainText())
        self.assertEqual((win.now.text(), win.now.property('classic')), ('지금 업데이트', 'lime'))
        self.assertEqual((win.later.text(), win.later.property('classic')), ('나중에', 'cancel'))
        hits = []
        win.update_now.connect(lambda: hits.append(1))
        win.now.click()
        self.assertEqual(hits, [1])
        self.assertFalse(win.now.isEnabled())       # no second download
        win.failed('받지 못했습니다')
        self.assertTrue(win.now.isEnabled())
        win.close()

    def test_build_folder_copy_offers_the_page(self):
        from kain_maple_translator.classic_windows import UpdateWindow
        rel = updater.latest_release(opener=opener_for(release_json()))
        win = UpdateWindow(rel, '0.4.54-R20.2', can_install=False)
        self.assertEqual(win.now.text(), '받는 페이지 열기')
        win.close()

    def test_up_to_date(self):
        from kain_maple_translator.classic_windows import UpdateWindow
        win = UpdateWindow(None, '0.4.54-R20.2')
        from PySide6.QtWidgets import QLabel
        texts = [w.text() for w in win.findChildren(QLabel)]
        self.assertIn('지금 최신 버전입니다.', texts)
        win.close()


class Install(unittest.TestCase):
    def test_silent_setup_restarts_the_app(self):
        cmd = updater.install_command(Path('C:/x/GeulClassic-Addon-Setup-v0.4.54-R20.3.exe'))
        self.assertIn('/SILENT', cmd)
        self.assertIn('/AUTOUPDATE=1', cmd)
        iss = (ROOT / 'installer' / 'GeulClassic-Addon.iss').read_text(encoding='utf-8-sig')
        self.assertIn('Check: IsAutoUpdate', iss)
        self.assertIn("{param:AUTOUPDATE|0}", iss)

    def test_only_an_installed_copy_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'app.exe'
            exe.write_bytes(b'')
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(exe)):
                self.assertIsNone(updater.installed_dir())
                (Path(tmp) / 'unins000.exe').write_bytes(b'')
                self.assertEqual(updater.installed_dir(), Path(tmp).resolve())
        self.assertIsNone(updater.installed_dir())   # source run

    def test_settings_switch_persists(self):
        from kain_maple_translator.core import load_config, save_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            cfg = load_config(path)
            self.assertTrue(cfg['update_check'])
            cfg['update_check'] = False
            save_config(cfg, path)
            self.assertFalse(load_config(path)['update_check'])


if __name__ == '__main__':
    unittest.main()
