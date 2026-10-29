"""Bounded rolling stage timings; safe from OCR and translation threads."""
from collections import defaultdict, deque
import math
import threading


class LatencyBook:
    def __init__(self, capacity=256):
        self.capacity = capacity
        self.samples = defaultdict(lambda: deque(maxlen=capacity))
        self.counts = defaultdict(int)
        self.peaks = defaultdict(float)
        self.lock = threading.Lock()

    def observe(self, stage, milliseconds):
        with self.lock:
            value=max(0.0,float(milliseconds))
            self.samples[stage].append(value)
            self.peaks[stage]=max(self.peaks[stage],value)
            self.counts[stage] += 1

    def snapshot(self):
        out = {}
        with self.lock:
            for stage, series in self.samples.items():
                data = sorted(series)
                if not data:
                    continue
                for label, fraction in (('p50', .5), ('p95', .95)):
                    out[f'{stage}_{label}_ms'] = round(data[max(0, math.ceil(len(data)*fraction)-1)], 2)
                out[f'{stage}_max_ms'] = round(data[-1], 2)
                out[f'{stage}_lifetime_max_ms'] = round(self.peaks[stage], 2)
                out[f'{stage}_samples'] = self.counts[stage]
        return out
