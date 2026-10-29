"""Offline compare of user-authorized Korean item exports against GMS v83 IDs.

Does NOT crawl Planet Helper, MapleNote, mapledb.kr, or other websites.
Only read input files the user owns or has explicit permission to reuse.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

MAX_BYTES = 25_000_000
MAX_ROWS = 100_000


def _rows(path: Path) -> list[dict]:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Input >25MB')
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as f:
            data = list(csv.DictReader(f))
    elif path.suffix.lower() == '.json':
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(data, dict):
            if isinstance(data.get('items'), list):
                data=data['items']
            elif isinstance(data.get('records'), list):
                data=data['records']
            else:
                raise ValueError('JSON needs an items or records list')
    else:
        raise ValueError('CSV or JSON required')
    if not isinstance(data,list) or len(data)>MAX_ROWS:
        raise ValueError('Expected list <=100,000 records')
    return [x for x in data if isinstance(x,dict)]


def compare(en_rows: list[dict], ko_rows: list[dict]) -> dict:
    english = {}
    for row in en_rows:
        ident=str(row.get('item_id') or row.get('id') or '').strip()
        name=str(row.get('name_en') or '').strip()
        if ident.isdecimal() and name:
            english[ident]=name
    ko_ids = defaultdict(set)
    for row in ko_rows:
        ident=str(row.get('item_id') or row.get('id') or '').strip()
        korean=str(row.get('name_ko') or row.get('korean') or '').strip()
        if ident.isdecimal() and re.search('[가-힣]',korean):
            ko_ids[ident].add(korean)
    exact=[]
    disputed=[]
    for ident, en in english.items():
        matched=ko_ids.get(ident,set())
        if len(matched)==1:
            exact.append({'item_id':ident,'name_en':en,'name_ko':next(iter(matched))})
        elif len(matched)>1:
            disputed.append(ident)
    # Same English display title can represent different Korean names across
    # IDs; do not silently override the translation dictionary in that case.
    name_groups=defaultdict(set)
    for row in exact:
        name_groups[unicodedata.normalize('NFKC',row['name_en']).casefold()].add(row['name_ko'])
    safe=[row for row in exact if len(name_groups[unicodedata.normalize('NFKC',row['name_en']).casefold()])==1]
    return {
        'english_ids':len(english), 'korean_ids':len(ko_ids),
        'matched_ids':len(exact), 'missing_ids':len(english)-len(exact)-len(disputed),
        'conflicting_korean_ids':len(disputed),
        'unambiguous_for_text_replacement':len(safe),
        'ambiguous_english_ids':len(exact)-len(safe),
        'matched':exact, 'safe_for_glossary':safe,
        'warning':'Matching ID does not establish official Korean localization; verify game version and source rights.'
    }


def main() -> None:
    p=argparse.ArgumentParser(description='Compare only user-authorized Korean names by item ID (no network).')
    p.add_argument('--english',type=Path,default=Path('resources/item-ids/gms-v83-index.json'))
    p.add_argument('--korean',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('AUTHORIZED-ID-MATCH-REPORT.json'))
    opts=p.parse_args()
    en=_rows(opts.english)
    ko=_rows(opts.korean)
    result=compare(en,ko)
    report={k:v for k,v in result.items() if k not in ('matched','safe_for_glossary')}
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    opts.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    filename=opts.output.with_name('AUTHORIZED-ID-MATCH-CATALOG.csv')
    with filename.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['item_id','name_en','name_ko'])
        writer.writeheader()
        writer.writerows(result['safe_for_glossary'])
    print(f"GMS EN {report['english_ids']} / KO {report['korean_ids']} / ID matched {report['matched_ids']} / text-safe {report['unambiguous_for_text_replacement']}")
    print(f'Outputs: {opts.output}, {filename}')


if __name__=='__main__':
    main()
