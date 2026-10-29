"""Build a local v83 item-ID index from PUBLIC GMS WZ XML snapshots.

NEVER requests, crawls or scrapes meowdb.com.
The user can also supply Korean WZ XML exports in `item-sources/ko/`;
items are joined by their numeric ID, no invented Korean names.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/andrenogrib/gms_v83_wztoweb/main/wz_files/wz/String.wz/'
GROUPS = ('Eqp','Consume','Etc','Ins','Cash','Pet')
HEADERS = {'User-Agent':'GeulClassic-KAIN-Item-Index/0.4.12 (6 static files, non-MeowDB)'}
MAX_SIZE=6_000_000


def extract_items(xml_data:bytes)->dict[str,str]:
    root=ET.fromstring(xml_data)
    out={}
    # On WZ XML item nodes have decimal seven/eight-digit names.
    for elem in root.iter('imgdir'):
        item_id=elem.attrib.get('name','')
        if not re.fullmatch(r'\d{7,8}',item_id): continue
        name=next((x.attrib.get('value','').strip() for x in elem.findall('string')
                   if x.attrib.get('name') == 'name'), '')
        if name and len(name)<160: out[item_id]=name
    return out


def read_input(path:Path):
    if path.stat().st_size>MAX_SIZE: raise ValueError(f'XML too large: {path}')
    return extract_items(path.read_bytes())


def fetch_one(group:str,destination:Path,offline=False):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.is_file() and destination.stat().st_size>100:
        return read_input(destination)
    if offline: return {}
    req=urllib.request.Request(BASE+group+'.img.xml',headers=HEADERS)
    with urllib.request.urlopen(req,timeout=30) as r:
        final=r.geturl()
        if not final.startswith('https://raw.githubusercontent.com/andrenogrib/gms_v83_wztoweb/'):
            raise ValueError('Unexpected source redirect')
        data=r.read(MAX_SIZE+1)
    if len(data)>MAX_SIZE: raise ValueError('XML download too large')
    names=extract_items(data)
    if not names: raise ValueError(f'Invalid WZ item metadata: {group}')
    destination.write_bytes(data)
    return names


def build_index(root:Path,offline=False)->dict:
    base=root/'item-sources'
    english={}; korean={}
    fetched=[]
    for group in GROUPS:
        source=base/'en'/f'{group}.img.xml'
        names=fetch_one(group,source,offline=offline)
        english.update(names)
        fetched.append((group,len(names)))
        ko=base/'ko'/f'{group}.img.xml'
        if ko.is_file(): korean.update(read_input(ko))
    rows=[{'item_id':ident,'name_en':name,'name_ko':korean.get(ident,'')}
          for ident,name in sorted(english.items(),key=lambda x:int(x[0]))]
    output=root/'resources'/'item-ids'/'gms-v83-index.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'source':'public GMS v83 WZ XML (not meowdb)',
                                  'not_classic_world_complete':True,
                                  'items':rows},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    result={'total_ids':len(rows),'korean_names':sum(bool(x['name_ko']) for x in rows),
            'english_without_korean':sum(not x['name_ko'] for x in rows),
            'by_group':dict(fetched),'source':BASE,'output':str(output)}
    (root/'ITEM-ID-REPORT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('--offline',action='store_true')
    a=p.parse_args()
    result=build_index(Path(a.root),offline=a.offline)
    print('OPTIONAL LEGACY ITEM INDEX ONLY (not EXE build):',result['total_ids'],'IDs; Korean names:',result['korean_names'])
    if result['total_ids'] and not result['korean_names']:
        print('INFO: Korean names require separate verified Korean XML; EN->KO offline translation is handled at runtime.')
    if not result['total_ids']:
        print('No input files available. Place GMS WZ XML in item-sources/en, or check network.',file=sys.stderr)
        return 2
    return 0

if __name__=='__main__': raise SystemExit(main())
