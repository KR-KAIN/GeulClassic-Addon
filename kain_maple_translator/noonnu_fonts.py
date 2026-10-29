"""Resolve Noonnu font-page URLs to app-local fonts without a manual download.

Only a safe subset of HTTPS font hosts is allowed; never access local/private URLs.
Fonts are cached privately, NOT redistributed with the app. Verify each font license.
"""
from __future__ import annotations
import hashlib
import html
import io
import ipaddress
import os
from pathlib import Path
import re
import socket
import tempfile
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

MAX_CSS = 2_000_000
MAX_FONT = 18_000_000
HOSTS = ('noonnu.cc','fonts.googleapis.com','fonts.gstatic.com',
         'cdn.jsdelivr.net','fastly.jsdelivr.net','raw.githubusercontent.com',
         'cdn.jsdelivr.net','cdn.nhnfonts.com')


class FontUrlError(ValueError):
    pass


def checked_url(address: str, *, page=False) -> str:
    address = str(address or '').strip()
    u = urlsplit(address)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None,443):
        raise FontUrlError('HTTPS 눈누 폰트 주소만 사용할 수 있습니다.')
    host=u.hostname.lower().rstrip('.')
    if page and host not in ('noonnu.cc','www.noonnu.cc'):
        raise FontUrlError('폰트 페이지 주소는 noonnu.cc만 지원합니다.')
    if not any(host==base or host.endswith('.'+base) for base in HOSTS):
        raise FontUrlError('허용되지 않은 폰트 배포 주소입니다: '+host)
    # Do not fetch loopback/intranet: no address bypass via URL text.
    try:
        ip=ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not ip.is_global: raise FontUrlError('내부 네트워크 주소는 사용할 수 없습니다.')
    if len(address)>2048: raise FontUrlError('주소가 너무 깁니다.')
    return address


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(address: str, *, limit=MAX_CSS) -> bytes:
    checked_url(address)
    request=Request(address,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
                                     'Accept':'text/css,text/html,application/octet-stream,*/*'})
    with build_opener(_SafeRedirect).open(request,timeout=12) as rsp:
        size=int(rsp.headers.get('Content-Length') or 0)
        if size>limit: raise FontUrlError('폰트 파일 크기가 허용 범위를 넘었습니다.')
        content=rsp.read(limit+1)
        if len(content)>limit: raise FontUrlError('폰트 데이터가 너무 큽니다.')
        return content


def font_css_candidates(text: str, base_url: str) -> list[str]:
    """Resolve @import and src:url(...) from Noonnu page or CSS."""
    clean=html.unescape(text).replace('\\/','/')
    # source HTML sometimes contains CSS in JSON quoted string
    urls=[]
    for match in re.finditer(r'@import\s+(?:url\()?\s*[\'\"]?([^\'\"\s);]+)',clean,re.I):
        urls.append(urljoin(base_url,match.group(1)))
    for match in re.finditer(r'url\(\s*[\'\"]?([^\'\")]+)',clean,re.I):
        urls.append(urljoin(base_url,match.group(1).strip()))
    return list(dict.fromkeys(urls))


def _is_font_url(url: str) -> bool:
    return bool(re.search(r'\.(?:woff2?|ttf|otf)(?:[?#]|$)', url, re.I))


def _resolve(url: str) -> list[str]:
    checked_url(url)
    if _is_font_url(url): return [url]
    visited=set()
    def expand(current: str, depth: int):
        if depth>3 or current in visited: return []
        visited.add(current)
        blob=_fetch(current).decode('utf-8','replace')
        urls=font_css_candidates(blob,current)
        fonts=[link for link in urls if _is_font_url(link)]
        css=[link for link in urls if re.search(r'(?:\.css(?:[?#]|$)|fonts\.googleapis\.com/css)',link,re.I)]
        for style_url in css[:5]:
            try: fonts.extend(expand(style_url,depth+1))
            except (FontUrlError,OSError): continue
        return list(dict.fromkeys(fonts))
    return expand(url,0)


def _sfnt_font(data: bytes) -> bytes:
    if data[:4] in (b'\x00\x01\x00\x00', b'OTTO',b'true',b'ttcf'): return data
    if data[:4] not in (b'wOFF',b'wOF2'): raise FontUrlError('지원하지 않는 폰트 파일 형식입니다.')
    try:
        from fontTools.ttLib import TTFont
        raw=TTFont(io.BytesIO(data)); raw.flavor=None
        output=io.BytesIO();raw.save(output)
        return output.getvalue()
    except Exception as ex:
        raise FontUrlError('웹폰트 변환 실패 (fonttools/brotli 확인): '+str(ex)) from ex


def cached_font_from_noonnu(url: str, cache_dir: Path | None=None) -> Path:
    checked_url(url, page=not _is_font_url(url) and not re.search(r'\.css(?:[?#]|$)',url,re.I))
    if cache_dir is None:
        base=os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or str(Path(tempfile.gettempdir())/'KainFontCache')
        cache_dir=Path(base)/'KAINMapleTranslator'/'webfonts'
    cache_dir.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(url.encode('utf-8')).hexdigest()[:22]
    dest=cache_dir/(key+'.ttf')
    if dest.is_file() and dest.stat().st_size>1000:return dest
    candidates=_resolve(url)
    if not candidates:raise FontUrlError('페이지에서 웹폰트 파일을 찾지 못했습니다. 웹폰트가 제공되지 않는 폰트일 수 있습니다.')
    error=None
    # Google Fonts Korean may be split into many subsets. Prefer larger Korean subset;
    # ordinary Noonnu files usually include full Korean coverage.
    for item in candidates[:30]:
        try:
            checked_url(item)
            data=_fetch(item,limit=MAX_FONT)
            sfnt=_sfnt_font(data)
            if len(sfnt)<1000:continue
            tmp=dest.with_suffix('.partial')
            tmp.write_bytes(sfnt)
            tmp.replace(dest)
            return dest
        except (FontUrlError,OSError) as ex:
            error=ex
    raise FontUrlError('폰트 적용 실패: '+str(error or '사용 가능한 파일이 없습니다'))
