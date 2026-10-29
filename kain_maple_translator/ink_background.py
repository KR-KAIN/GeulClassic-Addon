"""Estimate the modal background without letting dense letters move the median."""
import cv2
import numpy as np


def row_background(image):
    pixels = image[:, :, :3]
    # Quantized mode tolerates capture scaling and alpha blending. The median
    # is taken only inside that background cluster, not across the text row.
    q = pixels.astype(np.uint16) >> 3
    codes = q[:, :, 0]*1024 + q[:, :, 1]*32 + q[:, :, 2]
    background = np.empty((pixels.shape[0], 3), np.float32)
    for y in range(pixels.shape[0]):
        values, counts = np.unique(codes[y], return_counts=True)
        background[y] = np.median(pixels[y, codes[y] == values[counts.argmax()]], axis=0)
    # Dense glyphs can win a single scanline even in the modal estimator.
    # Five adjacent rows keep the same band while rejecting that outlier.
    padded=np.pad(background,((2,2),(0,0)),mode='edge')
    return np.median(np.stack([padded[i:i+len(background)] for i in range(5)]),axis=0)


def neutral_ink(image):
    background = row_background(image)
    delta = np.max(np.abs(image[:, :, :3].astype(np.float32)-background[:, None]), axis=2)
    # Preserve anti-aliasing, punctuation and both light/dark linked items.
    foreground = delta[delta > 12]
    peak = float(np.percentile(foreground, 90)) if foreground.size else 100
    gain, offset = (min(16., 240/max(12., peak-4)), 4) if peak < 55 else (3.4, 8)
    neutral = 255-np.clip((delta-offset)*gain, 0, 255).astype(np.uint8)
    neutral[delta < 12] = 255
    return cv2.cvtColor(neutral, cv2.COLOR_GRAY2BGR)
