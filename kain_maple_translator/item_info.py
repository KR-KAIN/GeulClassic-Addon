"""Classic World item data for the chat item tooltip (R19).

resources/item-info/item-info.sqlite3 is built by scripts/fetch_item_info.py
from MapleStory Classic World's own client data (maplestory.io region MCW):
names (English/Korean), Korean descriptions, required level/stats/jobs,
upgrade slots, attack speed, base stats and the icon. Read-only; nothing is
downloaded while the app runs.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_LOCK = threading.Lock()


def db_path() -> Path:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'resources' / 'item-info' / 'item-info.sqlite3'


@dataclass
class ItemInfo:
    id: int
    name: str
    name_ko: str = ''
    desc: str = ''
    desc_ko: str = ''
    overall: str = ''
    category: str = ''
    sub: str = ''
    req_level: int = 0
    cash: bool = False
    req_str: int = 0
    req_dex: int = 0
    req_int: int = 0
    req_luk: int = 0
    req_pop: int = 0
    req_job: int = 0
    tuc: int = 0
    attack_speed: int = 0
    stats: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    icon: bytes = b''

    @property
    def is_equip(self) -> bool:
        return self.overall == 'Equip'

    @property
    def is_weapon(self) -> bool:
        return 'Weapon' in self.category

    def display_name(self, label: str = '') -> str:
        """The name the chat shows ([이블 스컬]) wins, then the client's Korean
        name, then English."""
        if label and re.search('[가-힣]', label):
            return label
        return self.name_ko or label or self.name

    def description(self) -> str:
        text = self.desc_ko or self.desc
        return text.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\r\n', '\n').strip()


_COLUMNS = ('id', 'name', 'name_ko', 'desc', 'desc_ko', 'overall', 'category', 'sub', 'req_level', 'cash',
            'req_str', 'req_dex', 'req_int', 'req_luk', 'req_pop', 'req_job', 'tuc', 'attack_speed',
            'stats', 'extra', 'icon')


def _key(text: str) -> str:
    """Order-free comparison key: 'Gloves Attack Scroll 60%' and
    'Scroll for Gloves for ATT 60%' still differ, but '장갑 공격력 60% 주문서'
    and '장갑 공격력 주문서 60%' match."""
    words = re.findall(r'[가-힣]+|\d+%?|[a-z]+', (text or '').casefold().replace("'", ''))
    return ' '.join(sorted(words))


class ItemInfoDB:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or db_path())
        self.ok = self.path.exists()
        self._con = None
        self._by_key: dict[str, list[int]] = {}
        self._names_en: dict[str, list[int]] = {}
        if self.ok:
            uri = 'file:' + self.path.as_posix() + '?mode=ro&immutable=1'
            self._con = sqlite3.connect(uri, uri=True, check_same_thread=False)
            for item_id, name, name_ko in self._con.execute('SELECT id, name, name_ko FROM items'):
                for text in (name, name_ko):
                    if text:
                        self._by_key.setdefault(_key(text), []).append(item_id)
                if name:
                    self._names_en.setdefault(name.casefold(), []).append(item_id)

    @property
    def count(self) -> int:
        return len(self._names_en)

    def get(self, item_id: int) -> ItemInfo | None:
        if not self._con:
            return None
        with _LOCK:
            row = self._con.execute(f'SELECT {",".join(_COLUMNS)} FROM items WHERE id=?', (int(item_id),)).fetchone()
        if not row:
            return None
        data = dict(zip(_COLUMNS, row))
        data['cash'] = bool(data['cash'])
        data['stats'] = json.loads(data['stats'] or '{}')
        data['extra'] = json.loads(data['extra'] or '{}')
        data['icon'] = bytes(data['icon'] or b'')
        for key in ('name_ko', 'desc', 'desc_ko'):
            data[key] = data[key] or ''
        return ItemInfo(**data)

    def _best(self, ids: list[int]) -> ItemInfo | None:
        items = [i for i in (self.get(x) for x in dict.fromkeys(ids)) if i]
        if not items:
            return None
        # a real (non-cash) equip with stats beats a cash cover of the same name
        items.sort(key=lambda i: (i.cash, not i.stats, i.id))
        return items[0]

    def find_name(self, name: str) -> ItemInfo | None:
        name = re.sub(r'\s+', ' ', (name or '').strip().strip('[]')).strip()
        if len(name) < 2 or not self.ok:
            return None
        ids = self._names_en.get(name.casefold()) or self._by_key.get(_key(name))
        if ids:
            return self._best(ids)
        english = _korean_to_english(name)
        if english:
            ids = self._names_en.get(english.casefold()) or self._by_key.get(_key(english))
            if ids:
                return self._best(ids)
        return None

    def lookup(self, label: str, original: str = '', index: int = -1) -> ItemInfo | None:
        """The [label] a chat row shows (Korean or English). The row's
        original English text decides when the label is our translation."""
        hit = self.find_name(label)
        if hit:
            return hit
        labels = re.findall(r'\[([^\[\]\n]+)\]', original or '')
        if labels:
            if 0 <= index < len(labels):
                hit = self.find_name(labels[index])
                if hit:
                    return hit
            if len(labels) == 1:
                return self.find_name(labels[0])
        return None


@lru_cache(maxsize=1)
def _korean_names() -> dict[str, str]:
    """Korean label -> English name, from every name table the translator
    uses (curated market words, meowdb, the ID index)."""
    out: dict[str, str] = {}
    try:
        from .classic_item_index import current_index
        for en, ko in current_index().by_en.values():
            if ko:
                out.setdefault(_key(ko), en)
    except Exception:
        pass
    try:
        from .market_item_terms import MARKET_NAMES
        for en, ko in MARKET_NAMES.items():
            out[_key(ko)] = en
    except Exception:
        pass
    return out


def _korean_to_english(name: str) -> str:
    if not re.search('[가-힣]', name):
        return ''
    return _korean_names().get(_key(name), '')


_DB: ItemInfoDB | None = None


def current_db() -> ItemInfoDB:
    global _DB
    if _DB is None:
        _DB = ItemInfoDB()
    return _DB
