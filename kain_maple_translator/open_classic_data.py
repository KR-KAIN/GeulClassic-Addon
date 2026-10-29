"""Licensed Classic Maple Wiki offline data reader (not Planet Helper / MeowDB).

The *source* exports are English-first. Nothing in this module asserts that a
machine-translated Korean draft is an official MapleStory item name.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from functools import lru_cache

DATASETS = ("items", "monsters", "maps", "npcs", "quests", "shops", "classes", "professions", "systems", "patches", "builds")
SOURCE = "https://classicmaple.wiki/data/"
LICENSE = "CC BY-NC-SA 4.0"


def data_directory() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "resources" / "open-classic"


def _load_json(path: Path):
    try:
        if not path.is_file() or path.stat().st_size > 15_000_000:
            return []
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        return []


@lru_cache(maxsize=12)
def read_dataset(name: str):
    if name not in DATASETS:
        raise ValueError("Unknown licensed dataset")
    rows = _load_json(data_directory() / (name + ".json"))
    return rows if isinstance(rows, list) else []


def item_name_rows():
    """Return only recognizable names; no guessed Korean localizations."""
    result=[]
    for row in read_dataset("items"):
        if not isinstance(row,dict):
            continue
        english = str(row.get("name") or "").strip()
        ident = str(row.get("id") or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,120}",ident):
            continue
        if not english or len(english)>150 or not re.search(r"[a-zA-Z]",english):
            continue
        # The original published data does not include Korean names.
        # Only a *separately verified bilingual source* may populate name_ko.
        result.append({"item_id":"cw:"+ident,"name_en":english,"name_ko":""})
    return result


def counts():
    return {kind:len(read_dataset(kind)) for kind in DATASETS}


def status_text():
    quantities=counts()
    return " / ".join(f"{kind} {qty:,}" for kind,qty in quantities.items() if qty)
