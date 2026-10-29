"""Read bundled images without passing Unicode filenames through C fopen."""
from pathlib import Path
import cv2
import numpy as np


def read_image(path, flags=cv2.IMREAD_COLOR):
    try:
        blob=Path(path).read_bytes()
        return cv2.imdecode(np.frombuffer(blob,np.uint8),flags) if blob else None
    except (OSError,ValueError,cv2.error):
        return None
