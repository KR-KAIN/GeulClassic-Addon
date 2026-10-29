"""Cut the chat-window skin out of the user's game screenshot (412x573).

resources/classic_ui/ref_chat_window.png -> chat_skin.png (title text and
scrollbar parts removed), chat_up.png, chat_down.png, chat_thumb.png.
Coordinates were measured on the screenshot pixel by pixel.
"""
from pathlib import Path
import cv2
import numpy as np

UI = Path(__file__).resolve().parents[1] / 'resources' / 'classic_ui'


def main():
    ref = cv2.imdecode(np.fromfile(str(UI / 'ref_chat_window.png'), np.uint8), cv2.IMREAD_UNCHANGED)
    if ref.shape[2] == 3:
        ref = cv2.cvtColor(ref, cv2.COLOR_BGR2BGRA)
    skin = ref.copy()
    # title text 'equips' -> plain white of the box
    skin[9:41, 24:372] = ref[9:41, 200:201]
    # scrollbar: keep only the track (row 300 pattern)
    skin[51:526, 382:404] = ref[300:301, 382:404]
    pieces = {'chat_skin': skin, 'chat_up': ref[51:69, 382:404], 'chat_down': ref[506:525, 382:404],
              'chat_thumb': ref[69:107, 382:404]}
    for name, img in pieces.items():
        ok, buf = cv2.imencode('.png', img)
        buf.tofile(str(UI / f'{name}.png'))
        print(name, img.shape)


if __name__ == '__main__':
    main()
