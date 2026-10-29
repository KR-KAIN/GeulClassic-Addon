"""Download publisher-provided JSON exports, NOT scrape the website.

Licensed CC BY-NC-SA 4.0, non-commercial use only; see OPEN-DATA-LICENSE.md.
Use --source-dir DIRECTORY to verify/package user-provided exports offline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from kain_maple_translator.open_classic_data import DATASETS, SOURCE

MAX_BYTES=15_000_000
HEADERS={"User-Agent":"GeulClassic-KAIN/0.4.14 (published JSON exports, CC-BY-NC-SA)"}


def validate_export(kind, data:bytes):
    if len(data)>MAX_BYTES: raise ValueError(f"{kind}: oversized")
    rows=json.loads(data.decode("utf-8-sig"))
    if not isinstance(rows,list): raise ValueError(f"{kind}: expected JSON list")
    if kind in ("items","monsters","maps","npcs","quests"):
        if not rows or not all(isinstance(x,dict) and x.get("name") and x.get("id") for x in rows):
            raise ValueError(f"{kind}: invalid entity schema")
    return rows


def request_export(name):
    url=SOURCE+name+".json"
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=35) as response:
        if response.geturl().split("?",1)[0]!=url:
            raise ValueError(f"{name}: unexpected source redirect")
        if response.status!=200:
            raise ValueError(f"{name}: HTTP {response.status}")
        raw=response.read(MAX_BYTES+1)
    return raw


def build(root:Path, source_dir:Path|None=None):
    folder=root/"resources"/"open-classic"
    folder.mkdir(parents=True,exist_ok=True)
    reports=[]
    for name in DATASETS:
        target=folder/(name+".json")
        try:
            if source_dir is not None:
                raw=(source_dir/(name+".json")).read_bytes()
            else:
                raw=request_export(name)
            rows=validate_export(name,raw)
            # Atomic writes avoid corrupting a previous complete offline DB.
            draft=target.with_suffix(".json.tmp")
            draft.write_bytes(raw)
            os.replace(draft,target)
            reports.append({"dataset":name,"items":len(rows),"bytes":len(raw),
                            "sha256":hashlib.sha256(raw).hexdigest(),"status":"ok"})
            print(name,len(rows),flush=True)
        except Exception as exc:
            previous_valid=False
            if target.is_file():
                try: validate_export(name,target.read_bytes()); previous_valid=True
                except (ValueError,UnicodeError,OSError): pass
            reports.append({"dataset":name,"items":0,"status":"reused-cache" if previous_valid else "unavailable",
                            "error":str(exc)[:350]})
            print(f"WARN {name}: {exc}",file=sys.stderr,flush=True)
    required=("items","monsters","maps","npcs","quests")
    ok=all(any(r["dataset"]==name and r["status"] in ("ok","reused-cache") for r in reports)
           for name in required)
    report={"source":SOURCE,"license":"CC BY-NC-SA 4.0","noncommercial_only":True,
            "retrieved_utc":datetime.now(timezone.utc).isoformat(),"required_data_available":ok,
            "datasets":reports}
    (root/"OPEN-DATA-REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--source-dir",default=None)
    args=p.parse_args()
    result=build(Path(args.root),Path(args.source_dir) if args.source_dir else None)
    print("REQUIRED DATA READY" if result["required_data_available"] else "INCOMPLETE DATA; check OPEN-DATA-REPORT.json")
    return 0 if result["required_data_available"] else 2

if __name__=="__main__":
    raise SystemExit(main())
