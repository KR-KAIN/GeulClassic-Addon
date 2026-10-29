"""Download the official Argos EN/KO model archives during BUILD only.
The distributed application itself performs no HTTP requests.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
from urllib.request import urlopen, Request
from urllib.parse import urlparse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'resources' / 'models'
INDEX = 'https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json'
PAIRS = [('en','ko'),('ko','en')]


def fetch_models(fetch_index=None, fetch_blob=None):
    MODELS.mkdir(parents=True, exist_ok=True)
    def default_index():
        with urlopen(Request(INDEX, headers={'User-Agent':'KAINMapleTranslator/0.3.0'}), timeout=30) as response:
            return json.load(response)
    def default_blob(url):
        with urlopen(Request(url, headers={'User-Agent':'KAINMapleTranslator/0.3.0'}), timeout=150) as response:
            return response.read()
    index = (fetch_index or default_index)()
    blob = fetch_blob or default_blob
    for src,dst in PAIRS:
        path = MODELS / f'translate-{src}_{dst}.argosmodel'
        if path.exists() and path.stat().st_size > 100000:
            with zipfile.ZipFile(path) as z:
                if z.testzip() is None and any(n.endswith('metadata.json') for n in z.namelist()):
                    print(f'CACHE MODEL {path.name} ({path.stat().st_size:,} bytes)',flush=True)
                    continue
        item=next((p for p in index if p.get('from_code')==src and p.get('to_code')==dst),None)
        if not item:raise RuntimeError(f'Official Argos model index missing {src}->{dst}')
        url=next((u for u in item.get('links',[]) if urlparse(u).scheme=='https'),None)
        if not url:raise RuntimeError(f'Model download HTTPS URL missing: {src}->{dst}')
        print(f'DOWNLOADING {src}->{dst}: {url}',flush=True)
        payload=blob(url)
        if len(payload)<100000:raise RuntimeError(f'Model download too small: {src}->{dst}')
        tmp=path.with_suffix('.tmp')
        tmp.write_bytes(payload)
        try:
            with zipfile.ZipFile(tmp) as z:
                bad=z.testzip()
                if bad:raise RuntimeError('Bad model archive member: '+bad)
                if not any(n.endswith('metadata.json') for n in z.namelist()):
                    raise RuntimeError('Archive metadata.json missing')
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
        print(f'MODEL READY {path.name} ({path.stat().st_size:,} bytes)',flush=True)
    print('MODEL PASS: both EN/KO local archives verified',flush=True)

if __name__=='__main__':
    try:fetch_models()
    except Exception as exc:
        print('MODEL FAILED:',str(exc),file=sys.stderr)
        sys.exit(1)
