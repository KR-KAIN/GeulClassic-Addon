"""Build English -> Korean item names for MapleStory Classic World.

Usage: python scripts/fetch_meowdb_items.py [--kms-versions 284,389] [--gms-versions 62,83,...]
Writes resources/meowdb/meowdb-items-ko.json.

1. meowdb.com lists every Classic World item with its English name and, for
   some items, a Korean name (used first).
2. maplestory.io serves GMS (English) and KMS (Korean) client item names by
   game item ID. Joining them by ID gives verified English -> Korean pairs.
3. A meowdb item gets a KMS name only when its English name matches a GMS
   name exactly and every GMS item with that name has the same Korean name.
   (meowdb's iconKey is an icon, not always the item ID: never trusted alone.)
"""
from __future__ import annotations
import argparse, json, re, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEOW = 'https://meowdb.com/msclassic/api/items?locale=ko&limit=500&page={page}'
API = 'https://maplestory.io/api/{region}/{ver}/item?startPosition={start}&count={count}'
UA = {'User-Agent': 'KAIN-GeulClassic-Addon item-name import (personal, infrequent)'}


def get(url, timeout=90):
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout))
        except Exception as exc:  # both sites are busy at times
            print('  retry', attempt + 1, str(exc)[:80])
            time.sleep(3 + attempt * 4)
    raise RuntimeError('failed: ' + url)


def meowdb_items():
    rows, page = {}, 1
    while True:
        data = get(MEOW.format(page=page))
        for it in data.get('items', []):
            rows[it['id']] = it
        print('meowdb page', page, len(rows))
        if not data.get('hasMore'):
            return list(rows.values())
        page += 1
        time.sleep(0.8)


def client_names(region, ver):
    names, start, count = {}, 0, 4000
    want = '[가-힣]' if region == 'KMS' else '[A-Za-z]'
    while True:
        data = get(API.format(region=region, ver=ver, start=start, count=count))
        for it in data:
            name = str(it.get('name') or '').strip()
            if re.search(want, name):
                names[str(it.get('id'))] = name
        print(region, ver, 'from', start, 'got', len(data), 'total', len(names))
        if len(data) < count:
            return names
        start += count
        time.sleep(0.5)


def norm(name):
    return re.sub(r'[^a-z0-9]+', ' ', name.lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kms-versions', default='284,389')
    ap.add_argument('--gms-versions', default='62,83,95,111,150,176,213,240,270')
    args = ap.parse_args()
    items = meowdb_items()
    kms = {}
    for ver in args.kms_versions.split(','):   # newer versions win per ID
        kms.update(client_names('KMS', ver.strip()))
    en_to_ko: dict[str, set] = {}
    for ver in args.gms_versions.split(','):
        for ident, en in client_names('GMS', ver.strip()).items():
            if ident in kms:
                en_to_ko.setdefault(norm(en), set()).add(kms[ident])
    out, by_source = [], {'meowdb': 0, 'gms-kms': 0}
    for it in items:
        en = str(it.get('name') or '').strip()
        meow_ko = str(it.get('displayName') or '').strip()
        if not re.search('[A-Za-z]', en):
            continue
        if re.search('[가-힣]', meow_ko) and meow_ko != en:
            ko, source = meow_ko, 'meowdb'
        else:
            found = en_to_ko.get(norm(en), set())
            if len(found) != 1:
                continue   # unknown or ambiguous: keep English
            ko, source = next(iter(found)), 'gms-kms'
        by_source[source] += 1
        out.append({'id': it['id'], 'en': en, 'ko': ko, 'source': source,
                    'type': it.get('type'), 'subtype': it.get('subtype')})
    out.sort(key=lambda r: r['id'])
    dest = ROOT / 'resources' / 'meowdb' / 'meowdb-items-ko.json'
    dest.write_text(json.dumps({'source': 'meowdb.com/msclassic + maplestory.io GMS ' + args.gms_versions
                                + ' / KMS ' + args.kms_versions,
                                'fetched': time.strftime('%Y-%m-%d'), 'items_seen': len(items),
                                'by_source': by_source, 'items': out}, ensure_ascii=False, indent=0),
                    encoding='utf-8')
    print(f'{len(items)} Classic items, {len(out)} with Korean names {by_source} -> {dest}')


if __name__ == '__main__':
    main()
