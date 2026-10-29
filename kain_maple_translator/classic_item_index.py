"""Classic MapleStory item names indexed by in-game ID, not a MeowDB scraper.

Bundled English v83 client names are from an independent public WZ snapshot.
Optional Korean XML exports use the SAME item ID; unmatched records remain
English instead of being labelled as an official Korean name. Existing curated
manual catalog wins over this generated index.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path


def bundled_index_path() -> Path:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'resources' / 'item-ids' / 'gms-v83-index.json'


def synced_names_path() -> Path:
    from .item_catalog import catalog_path
    return catalog_path().with_name('gms-kms-item-names.json')


def _safe_synced_rows(path: Path) -> list[dict]:
    """Local names from explicit GMS/KMS sync, never fetched during OCR."""
    try:
        if path.stat().st_size > 8_000_000:
            return []
        obj=json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(obj,dict) or obj.get('source')!='maplestory.io'
                or not isinstance(obj.get('items'),list)):
            return []
        return obj['items'][:100000]
    except (OSError,ValueError,TypeError):
        return []


def meowdb_path() -> Path:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'resources' / 'meowdb' / 'meowdb-items-ko.json'


def mcw_pairs() -> list[tuple[str, str]]:
    """(English, Korean) names from Classic World's own client data
    (resources/item-info, scripts/fetch_item_info.py)."""
    try:
        import sqlite3
        from .item_info import db_path
        path = db_path()
        if not path.exists():
            return []
        con = sqlite3.connect('file:' + path.as_posix() + '?mode=ro&immutable=1', uri=True)
        try:
            rows = con.execute("SELECT name, name_ko FROM items WHERE name_ko != '' AND name_ko != name").fetchall()
        finally:
            con.close()
        return [((en or '').strip(), (ko or '').strip()) for en, ko in rows
                if en and re.search('[가-힣]', ko or '')]
    except Exception:
        return []


def meowdb_pairs() -> list[tuple[str, str]]:
    """(English, Korean) item names collected by scripts/fetch_meowdb_items.py."""
    try:
        obj = json.loads(meowdb_path().read_text(encoding='utf-8'))
        rows = obj.get('items', []) if isinstance(obj, dict) else []
    except (OSError, ValueError):
        return []
    out = []
    for row in rows[:50000]:
        en = str(row.get('en') or '').strip()
        ko = str(row.get('ko') or '').strip()
        if re.search(r'[A-Za-z]', en) and re.search('[가-힣]', ko) and len(en) <= 150 and len(ko) <= 150:
            out.append((en, ko))
    return out


def _safe_load(path: Path) -> list[dict]:
    try:
        if path.stat().st_size > 12_000_000:
            return []
        value = json.loads(path.read_text(encoding='utf-8'))
        return value['items'] if isinstance(value, dict) and isinstance(value.get('items'),list) else []
    except (OSError, ValueError, KeyError):
        return []


class ClassicItemIndex:
    def __init__(self, rows, synced_rows=None):
        self.by_id = {}
        self.by_en = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get('item_id') or '')
            en = str(row.get('name_en') or '').strip()
            ko = str(row.get('name_ko') or '').strip()
            if not item_id.isdecimal() or not en or len(en)>150 or len(ko)>150:
                continue
            self.by_id[item_id] = {'name_en':en, 'name_ko':ko}
            # Avoid matching generic words such as 'Top', 'Hat', 'Overall' in free chat.
            if len(en) >= 7 and re.search(r'[a-zA-Z]',en) and (len(en.split())>1 or len(en)>=12):
                self.by_en.setdefault(en.casefold(),(en,ko))
        # Explicit maplestory.io GMS/KMS ID join: contains only pairs with
        # unique English-title -> Korean-name matches. Keep any previously
        # verified legacy translation if it already exists.
        self.synced_count=0
        for row in synced_rows or ():
            if not isinstance(row,dict): continue
            ident=str(row.get('item_id') or '')
            en=str(row.get('name_en') or '').strip()
            ko=str(row.get('name_ko') or '').strip()
            if not ident.isdecimal() or not re.search(r'[a-zA-Z]',en) or not re.search(r'[가-힣]',ko):
                continue
            if not (3 <= len(en) <= 150 and 1 <= len(ko) <= 150): continue
            original=self.by_id.get(ident)
            if not original or not original.get('name_ko'):
                self.by_id[ident]={'name_en':en,'name_ko':ko}
            if len(en)>=7 and (len(en.split())>1 or len(en)>=12):
                key=en.casefold()
                old=self.by_en.get(key)
                if not old or not old[1]:
                    self.by_en[key]=(en,ko)
                    self.synced_count += 1
        # Classic World item names (resources/meowdb): meowdb's Korean names
        # plus GMS->KMS names joined by item ID. They fill names that have no
        # Korean yet; a name already verified/curated here is kept.
        self.meowdb_count=0
        from .market_item_terms import MARKET_NAMES
        curated={re.sub(r'[^a-z0-9]+',' ',k).strip() for k in MARKET_NAMES}
        for en,ko in meowdb_pairs():
            if re.sub(r'[^a-z0-9]+',' ',en.lower()).strip() in curated:
                continue   # the user's own wording (market_item_terms) wins
            for variant in {en, en.replace('-', ' ')}:
                if len(variant) >= 5 and (len(variant.split())>1 or len(variant)>=8):
                    old=self.by_en.get(variant.casefold())
                    if not old or not old[1]:
                        self.by_en[variant.casefold()]=(variant,ko)
                        self.meowdb_count += 1
        # R19: Classic World's own Korean client names (resources/item-info,
        # maplestory.io MCW) fill names that are still missing.
        self.mcw_count=0
        for en,ko in mcw_pairs():
            if re.sub(r'[^a-z0-9]+',' ',en.lower()).strip() in curated:
                continue
            if len(en)>=7 and (len(en.split())>1 or len(en)>=12):
                old=self.by_en.get(en.casefold())
                if not old or not old[1]:
                    self.by_en[en.casefold()]=(en,ko)
                    self.mcw_count += 1
        # Public Classic World wiki names complement the legacy v83 index.
        # The publisher's export is English-first. Do not claim Korean names.
        from .open_classic_data import item_name_rows
        self.open_classic_count=0
        for row in item_name_rows():
            name=row["name_en"]
            if len(name) >= 7 and (len(name.split())>1 or len(name)>=12):
                if name.casefold() not in self.by_en:
                    self.by_en[name.casefold()] = (name, "")
                    self.open_classic_count += 1
        # A prefix bucket avoids recompiling a giant 10K-alternation regex.
        self.prefix = {}
        for en,ko in self.by_en.values():
            self.prefix.setdefault(en[0].lower(),[]).append((en,ko))
        for entries in self.prefix.values():
            entries.sort(key=lambda x:-len(x[0]))

    @property
    def count(self):
        return len(self.by_id)

    @property
    def localized_count(self):
        return sum(1 for row in self.by_id.values() if row['name_ko'])

    def find(self,text,max_hits=4):
        result=[]; used=[]
        for i,c in enumerate(text):
            if len(result)>=max_hits: break
            if (i>0 and (text[i-1].isalnum() or text[i-1]=='_')) or any(a<=i<b for a,b,*_ in used):
                continue
            for name,ko in self.prefix.get(c.lower(),[]):
                end=i+len(name)
                if text[i:end].casefold() != name.casefold(): continue
                if end<len(text) and (text[end].isalnum() or text[end]=='_'): continue
                used.append((i,end,name,ko)); result.append((i,end,name,ko)); break
        return result

    def replace_verified(self, text):
        matches=self.find(text)
        for start,end,en,ko in reversed(matches):
            if ko: text=text[:start]+ko+text[end:]
        return text



# If the v83 client contains an English title but no verified Korean string,
# optionally use the offline model once and remember its result. This is
# explicitly AI-generated, not a verified official Korean item name.
_AUTOTRANSLATIONS = None


def _auto_cache_path() -> Path:
    root = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME')
    if not root:
        try: root = str(Path.home() / '.local/share')
        except (RuntimeError, OSError): root = tempfile.gettempdir()
    return Path(root) / 'KAINMapleTranslator' / 'item-ai-draft-cache.json'


def _auto_cache() -> dict[str,str]:
    global _AUTOTRANSLATIONS
    if _AUTOTRANSLATIONS is not None:
        return _AUTOTRANSLATIONS
    path = _auto_cache_path()
    try:
        if path.stat().st_size > 4_000_000: raise ValueError('oversize')
        value = json.loads(path.read_text(encoding='utf-8'))
        _AUTOTRANSLATIONS = value if isinstance(value,dict) else {}
    except (OSError,ValueError):
        _AUTOTRANSLATIONS={}
    return _AUTOTRANSLATIONS


def _store_auto_cache(data):
    path=_auto_cache_path()
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        tmp.replace(path)
    except OSError:
        pass  # Read-only user profile: translation still works for this session


def replace_unverified_item_names(text: str, translate_fn, max_new=2):
    """Translate exact OLD-GMS item titles only in a trade listing.

    This does not perform blind token replacement in everyday chat; unreliable
    input and names that cannot be translated are left intact. Previously
    translated entries are cached, avoiding recurring model work.
    """
    if not re.search(r'팝니다|삽니다|판매|구매|제시|거래',text):
        return text
    index=current_index()
    cache=_auto_cache()
    hits=index.find(text,max_hits=4)
    new_count=0; changed=False
    for start,end,name,verified_ko in reversed(hits):
        if verified_ko:
            continue
        key=name.casefold()
        translated=cache.get(key)
        if translated is None and new_count < max_new:
            new_count+=1
            try:
                guessed=str(translate_fn(name)).strip()
                # Never treat an untranslated source / made-up punctuation as Korean.
                translated=(guessed if re.search(r'[가-힣]',guessed) and
                            len(guessed)<180 else name)
            except Exception as ex:
                # Fast/batch planning is not a failed item translation. Let
                # its suspension escape without poisoning the persistent DB.
                if getattr(ex, 'defer_translation', False):
                    raise
                continue
            if translated == name:
                continue  # failed inference must be retryable next time
            cache[key]=translated
            changed=True
        if translated and translated!=name:
            text=text[:start]+translated+text[end:]
    if changed:
        _store_auto_cache(cache)
    return text

_CACHED=None
_CACHED_KEY=None

def current_index():
    global _CACHED,_CACHED_KEY
    path=bundled_index_path()
    local=synced_names_path()
    def stamp(p):
        try: return (str(p),p.stat().st_mtime_ns,p.stat().st_size)
        except OSError: return (str(p),None,None)
    key=(stamp(path),stamp(local))
    if _CACHED is None or key!=_CACHED_KEY:
        _CACHED=ClassicItemIndex(_safe_load(path),_safe_synced_rows(local))
        _CACHED_KEY=key
    return _CACHED


def index_state():
    index=current_index()
    return (f'구버전 ID {index.count:,}개 / 영문 공개 DB 추가 {index.open_classic_count:,}개'
            f' / 한글 ID 대응 {index.localized_count:,}개 (API 후보 {index.synced_count:,}개)')
