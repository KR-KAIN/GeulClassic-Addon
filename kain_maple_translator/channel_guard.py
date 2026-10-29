"""Suppress duplicate delivery caused by one OCR line switching channel classification.

This is not a text-wide dedupe: real repeated messages remain legal.
"""
from __future__ import annotations
from collections import OrderedDict
from .core import normalized


class ChannelGuard:
    def __init__(self):
        self.recent = OrderedDict()

    def accept(self, row: dict, captured_at: float) -> bool:
        identity = (normalized(str(row.get('nickname', ''))),
                    normalized(str(row.get('body', ''))))
        if not identity[0] or not identity[1]:
            return True
        kind = 'normal' if row.get('kind','normal') == 'normal' else 'megaphone'
        rect = row.get('rect') or (0, 0, 0, 0)
        y = float(rect[1]) + float(rect[3]) / 2
        prior = self.recent.get(identity)
        event = row.get('_visual_event_id')
        # The visual ledger already established separate physical arrivals.
        # A channel-classification flicker must not override that evidence
        # and mute a player's genuine repeated post. Legacy callers without
        # event IDs retain the geometry/time fallback below.
        distinct_arrival = bool(prior and event is not None and
                                prior[3] is not None and event != prior[3])
        # A cross-classification bounce is only a duplicate if it occurs at
        # effectively the same screen location shortly after the first read.
        bouncing = bool(prior and not distinct_arrival and prior[0] != kind and
                        0 <= captured_at - prior[2] <= 1.5 and
                        abs(y - prior[1]) <= max(24, float(rect[3]) * 1.5))
        if bouncing:
            return False
        self.recent[identity] = (kind, y, captured_at, event)
        self.recent.move_to_end(identity)
        while len(self.recent) > 256:
            self.recent.popitem(last=False)
        # Expire old data so a repeated message from a later broadcast is legal.
        for key, value in list(self.recent.items()):
            if captured_at - value[2] > 2:
                del self.recent[key]
        return True
