"""Download the game's own buttons and turn them into blank 3-slice sprites.

Source: the public maplestory.io WZ browser, region MCW version 1 (MapleStory
Classic World itself):
- UI/UserList.img/Buddy/button:add       -> lime   (ADD / DELETE)
- UI/UserList.img/Buddy/button:mystatus  -> orange (MY STATUS / CREATE GROUP)
- UI/UserList.img/Buddy/button:whisper   -> pink   (WHISPER / TALK)
- UI/Options.img/button:OK               -> blue   (CONFIRM)
- UI/Options.img/button:Cancel           -> cancel (CANCEL, the blue one's pair)
- UI/Basic.img/BtClose                   -> close  (the blue X)
each in its four states (normal / mouseOver / pressed / disabled = grey).

The label is baked into the sprite, so the blank button is rebuilt from the
game's own pixels: the 3px left and right ends, and one text-free column
between them (the vertical gradient) repeated. The addon stretches only that
middle, exactly like the game stretches nothing but plain columns.

Writes resources/classic_ui/button/<kind>_<state>.png (native size) and the
Qt style-sheet copies resources/classic_ui/qss_btn_<kind>[_<state>].png at
the 1920x1080 stretch (bilinear, like the game window).
"""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'resources' / 'classic_ui' / 'button'
QSS = ROOT / 'resources' / 'classic_ui'
WZ = 'https://maplestory.io/api/wz/MCW/1/UI'
SOURCES = {
    'lime': 'UserList.img/Buddy/button:add',
    'orange': 'UserList.img/Buddy/button:mystatus',
    'pink': 'UserList.img/Buddy/button:whisper',
    'blue': 'Options.img/button:OK',
    'cancel': 'Options.img/button:Cancel',
    'close': 'Basic.img/BtClose',
}
STATES = {'normal': 'normal', 'hover': 'mouseOver', 'pressed': 'pressed', 'disabled': 'disabled'}
CAP = 3          # left/right ends kept as drawn
FILL = 10        # blank middle columns stored (stretched at run time)
QSS_SCALE = (1920 / 1366, 1080 / 768)


def get(path):
    req = urllib.request.Request(f'{WZ}/{path}', headers={'User-Agent': 'GeulClassic-Addon button builder'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def sprite(path) -> np.ndarray:
    data = get(path)
    png = base64.b64decode(data['value'])
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return img


def _same(img, a, b) -> bool:
    return np.abs(img[:, a].astype(int) - img[:, b].astype(int)).max() <= 6


def blank(img: np.ndarray) -> np.ndarray:
    """The button without its label: the drawn ends + one clean gradient
    column. The pressed state has an extra inner edge, so the first column
    that equals its next two (no edge, no letter) is found per sprite."""
    w = img.shape[1]
    left = next(x for x in range(2, w // 2) if _same(img, x, x + 1) and _same(img, x, x + 2))
    # the ends are symmetric; their width is stored in caps.json
    return np.hstack([img[:, :left], np.repeat(img[:, left:left + 1], FILL, axis=1), img[:, w - left:]]), left


def save(path: Path, img: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode('.png', img)
    assert ok
    path.write_bytes(buf.tobytes())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    caps = {}
    for kind, node in SOURCES.items():
        for state, wz_state in STATES.items():
            img = sprite(f'{node}/{wz_state}/0')
            if kind == 'close':
                save(OUT / f'{kind}_{state}.png', img)
                continue
            out, cap = blank(img)
            caps[f'{kind}_{state}'] = cap
            save(OUT / f'{kind}_{state}.png', out)
            # Qt style-sheet copy, stretched like the game window
            wide = np.hstack([out[:, :cap], np.repeat(out[:, cap:cap + 1], 40, axis=1), out[:, -cap:]])
            big = cv2.resize(wide, (round(wide.shape[1] * QSS_SCALE[0]), round(wide.shape[0] * QSS_SCALE[1])),
                             interpolation=cv2.INTER_LINEAR)
            suffix = '' if state == 'normal' else f'_{state}'
            save(QSS / f'qss_btn_{kind}{suffix}.png', big)
        print('ok', kind)
    (OUT / 'caps.json').write_text(json.dumps(caps, indent=1, sort_keys=True), encoding='utf-8')


if __name__ == '__main__':
    main()
