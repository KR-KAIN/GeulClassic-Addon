"""Build resources/item-info/item-info.sqlite3 for the item tooltip (R19).

Source: the public maplestory.io API, region MCW version 1 = MapleStory
Classic World itself (not GMS v83: e.g. Iron Ball needs STR 35 / DEX 15 and
has 40 attack in Classic World, exactly what the game's tooltip shows).

For every Classic World item: English + Korean name, Korean description,
category, required level/stats/jobs, upgrade slots (tuc), attack speed, all
'inc*' stats and the icon (PNG bytes).

The app never downloads anything at run time; it only reads this file.
Usage:  python scripts/fetch_item_info.py [--workers 6]
"""
from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'resources' / 'item-info' / 'item-info.sqlite3'
API = 'https://maplestory.io/api/MCW/1/item'
UA = {'User-Agent': 'GeulClassic-Addon item tooltip builder (offline cache)'}


def get(url: str, tries: int = 4) -> bytes:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    return b''


def schema(con):
    con.execute('''CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY, name TEXT, name_ko TEXT, desc TEXT, desc_ko TEXT,
        overall TEXT, category TEXT, sub TEXT, req_level INTEGER, cash INTEGER,
        req_str INTEGER, req_dex INTEGER, req_int INTEGER, req_luk INTEGER, req_pop INTEGER,
        req_job INTEGER, tuc INTEGER, attack_speed INTEGER, stats TEXT, extra TEXT, icon BLOB)''')
    con.execute('CREATE INDEX IF NOT EXISTS items_name ON items(name COLLATE NOCASE)')
    con.execute('CREATE INDEX IF NOT EXISTS items_name_ko ON items(name_ko)')
    con.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)')


def fix_korean(con, workers: int = 6):
    """Fill missing Korean descriptions (items that have an English one)."""
    todo = [r[0] for r in con.execute(
        "SELECT id FROM items WHERE desc != '' AND (desc_ko IS NULL OR desc_ko = '')")]
    print('Korean descriptions to fill', len(todo), flush=True)
    lock = threading.Lock()

    def work(item_id):
        full = json.loads(get(f'{API}/{item_id}?locale=ko'))
        nested = full.get('description') if isinstance(full.get('description'), dict) else {}
        descs = nested.get('descriptions') or {}
        names = nested.get('names') or {}
        ko = descs.get('ko') or ''
        if ko and ko == descs.get('en'):
            ko = ''
        with lock:
            con.execute('UPDATE items SET desc_ko=? WHERE id=?', (ko, item_id))
            if names.get('ko') and names.get('ko') != names.get('en'):
                con.execute("UPDATE items SET name_ko=? WHERE id=? AND (name_ko IS NULL OR name_ko='')",
                            (names['ko'], item_id))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, f in enumerate(as_completed([pool.submit(work, i) for i in todo]), 1):
            try:
                f.result()
            except Exception as exc:
                print('fail', exc, flush=True)
            if n % 500 == 0:
                with lock:
                    con.commit()
                print('korean', n, '/', len(todo), flush=True)
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--fix-korean', action='store_true', help='only fill missing Korean descriptions')
    args = ap.parse_args()
    if args.fix_korean:
        con = sqlite3.connect(OUT, check_same_thread=False)
        fix_korean(con, args.workers)
        con.execute('VACUUM')
        con.close()
        print('size', OUT.stat().st_size, flush=True)
        return 0
    listing = json.loads(get(f'{API}?startPosition=0&count=100000'))
    rows = {str(x['id']): x for x in listing if x.get('name')}
    print('Classic World items', len(rows), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(OUT, check_same_thread=False)
    schema(con)
    done = {str(r[0]) for r in con.execute('SELECT id FROM items WHERE icon IS NOT NULL')}
    todo = [i for i in rows if i not in done]
    print('to fetch', len(todo), flush=True)
    lock = threading.Lock()

    def work(item_id):
        x = rows[item_id]
        t = x.get('typeInfo') or {}
        full = json.loads(get(f'{API}/{item_id}?locale=ko'))
        meta = full.get('metaInfo') or {}
        # ?locale=ko nests the per-language names/descriptions in 'description'
        nested = full.get('description') if isinstance(full.get('description'), dict) else {}
        names = nested.get('names') or full.get('names') or x.get('names') or {}
        descs = nested.get('descriptions') or full.get('descriptions') or {}
        untranslated = set(x.get('untranslated') or [])
        name_ko = names.get('ko', '') if 'ko' not in untranslated else ''
        desc_ko = descs.get('ko', '') or ''
        if desc_ko and desc_ko == descs.get('en'):
            desc_ko = ''
        # iconRaw has no drop shadow: the tooltip adds the game's own shade
        raw = meta.get('iconRaw') or meta.get('icon')
        icon = base64.b64decode(raw) if raw else b''
        if not icon:
            try:
                icon = get(f'{API}/{item_id}/icon')
            except Exception:
                icon = b''
        stats = {k: v for k, v in meta.items() if k.startswith('inc') and isinstance(v, (int, float)) and v}
        extra = {k: meta[k] for k in ('consumeSpec', 'success', 'price', 'only', 'tradeBlock', 'quest')
                 if k in meta}
        row = (int(item_id), x.get('name', ''), name_ko, x.get('desc', '') or '', desc_ko,
               t.get('overallCategory', ''), t.get('category', ''), t.get('subCategory', ''),
               int(x.get('requiredLevel') or meta.get('reqLevel') or 0), 1 if x.get('isCash') else 0,
               int(meta.get('reqSTR') or 0), int(meta.get('reqDEX') or 0), int(meta.get('reqINT') or 0),
               int(meta.get('reqLUK') or 0), int(meta.get('reqPOP') or 0), int(meta.get('reqJob') or 0),
               int(meta.get('tuc') or 0), int(meta.get('attackSpeed') or 0),
               json.dumps(stats), json.dumps(extra, ensure_ascii=False), icon)
        with lock:
            con.execute('INSERT OR REPLACE INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', row)
        return item_id

    n = fails = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, i) for i in todo]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                fails += 1
                if fails <= 5:
                    print('fail', exc, flush=True)
            n += 1
            if n % 500 == 0:
                with lock:
                    con.commit()
                print('progress', n, '/', len(todo), 'fails', fails, flush=True)
    con.execute("INSERT OR REPLACE INTO meta VALUES('source', 'maplestory.io MCW 1 (MapleStory Classic World, public API)')")
    con.execute("INSERT OR REPLACE INTO meta VALUES('fetched', ?)", (time.strftime('%Y-%m-%d'),))
    con.commit()
    fix_korean(con, args.workers)
    total = con.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    con.execute('VACUUM')
    con.close()
    print('DONE items', total, 'fails', fails, 'size', OUT.stat().st_size, flush=True)
    return 0 if fails < 50 else 1


if __name__ == '__main__':
    sys.exit(main())
