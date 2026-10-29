"""Korean names for Classic World items that have none in the Classic World data.

Usage:  python scripts/fetch_kms_names.py [--kms 284,389] [--gms 83,176,240] [--cache DIR]
Writes resources/item-info/kms-names.json.

Classic World's own client data (resources/item-info, region MCW) has no
Korean name for about 3,000 of its 7,350 items: pets, megaphones and many
cash items among them. The Korean MapleStory client (region KMS on the public
maplestory.io API, the same game data the bundled graphics come from) names
the same item IDs. An ID only counts as the same item when a GMS client gives
that ID the same English name Classic World does, so an ID reused for another
item is never mislabelled. Classic World's own Korean names always win.

No meowdb data is used. The app never downloads anything at run time.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'resources' / 'item-info' / 'item-info.sqlite3'
OUT = ROOT / 'resources' / 'item-info' / 'kms-names.json'
API = 'https://maplestory.io/api/{region}/{ver}/item?startPosition={start}&count={count}'
UA = {'User-Agent': 'GeulClassic-Addon item-name builder (offline, infrequent)'}
HANGUL = re.compile('[가-힣]')


def get(url: str, tries: int = 5):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as exc:   # the API is busy at times
            if attempt == tries - 1:
                raise
            print('  retry', attempt + 1, str(exc)[:80])
            time.sleep(3 + attempt * 4)


def client_names(region: str, ver: str, cache: Path | None) -> dict[str, str]:
    """{item id: name} for one client version (cached between runs)."""
    if cache:
        path = cache / f'{region}-{ver}.json'
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
    names, start, count = {}, 0, 4000
    while True:
        rows = get(API.format(region=region, ver=ver, start=start, count=count))
        for row in rows:
            name = str(row.get('name') or '').strip()
            if name:
                names[str(row.get('id'))] = name
        print(f'{region} {ver}: {start}+{len(rows)} -> {len(names)}')
        if len(rows) < count:
            break
        start += count
        time.sleep(.5)
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f'{region}-{ver}.json').write_text(json.dumps(names, ensure_ascii=False), encoding='utf-8')
    return names


def norm(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', name.lower()).strip()


ENGLISH_WORD = re.compile('[A-Za-z]{4,}')   # 'Speed 포션' - but 'HP', 'STR' are Korean usage


def build(items, kms: dict[str, str], gms: list[dict[str, str]]):
    """items: (id, English, Korean-or-empty[, category]) from Classic World.

    1. Same ID: the KMS name, when a GMS client gives the ID the same English name.
    2. Same English name: Classic World renumbered some items (Megaphone is
       5070000 there, 5071000 in GMS/KMS), so a GMS item with exactly this
       English name lends its KMS name, when every such GMS item agrees.
    Items whose Classic World Korean is half English ('Speed 포션') get the
    KMS name as well, marked over_cw. One-word hair/face names are skipped:
    'Casanova' or 'Redemption' in chat is a word, not an item.
    """
    by_name: dict[str, set] = {}
    for g in gms:
        for ident, en in g.items():
            ko = kms.get(ident, '')
            if HANGUL.search(ko):
                by_name.setdefault(norm(en), set()).add(ko)
    out, stats = [], {'has_cw_korean': 0, 'same_id': 0, 'same_name': 0, 'over_half_english': 0,
                      'ambiguous': 0, 'not_found': 0, 'one_word_hair': 0}
    for row in items:
        ident, en, ko = row[:3]
        category = row[3] if len(row) > 3 else ''
        key = str(ident)
        if category == 'Character' and ' ' not in en.strip():
            stats['one_word_hair'] += 1
            continue
        half_english = bool(ko and HANGUL.search(ko) and ENGLISH_WORD.search(ko))
        if ko and HANGUL.search(ko) and ko != en and not half_english:
            stats['has_cw_korean'] += 1
            continue
        kname = kms.get(key, '')
        english = {norm(g[key]) for g in gms if key in g}
        if HANGUL.search(kname) and norm(en) in english:
            found, by = {kname}, 'id'
        else:
            found, by = by_name.get(norm(en), set()), 'name'
        if len(found) == 1:
            name = next(iter(found))
            if half_english:
                if ENGLISH_WORD.search(name):
                    stats['has_cw_korean'] += 1   # no better name: keep Classic World's
                    continue
                out.append({'id': ident, 'en': en, 'ko': name, 'by': by, 'over_cw': True})
                stats['over_half_english'] += 1
                continue
            out.append({'id': ident, 'en': en, 'ko': name, 'by': by})
            stats['same_id' if by == 'id' else 'same_name'] += 1
        elif half_english:
            stats['has_cw_korean'] += 1
        elif found:
            stats['ambiguous'] += 1    # GMS items of this name differ in Korean
        else:
            stats['not_found'] += 1
    return out, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kms', default='284,389', help='KMS versions; later ones win per ID')
    ap.add_argument('--gms', default='83,176,240', help='GMS versions used to confirm an ID')
    ap.add_argument('--cache', default='', help='folder to keep the downloaded name lists')
    args = ap.parse_args()
    cache = Path(args.cache) if args.cache else None
    con = sqlite3.connect('file:' + DB.as_posix() + '?mode=ro', uri=True)
    items = con.execute('SELECT id, name, name_ko, category FROM items WHERE name != ""').fetchall()
    con.close()
    kms: dict[str, str] = {}
    for ver in args.kms.split(','):
        kms.update(client_names('KMS', ver.strip(), cache))
    gms = [client_names('GMS', ver.strip(), cache) for ver in args.gms.split(',')]
    out, stats = build(items, kms, gms)
    OUT.write_text(json.dumps({
        'source': 'maplestory.io KMS ' + args.kms + ' client item names for Classic World (MCW) item IDs,'
                  ' each ID confirmed by the same English name in GMS ' + args.gms,
        'fetched': time.strftime('%Y-%m-%d'), 'stats': stats, 'items': out},
        ensure_ascii=False, indent=0), encoding='utf-8')
    print(f'{len(items)} Classic World items: {stats} -> {OUT}')


if __name__ == '__main__':
    main()
