"""User-authorized English/Korean item catalog importer. No web scraping.

Never download NiaMeowDB data without its owner's prior permission.
The app imports ONLY a file the user supplies and is entitled to use.
"""
from __future__ import annotations

import csv
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 50000
REQUIRED_COLUMNS = ('name_en', 'name_ko')

class CatalogError(ValueError):
    pass


def catalog_path() -> Path:
    root = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME')
    if not root:
        try:
            root = str(Path.home() / '.local' / 'share')
        except RuntimeError:
            root = tempfile.gettempdir()
    return Path(root) / 'KAINMapleTranslator' / 'authorized-items.json'


def _norm(value: str) -> str:
    return unicodedata.normalize('NFKC', str(value)).casefold().strip()


def _read_rows(filename: Path) -> list[dict]:
    if not filename.is_file():
        raise CatalogError('선택한 파일을 찾을 수 없습니다.')
    if filename.stat().st_size > MAX_BYTES:
        raise CatalogError('목록 파일은 25MB 이하여야 합니다.')
    if filename.suffix.lower() == '.csv':
        with filename.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
    elif filename.suffix.lower() == '.json':
        try:
            obj=json.loads(filename.read_text(encoding='utf-8-sig'))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CatalogError('유효한 UTF-8 JSON이 아닙니다.') from exc
        rows=obj.get('items') if isinstance(obj,dict) else obj
    else:
        raise CatalogError('CSV 또는 JSON 파일만 지원합니다.')
    if not isinstance(rows,list) or len(rows) > MAX_ROWS:
        raise CatalogError('아이템 목록 형식 또는 50,000개 제한을 확인하세요.')
    if not rows:
        raise CatalogError('아이템 목록이 비어 있습니다.')
    cleaned=[]
    mapping={}
    for ix,row in enumerate(rows,1):
        if not isinstance(row,dict):
            raise CatalogError(f'{ix}번 항목이 객체 형식이 아닙니다.')
        en=str(row.get('name_en') or row.get('english') or '').strip()
        ko=str(row.get('name_ko') or row.get('korean') or '').strip()
        if not en or not ko or len(en)>180 or len(ko)>180:
            raise CatalogError(f'{ix}번 항목의 영어명/한국어명을 확인하세요.')
        entry={'name_en':en,'name_ko':ko}
        for key in ('item_id','category'):
            if row.get(key) not in (None,''):
                entry[key]=str(row[key])[:100]
        raw_alias=row.get('aliases_en') or ''
        if isinstance(raw_alias,list):
            aliases=[str(a).strip() for a in raw_alias]
        else:
            aliases=[a.strip() for a in re.split(r'[|;]',str(raw_alias))]
        aliases=[a for a in aliases if a and len(a)<=180][:25]
        if aliases:
            entry['aliases_en']=aliases
        for alias in (en,*aliases):
            key=_norm(alias)
            if len(key)<3: continue  # very short words are too ambiguous
            if key in mapping and mapping[key]!=ko:
                raise CatalogError(f'영문 별칭 충돌: {alias} (서로 다른 한국어 이름)')
            mapping[key]=ko
        cleaned.append(entry)
    return cleaned


class ItemCatalog:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        mapping={}
        for item in rows:
            for alias in (item['name_en'],*item.get('aliases_en',[])):
                key=_norm(alias)
                if len(key)>=3:
                    mapping[key] = item['name_ko']
        self.mapping=mapping
        self._rx = None
        if mapping:
            # Prefer longer complete names; do not replace substrings of nicknames.
            expressions=sorted(mapping, key=lambda s:(-len(s),s))
            self._rx=re.compile(r'(?<!\w)(?:'+ '|'.join(re.escape(k) for k in expressions) +r')(?!\w)', re.I)

    @property
    def count(self) -> int:
        return len(self.rows)

    def lookup(self, english: str) -> str|None:
        return self.mapping.get(_norm(english))

    def replace(self, text: str) -> str:
        if not self._rx or not text: return text
        return self._rx.sub(lambda m: self.mapping.get(_norm(m.group(0)),m.group(0)),text)


_CATALOG: ItemCatalog|None=None
_CACHE_STAMP: tuple|None=None

def current_catalog() -> ItemCatalog:
    global _CATALOG,_CACHE_STAMP
    p=catalog_path()
    try:
        stat=p.stat()
        stamp=(str(p),stat.st_mtime_ns,stat.st_size)
    except OSError:
        stamp=(str(p),None,None)
    if _CATALOG is None or stamp!=_CACHE_STAMP:
        try:
            items=_read_rows(p) if p.is_file() else []
            _CATALOG=ItemCatalog(items)
        except (OSError,CatalogError):
            _CATALOG=ItemCatalog([])
        _CACHE_STAMP=stamp
    return _CATALOG


def install_catalog(filename: str|Path) -> int:
    """Import a locally obtained and authorized data file. Never fetches URLs."""
    global _CATALOG,_CACHE_STAMP
    rows=_read_rows(Path(filename))
    path=catalog_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='authorized-items-',suffix='.json',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump({'items':rows},out,ensure_ascii=False,indent=1)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    _CATALOG=None
    _CACHE_STAMP=None
    return len(rows)
