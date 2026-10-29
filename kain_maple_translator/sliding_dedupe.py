"""Short-lived evidence-based dedupe after consecutive-frame sequence tracking.

Text alone is not a message identity: a repeated trade advertisement is a
legitimate second event. This layer suppresses OCR retries and old lines that
move upward with the chat scroll, without globally muting that text.
"""
from __future__ import annotations
from collections import Counter, defaultdict, deque
from .core import normalized


class SlidingChatDeduper:
    def __init__(self, seconds=2.0, max_events=96):
        self.seconds=float(seconds)
        self._has_previous_frame = False
        self._previous_at=-1e9
        self.recent=deque(maxlen=max_events)
        self.previous={}
        self.skipped=0

    @staticmethod
    def identity(row):
        # R18: the same line can be judged a megaphone on one frame and
        # normal chat on the next; that is one message, not two.
        return (normalized(str(row.get('nickname',''))),
                normalized(str(row.get('body',''))))

    @staticmethod
    def y(row):
        x,y,w,h=row.get('rect') or (0,0,0,0)
        return float(y)+float(h)*.5

    def filter(self, candidates, visible_rows, captured_at):
        now=float(captured_at)
        while self.recent and now-self.recent[0][2]>self.seconds:
            self.recent.popleft()
        # A chat line returning after an actually empty view for several
        # seconds may be a fresh post; a one-frame OCR dropout is not.
        if now-self._previous_at>3.0:
            self.previous={}
            self._has_previous_frame=False
        visible=defaultdict(list)
        for row in visible_rows:
            visible[self.identity(row)].append(self.y(row))
        # Bottom anchor is a frame-relative EVENT gate, not a hard-coded
        # 35-pixel crop: a burst can append several new chat rows before OCR
        # finishes. Let the contiguous new suffix survive, including 2+ rows.
        # Rows that reappear higher up after an OCR dropout are not arrivals.
        ordered=sorted(visible_rows,key=self.y)
        candidate_ids={id(row) for row in candidates}
        candidate_positions=set()
        used=set()
        for row in candidates:
            # Production uses the SAME dict object from classified rows; a
            # geometry fallback supports snapshots that reconstructed dicts.
            match=next((i for i,shown in enumerate(ordered)
                        if i not in used and id(shown)==id(row)),None)
            if match is None:
                key=self.identity(row)
                match=next((i for i,shown in enumerate(ordered)
                            if i not in used and self.identity(shown)==key
                            and abs(self.y(shown)-self.y(row))<=max(3.,float(row.get('rect',(0,0,0,16))[3])*.7)),None)
            if match is not None:
                used.add(match)
                candidate_positions.add(match)
        suffix_start=len(ordered)
        while suffix_start-1 in candidate_positions:
            suffix_start-=1
        # Two identical messages visible in DIFFERENT rows is evidence of
        # repetition; movement of just one old row is not.
        accepted=[]
        prior=self.previous
        # Handle simultaneous identical candidates separately; don't let an
        # accepted first instance hide a second visible on the same frame.
        indices=defaultdict(int)
        for row in candidates:
            # At a stable chat box, newly admitted rows must enter via the
            # bottom suffix. Never re-emit an old mid-screen line because
            # the recognizer read it differently after a frame flicker.
            # Do not filter the first observed screen or an empty OCR frame.
            idx=next((i for i,shown in enumerate(ordered)
                      if id(shown)==id(row)),None)
            if idx is None:
                idx=next((i for i,shown in enumerate(ordered)
                          if self.identity(shown)==self.identity(row)
                          and abs(self.y(shown)-self.y(row)) <= max(3.,float(row.get('rect',(0,0,0,16))[3])*.7)),None)
            if self._has_previous_frame and ordered and idx is not None and idx < suffix_start:
                self.skipped+=1
                continue
            key=self.identity(row)
            y=self.y(row)
            count_now=len(visible[key])
            before=prior.get(key,())
            indices[key]+=1
            row_h=float((row.get('rect') or (0,0,0,15))[3])
            tolerance=max(4., min(12.,row_h*.42))
            # A line remaining at its location OR moving UP as new messages
            # arrive is the same visual event. But if extra instances now
            # coexist, never discard the newly arriving ones.
            old_visible=(count_now<=len(before) and any(
                -tolerance <= old_y-y <= max(140.,row_h*6.)
                for old_y in before))
            # The short buffer rescues false tracker resets / text OCR jitter
            # at the same line, not different-position legitimate repeats.
            recent_same=any(k==key and abs(old_y-y)<=tolerance
                            and 0<=now-t<=self.seconds
                            for k,old_y,t in self.recent)
            if (old_visible or recent_same) and not (
                    row.get('_new_visual_evidence') or row.get('_bottom_arrival')):
                self.skipped+=1
                continue
            accepted.append(row)
            self.recent.append((key,y,now))
        # A transient blank/partial OCR scan must not destroy the tracked
        # visual rows: otherwise a retry can replay the entire chat history.
        if visible_rows:
            if (len(visible_rows)>=sum(map(len,self.previous.values())) or
                    now-self._previous_at>2.5):
                self.previous=dict(visible)
            else:
                retained=defaultdict(list,{k:list(v) for k,v in self.previous.items()})
                for key,ys in visible.items():retained[key]=ys
                self.previous=dict(retained)
            self._previous_at=now
            self._has_previous_frame=True
        elif now-self._previous_at>4.0:
            self.previous={}
            self._has_previous_frame=False
        return accepted
