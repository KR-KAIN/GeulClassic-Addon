"""R8 TTL experiment: compare old 2s and experimental 15s filters without
changing OCR or delivery. Active gating is an explicit opt-in only.

Both filters receive the *same* physical-event candidates from the visual
ledger, so extra blocking counts quantify risk to real new messages.
"""
from __future__ import annotations
import os
from .sliding_dedupe import SlidingChatDeduper


class TTLTrial:
    SHORT_SECONDS=2.0
    LONG_SECONDS=15.0

    def __init__(self, mode='shadow'):
        self.mode=mode if mode in ('shadow','active','off') else 'shadow'
        self.short=SlidingChatDeduper(seconds=self.SHORT_SECONDS)
        self.long=SlidingChatDeduper(seconds=self.LONG_SECONDS)
        self.cumulative={'candidates':0,'short_allowed':0,'long_allowed':0,
                         'extra_blocked':0,'actual_blocked':0}

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get('KAIN_TTL15_MODE','shadow').strip().lower())

    def evaluate(self,candidates,visible,captured_at):
        if self.mode=='off':
            counts={'ttl_trial_mode':'off','ttl_candidates':len(candidates),
                    'ttl_short_allowed':0,'ttl_long_allowed':0,
                    'ttl_extra_blocked':0,'ttl_actual_blocked':0,
                    'ttl_visual_new_blocked':0,
                    'ttl_short_skipped_total':self.short.skipped,
                    'ttl_long_skipped_total':self.long.skipped}
            return candidates,counts
        # SlidingChatDeduper currently does not participate in R7 delivery.
        # These models are hypothetical 2s vs 15s gates, NOT R7 live results.
        short=self.short.filter(candidates,visible,captured_at)
        long=self.long.filter(candidates,visible,captured_at)
        short_ids={id(row) for row in short}
        long_ids={id(row) for row in long}
        extra=sum(1 for row in candidates if id(row) in short_ids and id(row) not in long_ids)
        actual=len(candidates)-len(long) if self.mode=='active' else 0
        chosen=long if self.mode=='active' else candidates
        counters={'ttl_trial_mode':self.mode,'ttl_candidates':len(candidates),
                  'ttl_short_allowed':len(short),'ttl_long_allowed':len(long),
                  'ttl_extra_blocked':extra,'ttl_actual_blocked':actual,
                  # All candidates have NEW physical event IDs per FrameMessageLedger.
                  'ttl_visual_new_blocked':len(candidates)-len(long),
                  'ttl_short_skipped_total':self.short.skipped,
                  'ttl_long_skipped_total':self.long.skipped}
        for key,source in (('candidates','ttl_candidates'),
                           ('short_allowed','ttl_short_allowed'),
                           ('long_allowed','ttl_long_allowed'),
                           ('extra_blocked','ttl_extra_blocked'),
                           ('actual_blocked','ttl_actual_blocked')):
            self.cumulative[key]+=counters[source]
            counters['ttl_total_'+key]=self.cumulative[key]
        return chosen,counters
