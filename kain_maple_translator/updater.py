"""Check GitHub for a newer release and install it (R20.2).

The only server is the project's own GitHub releases page
(api.github.com/repos/KR-KAIN/GeulClassic-Addon/releases/latest). Nothing
about the user or the game is sent. A setup file is installed only when its
SHA-256 matches the digest GitHub lists for that release asset.

An installed copy (Inno Setup put unins000.exe next to the exe) updates
itself: the new setup runs with /SILENT /AUTOUPDATE=1 and starts the app again
when done. A copy run from a build folder only offers the release page.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = '0.4.54-R20.2'
REPO = 'KR-KAIN/GeulClassic-Addon'
API_LATEST = f'https://api.github.com/repos/{REPO}/releases/latest'
DOWNLOAD_PREFIX = f'https://github.com/{REPO}/releases/download/'
ASSET = re.compile(r'^GeulClassic-Addon-Setup-v[\w.\-]+\.exe$')
_VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)-R(\d+)(?:\.(\d+))?', re.I)


def parse_version(text: str) -> tuple[int, ...] | None:
    """'v0.4.54-R20.2' -> (0, 4, 54, 20, 2); 'v0.4.54-R19' -> (0, 4, 54, 19, 0)."""
    m = _VERSION.search(text or '')
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())


def is_newer(remote: str, local: str | None = None) -> bool:
    a, b = parse_version(remote), parse_version(local or APP_VERSION)
    return bool(a and b and a > b)


def notes_for_app(body: str) -> str:
    """The release notes without the parts meant for the download page:
    the install steps, the SHA256 check and the copyright footer."""
    text = (body or '').replace('\r\n', '\n').split('\n---', 1)[0]
    parts = re.split(r'(?m)^(?=## )', text)
    keep = [p for p in parts if not re.match(r'## (설치|파일 확인)', p)]
    return re.sub(r'\n{3,}', '\n\n', ''.join(keep)).strip()


@dataclass(frozen=True)
class Release:
    version: str          # '0.4.54-R20.3'
    tag: str
    name: str
    page: str             # the release page on GitHub
    asset_name: str
    asset_url: str
    size: int
    sha256: str           # lowercase hex, '' when GitHub lists none
    notes: str = ''       # what changed (Markdown), for the UPDATE window


def _open(url: str, timeout: float, opener=None):
    req = urllib.request.Request(url, headers={
        'User-Agent': f'GeulClassic-Addon/{APP_VERSION} (update check)',
        'Accept': 'application/vnd.github+json'})
    return (opener or urllib.request.urlopen)(req, timeout=timeout)


def latest_release(timeout: float = 8, opener=None) -> Release | None:
    """The newest published release with a setup file, or None."""
    with _open(API_LATEST, timeout, opener) as r:
        data = json.loads(r.read().decode('utf-8'))
    tag = str(data.get('tag_name') or '')
    if data.get('draft') or data.get('prerelease') or not parse_version(tag):
        return None
    for asset in data.get('assets') or []:
        name = str(asset.get('name') or '')
        url = str(asset.get('browser_download_url') or '')
        if ASSET.match(name) and url.startswith(DOWNLOAD_PREFIX):
            digest = str(asset.get('digest') or '')
            sha = digest.split(':', 1)[1].lower() if digest.lower().startswith('sha256:') else ''
            m = _VERSION.search(tag)
            return Release(version=m.group(0), tag=tag, name=str(data.get('name') or tag),
                           page=str(data.get('html_url') or f'https://github.com/{REPO}/releases'),
                           asset_name=name, asset_url=url, size=int(asset.get('size') or 0), sha256=sha,
                           notes=notes_for_app(str(data.get('body') or '')))
    return None


def check(timeout: float = 8, opener=None) -> Release | None:
    """A release newer than this app, or None (also when offline)."""
    release = latest_release(timeout, opener)
    return release if release and is_newer(release.version) else None


def installed_dir() -> Path | None:
    """The folder of an installed copy (Inno Setup's uninstaller sits next to
    the exe); None for a copy run from a build folder or from source."""
    if not getattr(sys, 'frozen', False):
        return None
    folder = Path(sys.executable).resolve().parent
    return folder if (folder / 'unins000.exe').exists() else None


def updates_dir() -> Path:
    root = os.environ.get('LOCALAPPDATA') or str(Path.home())
    return Path(root) / 'KAINMapleTranslator' / 'updates'


class UpdateError(RuntimeError):
    pass


def download(release: Release, dest: Path | None = None, progress=None, opener=None,
             timeout: float = 60) -> Path:
    """Fetch the setup file and check its SHA-256; progress(done, total)."""
    if not release.sha256:
        raise UpdateError('GitHub에 파일 확인값(SHA256)이 없어 설치하지 않습니다')
    folder = Path(dest or updates_dir())
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('GeulClassic-Addon-Setup-*'):
        try:
            old.unlink()
        except OSError:
            pass
    target = folder / release.asset_name
    part = target.with_suffix('.part')
    digest = hashlib.sha256()
    done = 0
    with _open(release.asset_url, timeout, opener) as r, open(part, 'wb') as out:
        total = int(r.headers.get('Content-Length') or release.size or 0) if hasattr(r, 'headers') else release.size
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if digest.hexdigest() != release.sha256:
        part.unlink(missing_ok=True)
        raise UpdateError('받은 파일이 GitHub의 확인값과 달라 설치하지 않습니다')
    part.replace(target)
    return target


def install_command(setup: Path) -> list[str]:
    # /SILENT shows only the progress bar; /AUTOUPDATE=1 makes the setup
    # start the app again when it is done (installer/GeulClassic-Addon.iss)
    return [str(setup), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
            '/CLOSEAPPLICATIONS', '/AUTOUPDATE=1']


def launch_installer(setup: Path) -> None:
    """Start the setup on its own; the caller then quits the app."""
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(install_command(setup), close_fds=True,
                     creationflags=flags if os.name == 'nt' else 0)
