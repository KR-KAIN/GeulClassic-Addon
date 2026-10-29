"""Download the game's own item-tooltip pieces (R19).

From the public maplestory.io WZ browser, region MCW version 1 (MapleStory
Classic World itself):
- UI/Tooltip.img/Equip/{Can,Cannot,Dot,Speed}: 'REQ LEV' ... labels, digits,
  job names (orange = can wear, gray = cannot), bullet dots
- UI/UIToolTip.img/Item/Frame2: the 9-slice tooltip frame
- UI/UIToolTip.img/Item/ItemIcon: the icon cell (base / shade / cover)
Saved as PNG in resources/classic_ui/tooltip/ (+ origins.json).
"""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'resources' / 'classic_ui' / 'tooltip'
WZ = 'https://maplestory.io/api/wz/MCW/1/UI'
NODES = {
    'Tooltip.img/Equip/Can': 'Can',
    'Tooltip.img/Equip/Cannot': 'Cannot',
    'Tooltip.img/Equip/Dot': 'Dot',
    'Tooltip.img/Equip/Speed': 'Speed',
    'UIToolTip.img/Item/Frame2': 'Frame2',
    'UIToolTip.img/Item/ItemIcon': 'ItemIcon',
}


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'GeulClassic-Addon tooltip builder'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    origins = {}
    for path, prefix in NODES.items():
        for child in get(f'{WZ}/{path}').get('children', []):
            try:
                data = get(f'{WZ}/{path}/{child}')
            except Exception:
                continue
            if not data.get('value') or data.get('type') not in (None, 12) and not isinstance(data.get('value'), str):
                continue
            try:
                png = base64.b64decode(data['value'])
            except Exception:
                continue
            if not png.startswith(b'\x89PNG'):
                continue
            (OUT / f'{prefix}_{child}.png').write_bytes(png)
            if 'origin' in (data.get('children') or []):
                try:
                    origins[f'{prefix}_{child}'] = get(f'{WZ}/{path}/{child}/origin').get('value')
                except Exception:
                    pass
            print('saved', prefix, child)
    (OUT / 'origins.json').write_text(json.dumps(origins, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
