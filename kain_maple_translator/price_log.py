"""Free Market price log (R18): item + price pairs from trade chat.

Only explicit S>/B> (WTS/WTB/selling/buying) posts with a k/m/b meso price
are recorded. Unknown words are kept as typed; nothing is guessed. The same
seller repeating the same megaphone within 10 minutes counts once.
"""
from __future__ import annotations

import os
import re
import sqlite3
import statistics
import tempfile
import threading
import time
from pathlib import Path

_MARKER = re.compile(r'(?i)(?:^|(?<=[\s·,|/(]))(?:(S|B)\s*>+|WT(S|B)\b|(sell)(?:ing)?\b|(buy)(?:ing)?\b)')
_PRICE = re.compile(r'(?i)(?<![\w.])(\d+(?:[.,]\d+)?)\s*(?:([kmb])(?![a-z])(?:\s*(?:ea|each))?|mesos?\s*(?:ea|each)?\b|(?:ea|each)\b)')
_DROP = re.compile(r'(?i)\b(?:for|at|obo|firm|only|pm|pmo|ea|each|c/o|a/w|s/b|b/o|h/o|co|aw|sb|'
                   r'price|offer|offers|me|w|or|and|my|the|a|an|cheap|clean|new|x\d+|\d+)\b')


def db_path() -> Path:
    root = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME') or tempfile.gettempdir()
    return Path(root)/'KAINMapleTranslator'/'price-log.sqlite3'


def _mesos(amount: str, unit: str | None) -> int | None:
    try:
        value = float(amount.replace(',', '.'))
    except ValueError:
        return None
    # '200 ea' / '750 meso': plain mesos
    value *= {'k': 1e3, 'm': 1e6, 'b': 1e9}[unit.lower()] if unit else 1
    return int(round(value)) if 100 <= value <= 50e9 else None


def _clean_item(text: str) -> str:
    text = re.sub(r'[@~!?:;=*#"]+', ' ', text)
    text = re.sub(r'[\[\]()]', ' ', text)
    text = _DROP.sub(' ', text)
    words = [w for w in text.replace(',', ' ').split() if re.search(r'[A-Za-z가-힣]', w)]
    return ' '.join(words[-5:]).strip(' -.')


def item_key(name: str) -> str:
    return re.sub(r'[^0-9a-z가-힣]+', ' ', name.casefold()).strip()


def extract_prices(original: str) -> list[tuple[str, str, int]]:
    """[(side 'S'|'B', item, mesos)] from one chat line."""
    from .chat_cleanup import prepare_chat
    text = prepare_chat(original or '')
    if re.search(r'(?i)\bnx\b', text) and re.search(r'(?i)\d\s*k\s*nx\b|\bnx\s*\d', text):
        return []   # Nexon cash amounts, not mesos
    marks = list(_MARKER.finditer(text))
    if not marks:
        return []
    out = []
    for n, mark in enumerate(marks):
        side = 'S' if (mark.group(1) or mark.group(2) or '').upper() == 'S' or mark.group(3) else 'B'
        body = text[mark.end():marks[n+1].start() if n+1 < len(marks) else len(text)]
        label = None
        before = text[max(0, (marks[n-1].end() if n else 0)):mark.start()]
        link = re.search(r'\[([^\[\]]{3,60})\]', body) or re.search(r'\[([^\[\]]{3,60})\]', before)
        if link:
            label = link.group(1).strip()
        # 'B> 60% Scrolls Claw 140k Dagger 135k': the rate belongs to each item
        rate = ''
        head = re.match(r"\s*(\d+)\s*%\s*scrolls?(?![a-z])", body, re.I)
        if head:
            rate, body = ' '+head.group(1)+'%', body[head.end():]
        prices = list(_PRICE.finditer(body))
        start = 0
        for p in prices:
            mesos = _mesos(p.group(1), p.group(2))
            segment = body[start:p.start()]
            start = p.end()
            if mesos is None:
                continue
            item = _clean_item(re.split(r'[,/·|]', segment)[-1])
            weak = not item or len(re.sub(r'[^A-Za-z가-힣]', '', item)) < 3
            if weak and label:
                item, weak = label, False
            if weak:
                continue
            out.append((side, item+rate, mesos))
    return out


def _korean_label(item: str) -> str:
    try:
        from .megaphone_item_translation import localized_item_text
        from .user_glossary import glossary_leftover
        from .chat_cleanup import polish_leftover
        ko = localized_item_text(item)
        ko = polish_leftover(ko+' 팝니다')
        ko = re.sub(r'\s*팝니다\.?$', '', ko).strip()
        ko = glossary_leftover(item, ko)          # mokbi -> 목비 표창
        return ko if ko and ko.casefold() != item.casefold() else ''
    except Exception:
        return ''


from functools import lru_cache


@lru_cache(maxsize=4096)
def _cached_label(item: str) -> str:
    return _korean_label(item)


class PriceLog:
    def __init__(self, path: Path | None = None, clock=time.time):
        self.path = Path(path or db_path())
        self.clock = clock
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS prices(ts REAL, side TEXT, item_key TEXT, item TEXT,'
                       ' korean TEXT, price INTEGER, nickname TEXT, source TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS prices_item ON prices(item_key, ts)')

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=5)

    def record(self, nickname: str, original: str) -> int:
        rows = extract_prices(original)
        if not rows:
            return 0
        now = self.clock()
        added = 0
        with self._lock, self._connect() as db:
            for side, item, price in rows:
                key = item_key(item)
                dup = db.execute('SELECT 1 FROM prices WHERE item_key=? AND price=? AND side=? AND nickname=? AND ts>?',
                                 (key, price, side, nickname or '', now-600)).fetchone()
                if dup:
                    continue
                db.execute('INSERT INTO prices VALUES(?,?,?,?,?,?,?,?)',
                           (now, side, key, item, _korean_label(item), price, nickname or '', (original or '')[:300]))
                added += 1
        return added

    def summary(self, search: str = '', days: float = 7.0, limit: int = 300) -> list[dict]:
        """Per item: sell/buy counts, low/median/high, last price and time."""
        since = self.clock()-days*86400
        term = '%'+item_key(search)+'%' if search.strip() else '%'
        with self._lock, self._connect() as db:
            rows = db.execute('SELECT ts, side, item_key, item, korean, price FROM prices'
                              ' WHERE ts>=? AND (item_key LIKE ? OR korean LIKE ?) ORDER BY ts',
                              (since, term, '%'+search.strip()+'%' if search.strip() else '%')).fetchall()
        groups: dict[str, dict] = {}
        for ts, side, key, item, korean, price in rows:
            g = groups.setdefault(key, {'item': item, 'korean': '', 'S': [], 'B': [], 'last': 0, 'last_price': 0,
                                        'last_side': side})
            g[side].append(price)
            if ts >= g['last']:
                g['last'], g['last_price'], g['last_side'] = ts, price, side
                g['item'] = item
        for g in groups.values():
            g['korean'] = _cached_label(g['item'])
        out = []
        for key, g in groups.items():
            def stats(values):
                if not values:
                    return None
                return (min(values), int(statistics.median(values)), max(values), len(values))
            out.append({'key': key, 'item': g['item'], 'korean': g['korean'], 'sell': stats(g['S']),
                        'buy': stats(g['B']), 'last': g['last'], 'last_price': g['last_price'],
                        'last_side': g['last_side'], 'count': len(g['S'])+len(g['B'])})
        out.sort(key=lambda r: (-r['count'], -r['last']))
        return out[:limit]

    def clear(self):
        with self._lock, self._connect() as db:
            db.execute('DELETE FROM prices')


def money(value: int | None) -> str:
    if not value:
        return '—'
    from .hunt_extras import format_amount
    return format_amount(value)
