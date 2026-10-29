"""Explicit, one-shot maplestory.io item-ID comparison (no background scraping).

GMS v62 English + a user-selected KMS version (65, optional 284) share
numeric game item IDs. Generates a LOCAL optional names database, separate
from the user's hand-maintained glossary. Does not copy data from Planet Helper.

MapleStory names belong to their respective rightsholders. Check the API
provider's usage conditions before using this outside personal/noncommercial
projects. Network errors NEVER overwrite a previously verified result.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = 'https://maplestory.io/api'
PAGE = 4000
MAX_PAGES = 30
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_DB_BYTES = 8 * 1024 * 1024
USER_AGENT = 'KAIN-Maple-Translator/0.4.19 (personal item-name ID lookup; infrequent one-shot sync)'


def local_db_path() -> Path:
    root = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME')
    if not root:
        root = str(Path.home() / '.local' / 'share')
    return Path(root) / 'KAINMapleTranslator' / 'gms-kms-item-names.json'


def parse_item_rows(payload: object, region: str) -> dict[str, str]:
    """Handles the API's ItemNameInfo (Id/Name) and equivalent JSON shapes."""
    if isinstance(payload, dict):
        for key in ('items', 'Items', 'results', 'Results', 'data', 'Data'):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError(f'{region}: item endpoint did not return an item list')
    output = {}
    conflicts = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        ident = row.get('Id', row.get('id', row.get('itemId', row.get('item_id'))))
        name = row.get('Name', row.get('name'))
        if isinstance(name, dict):
            name = name.get('Name', name.get('name'))
        ident = str(ident or '').strip()
        name = str(name or '').strip()
        if not re.fullmatch(r'\d{6,9}', ident) or not 1 <= len(name) <= 160:
            continue
        if region == 'KMS' and not re.search(r'[가-힣]', name):
            continue
        if region == 'GMS' and not re.search(r'[a-zA-Z]', name):
            continue
        if ident in output and output[ident] != name:
            conflicts.add(ident)
        else:
            output[ident] = name
    for ident in conflicts:
        del output[ident]
    return output


def http_json(url: str, *, timeout: float = 30) -> object:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as handle:
        final = urllib.parse.urlsplit(handle.geturl())
        if final.scheme != 'https' or final.netloc.lower() != 'maplestory.io':
            raise ValueError('Unexpected API redirect; refusing non-maplestory.io host')
        raw = handle.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('API response exceeds 12 MB per page')
    try:
        return json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('API did not return valid JSON') from exc


def retrieve(region: str, version: int, *, loader=http_json, pause=0.2) -> dict[str, str]:
    if region not in ('GMS', 'KMS') or not 1 <= version <= 9999:
        raise ValueError('Invalid region or version')
    results = {}
    for page in range(MAX_PAGES):
        start = page * PAGE
        url = f'{ENDPOINT}/{region}/{version}/item?startPosition={start}&count={PAGE}'
        payload = loader(url)
        items = payload if isinstance(payload, list) else next((payload.get(k) for k in ('items','Items','results','Results','data','Data') if isinstance(payload.get(k),list)), None) if isinstance(payload,dict) else None
        if not isinstance(items, list):
            raise ValueError(f'{region}/{version}: unexpected item response')
        parsed = parse_item_rows(items,region)
        if not items:
            break
        seen = set(results)
        if page and parsed and not (set(parsed) - seen):
            raise ValueError(f'{region}/{version}: repeated page; pagination not supported')
        for ident, name in parsed.items():
            if ident in results and results[ident] != name:
                raise ValueError(f'{region}/{version}: ID {ident} has inconsistent names')
            results[ident]=name
        if len(items) < PAGE:
            break
        if pause:
            time.sleep(pause)
    else:
        raise ValueError(f'{region}/{version}: exceeded safe pagination limit ({MAX_PAGES} pages)')
    if not results:
        raise ValueError(f'{region}/{version}: no valid names returned')
    return results


def match_ids(english: dict[str,str], korean: dict[str,str]) -> dict:
    """Keep ID matches, then drop English titles with conflicting KO names.

    The count of same-ID matches and the count safe for live OCR replacement
    must be reported separately: one English display name can describe
    multiple different item IDs/localized names.
    """
    pairs=[]
    for ident,en in english.items():
        ko=korean.get(ident)
        if ko:
            pairs.append({'item_id':ident,'name_en':en,'name_ko':ko})
    unique_by_name=defaultdict(set)
    for row in pairs:
        unique_by_name[unicodedata.normalize('NFKC',row['name_en']).casefold()].add(row['name_ko'])
    safe = [row for row in pairs if len(unique_by_name[unicodedata.normalize('NFKC',row['name_en']).casefold()])==1]
    # Keep only sensible multi-character item titles; the runtime independently
    # suppresses generic single-word names in normal conversational chat.
    return {'gms_count':len(english),'kms_count':len(korean),
            'id_matched':len(pairs), 'safe_name_rows':len(safe),
            'ambiguous_english_rows':len(pairs)-len(safe),
            'gms_without_kms_id':len(english)-len(pairs),
            'items':safe}


def write_atomic_json(path:Path, obj:dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_DB_BYTES:
        raise ValueError('Joined DB exceeds 8 MB; refusing to overwrite')
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='gms-kms-',suffix='.tmp',delete=False) as handle:
        tmp=Path(handle.name)
        handle.write(raw)
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def sync(gms_version:int=62, kms_versions:tuple[int,...]=(65,284), *, loader=http_json, pause=0.2, output:Path|None=None) -> dict:
    en=retrieve('GMS',gms_version,loader=loader,pause=pause)
    failures={}; version=None; ko=None
    for candidate in kms_versions:
        try:
            current = retrieve('KMS',candidate,loader=loader,pause=pause)
            if len(current)<20:
                raise ValueError('Too few Korean names to accept as an item database')
            version=candidate;ko=current
            break
        except (ValueError,urllib.error.URLError,TimeoutError,OSError) as exc:
            failures[str(candidate)]=f'{type(exc).__name__}: {exc}'[:200]
    if ko is None:
        raise ValueError('No usable KMS version found. '+json.dumps(failures,ensure_ascii=False))
    result=match_ids(en,ko)
    if result['id_matched']<20 or not result['safe_name_rows']:
        raise ValueError(f'ID overlap too small ({result["id_matched"]}); refusing to replace existing item names')
    result.update({'source':'maplestory.io','gms_version':gms_version,'kms_version':version,
                   'attempted_kms_versions':list(kms_versions),'skipped_kms_versions':failures,
                   'created_utc':datetime.now(timezone.utc).isoformat(),
                   'note':'same-ID candidate pair, NOT proof of identical item or official classic localization'})
    write_atomic_json(output or local_db_path(),result)
    return result


def main():
    parser=argparse.ArgumentParser(description='Explicit GMS→KMS item-name ID comparison; personal/noncommercial use only')
    parser.add_argument('--gms-version',type=int,default=62)
    parser.add_argument('--kms-versions',default='65,284',help='Try in order; records actual selected version')
    parser.add_argument('--output',type=Path,default=local_db_path())
    args=parser.parse_args()
    try:
        versions=tuple(int(v.strip()) for v in args.kms_versions.split(','))
        if not versions or len(versions)>5 or any(not 1<=v<=9999 for v in versions):
            raise ValueError('Invalid KMS version list')
        result=sync(args.gms_version,versions,output=args.output)
    except (ValueError,urllib.error.URLError,TimeoutError,OSError) as exc:
        print(f'ITEM-SYNC FAILED: {type(exc).__name__}: {exc}',file=sys.stderr)
        print('Existing local item-name DB was not changed.',file=sys.stderr)
        raise SystemExit(1) from None
    print(f'ITEM-SYNC PASS: GMS {result["gms_version"]} ({result["gms_count"]:,}) + '
          f'KMS {result["kms_version"]} ({result["kms_count"]:,})')
    print(f'ID matched: {result["id_matched"]:,}; conflict-free rows: {result["safe_name_rows"]:,}; '
          f'ambiguous names: {result["ambiguous_english_rows"]:,}')
    print('Local DB: '+str(args.output))
    if result['skipped_kms_versions']:
        print('Unavailable KMS versions: '+json.dumps(result['skipped_kms_versions'],ensure_ascii=False))
    print('Note: Version differences can cause false same-ID matches. Review suspicious names.')


if __name__=='__main__':
    main()
