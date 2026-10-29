"""Screen-only hunting session tracking; never reads or modifies game memory.

The timer uses monotonic time; an OCR failure must never change elapsed hunting
minutes. Potion counts are conservative estimates made from stable, readably
rendered numbers. Level changes may need a reliable experience requirement and
are marked estimated rather than inventing exact EXP.
"""
from __future__ import annotations
from dataclasses import dataclass,field
import re
import time

@dataclass
class SlotRecord:
    icon_id: str = ''
    initial_count: int | None = None
    last_count: int | None = None
    spent: int = 0
    refills: int = 0
    pending: str | None = None

@dataclass
class HuntSession:
    clock: object = time.monotonic
    started_at: float | None = None
    finished_at: float | None = None
    running: bool = False
    start_level: int | None = None
    last_level: int | None = None
    start_exp: int | None = None
    last_exp: int | None = None
    last_percent: float | None = None
    gained_exp: int = 0
    start_percent: float | None = None
    gained_percent: float = 0.0
    start_meso: int | None = None
    last_meso: int | None = None
    meso_net: int = 0
    exp_estimated: bool = False
    pending_lower_exp: int | None = None
    slots: dict[str, SlotRecord] = field(default_factory=dict)
    retired_usage: dict[str,int] = field(default_factory=dict)

    def start(self):
        self.started_at = float(self.clock());self.finished_at=None
        self.running=True;self.start_level=None;self.last_level=None
        self.start_exp=None;self.last_exp=None;self.last_percent=None
        self.gained_exp=0;self.start_percent=None;self.gained_percent=0.0;self.start_meso=None;self.last_meso=None;self.meso_net=0
        self.exp_estimated=False;self.pending_lower_exp=None;self.slots.clear();self.retired_usage.clear()

    def finish(self):
        if self.running:
            self.finished_at = float(self.clock());self.running=False

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:return 0.
        end=float(self.clock()) if self.running else (self.finished_at or self.started_at)
        return max(0.,end-self.started_at)

    @property
    def elapsed_label(self) -> str:
        total=int(self.elapsed_seconds)
        return f'{total//3600:02}:{(total//60)%60:02}:{total%60:02}'

    def observe_exp(self, level: int | None, exp: int | None, pct: float | None=None):
        if not self.running or exp is None or exp < 0:
            return
        # The small LV icon sometimes cannot be OCR'd even though the EXP
        # counter is legible. Do not discard that valid EXP measurement.
        if level is None:
            level=self.last_level or self.start_level or 0
        level=int(level);exp=int(exp)
        if self.last_level is None:
            self.start_level=self.last_level=level
            self.start_exp=self.last_exp=exp;self.last_percent=pct;self.start_percent=pct
            return
        if self.last_level==0 and level>0:
            # Previously the level glyph was unreadable. This is NOT a
            # level-up; retain prior gained EXP without inventing a rollover.
            self.last_level=level;self.last_exp=exp;self.last_percent=pct
            return
        if level == self.last_level:
            # Percent and absolute EXP should imply roughly the same maximum
            # EXP for this level. A dropped OCR digit can otherwise fabricate
            # tens of thousands of gained EXP over a couple of seconds.
            if (pct is not None and self.last_percent is not None and
                    1.0<=pct<=100 and 1.0<=self.last_percent<=100 and
                    self.last_exp is not None and self.last_exp>=100):
                old_max=self.last_exp*100.0/self.last_percent
                new_max=exp*100.0/pct
                if old_max>0 and abs(new_max-old_max)/old_max>.12:
                    return
            delta=exp-self.last_exp
            if delta<0:
                # Never convert a single OCR misread/decrease into an
                # artificial gain when the counter returns on next frame.
                if self.pending_lower_exp is None or abs(self.pending_lower_exp-exp)>max(5,exp*.015):
                    self.pending_lower_exp=exp
                    return
            self.pending_lower_exp=None
            if delta >= 0:
                self.gained_exp+=delta
                if pct is not None and self.last_percent is not None and pct>=self.last_percent:
                    self.gained_percent+=pct-self.last_percent
            # Death may genuinely lower experience. Re-anchor only after a
            # second consistent observation, counting no negative gain.
            self.last_exp=exp;self.last_percent=pct
        elif level > self.last_level:
            self.pending_lower_exp=None
            # R18 live check: a misread level glyph ('1' for '18', then '18')
            # looked like a level-up and added the whole current EXP as
            # gained. A real level-up is +1 and resets EXP and percent.
            real=(level==self.last_level+1
                  and (self.last_exp is None or exp<self.last_exp)
                  and (pct is None or self.last_percent is None or pct<self.last_percent))
            if not real:
                self.last_level=level;self.last_exp=exp;self.last_percent=pct
                self.lower_level_reads=0
                return
            # The previous level threshold is not always displayed. If both
            # EXP and percentage are known, estimate requirement conservatively.
            if level == self.last_level+1 and self.last_exp and self.last_percent and self.last_percent>0.1:
                expected=round(self.last_exp*100/self.last_percent)
                if expected>=self.last_exp:
                    self.gained_exp+=expected-self.last_exp+exp
                else:self.gained_exp+=exp
            else:
                self.gained_exp+=exp
            if pct is not None and self.last_percent is not None:
                self.gained_percent+=(100.0-self.last_percent)+pct
            self.exp_estimated=True
            self.last_level=level;self.last_exp=exp;self.last_percent=pct
        else:
            # Character switch / inconsistent OCR: discard this reading -
            # unless the lower level keeps coming back (the previous level
            # was itself a misread, e.g. '81' for '18'): re-anchor, no gain.
            if getattr(self,'_lower_level',None)==level:
                self.lower_level_reads=getattr(self,'lower_level_reads',0)+1
            else:
                self._lower_level=level;self.lower_level_reads=1
            if self.lower_level_reads>=3:
                self.last_level=level;self.last_exp=exp;self.last_percent=pct
                self.lower_level_reads=0
            return

    def observe_slot(self, slot: str, icon_id: str, count: int | None):
        if not self.running or not icon_id:
            return
        record=self.slots.setdefault(slot,SlotRecord())
        if icon_id != record.icon_id:
            # Consecutive confirmation prevents animation or one bad frame
            # from mistaking an existing potion for a new type.
            # A potion can be consumed between observations. Confirm its
            # *visual identity*, not an identical (ever-changing) stack count.
            if record.pending != icon_id:
                record.pending=icon_id
                return
            record.pending=None
            if record.icon_id and record.spent:
                self.retired_usage[record.icon_id]=self.retired_usage.get(record.icon_id,0)+record.spent
            record.icon_id=icon_id
            record.initial_count=count
            record.last_count=count
            record.spent=0;record.refills=0
            return
        record.pending=None
        if count is None:return
        if record.last_count is None:
            record.last_count=count;return
        change=count-record.last_count
        if change < 0 and abs(change)<=9999:
            record.spent+=-change
        elif change>0:
            record.refills+=change
        record.last_count=count


    def observe_meso(self, total: int | None):
        """Observed inventory balance change, *not* unobservable gross loot."""
        if not self.running or total is None or total < 0:
            return
        total=int(total)
        if self.last_meso is None:
            self.start_meso=self.last_meso=total
            return
        # Ignore implausible one-shot OCR jumps to avoid artificial profits.
        if abs(total-self.last_meso) > max(2_000_000_000, self.last_meso*20):
            return
        self.meso_net += total-self.last_meso
        self.last_meso=total


def parse_exp_text(text: str):
    text=str(text or '').replace('，',',').replace('．','.')
    m=re.search(r'(?i)\bLV\.?\s*([0-9]{1,3})\b',text)
    level=int(m.group(1)) if m else None
    # Global Classic HUD can render the EXP counter as 7,465 or 7.465.
    # Treat comma and period as thousands separators for the absolute EXP
    # value, while the percentage continues to use a decimal point.
    e=re.search(r'(?i)\bEXP\s*[.:：．(\[]?\s*([\d,\.]{1,14})\s*[,\[( ]*\s*([\d.]{1,6})\s*%',text)
    if not e:
        e=re.search(r'(?i)\bEXP\s*[.:：．(\[]?\s*([\d,\.]{1,14})\s*\[',text)
    exp=None
    if e:
        raw=e.group(1).strip().strip('.,')
        normalized=re.sub(r'(?<=\d)[,.](?=\d{3}(?:\D|$))','',raw)
        # If OCR produced only digit separators, keep just the digits.
        if re.fullmatch(r'[\d,\.]+', raw) and re.search(r'\d', raw):
            normalized=''.join(ch for ch in normalized if ch.isdigit())
        try:
            exp=int(normalized) if normalized else None
        except ValueError:
            exp=None
    pct=float(e.group(2)) if e and e.lastindex and e.lastindex>=2 else None
    if pct is not None and not 0<=pct<=100:pct=None
    return level,exp,pct


def parse_meso_text(text: str):
    """Only accept an explicitly labelled on-screen inventory balance."""
    text=str(text or '').replace('，',',')
    match=re.search(r'(?i)(?:\bMESO(?:S)?\b|메소)\s*[:：]?\s*([\d,]{1,13})\b',text)
    if match:
        try:return int(match.group(1).replace(',',''))
        except ValueError:pass
    return None
