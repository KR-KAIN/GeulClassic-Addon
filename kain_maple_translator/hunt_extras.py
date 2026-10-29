"""EXP meter extras (R18): EXP per hour, level-up ETA, potion time left,
low-potion alerts and a saved hunting log. Pure logic, no Qt."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

MIN_RATE_SECONDS = 20.0   # a rate from the first seconds is noise


def exp_per_hour(session) -> int | None:
    secs = float(session.elapsed_seconds)
    if secs < MIN_RATE_SECONDS or session.gained_exp <= 0:
        return None
    return int(round(session.gained_exp*3600/secs))


def level_up_seconds(session) -> float | None:
    """Seconds to the next level at the current pace, or None."""
    secs = float(session.elapsed_seconds)
    if secs < MIN_RATE_SECONDS:
        return None
    exp, pct = session.last_exp, session.last_percent
    # EXP-based: requirement = exp*100/percent for this level
    if session.gained_exp > 0 and exp and pct and 0.1 <= pct < 100:
        need = exp*100.0/pct-exp
        return max(0.0, need/(session.gained_exp/secs))
    # Percent-based when the EXP number is unreadable
    gained_pct = getattr(session, 'gained_percent', 0.0)
    if gained_pct > 0 and pct is not None and pct < 100:
        return max(0.0, (100.0-pct)/(gained_pct/secs))
    return None


def potion_minutes(record, elapsed_seconds: float) -> float | None:
    """Minutes the remaining stack lasts at this session's usage pace."""
    if record is None or record.last_count is None or record.spent <= 0 or elapsed_seconds < MIN_RATE_SECONDS:
        return None
    per_minute = record.spent/(elapsed_seconds/60.0)
    return record.last_count/per_minute if per_minute > 0 else None


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return '—'
    seconds = int(seconds)
    if seconds < 60:
        return '1분 미만'
    hours, minutes = divmod(seconds//60, 60)
    if hours >= 100:
        return '100시간+'
    if hours:
        return f'{hours}시간 {minutes}분' if minutes else f'{hours}시간'
    return f'{minutes}분'


def format_amount(value: int | None) -> str:
    """Korean compact units for a small cell: 12,345 / 123.4만 / 1.2억."""
    if value is None:
        return '—'
    value = int(value)
    if value >= 100_000_000:
        return f'{value/100_000_000:.1f}억'
    if value >= 100_000:
        return f'{value/10_000:.1f}만'.replace('.0만', '만')
    return f'{value:,}'


def low_potion_slots(session, threshold: int) -> list[str]:
    """Slots whose current stack is at or below the warning count."""
    if threshold <= 0:
        return []
    return [key for key, rec in session.slots.items()
            if rec.last_count is not None and rec.initial_count and rec.last_count <= threshold]


# ------------------------------------------------------------- hunt log
def hunt_log_path() -> Path:
    root = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME') or tempfile.gettempdir()
    return Path(root)/'KAINMapleTranslator'/'hunt-log.json'


def load_hunt_log(path: Path | None = None) -> list[dict]:
    path = path or hunt_log_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_hunt_log(rows: list[dict], path: Path | None = None) -> None:
    path = path or hunt_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(rows[-500:], ensure_ascii=False, indent=1), encoding='utf-8')
        tmp.replace(path)
    except OSError:
        pass


def session_record(session, place: str = '', when: float | None = None) -> dict | None:
    """One finished hunt, or None when nothing was measured."""
    secs = int(session.elapsed_seconds)
    used = {key: rec.spent for key, rec in session.slots.items() if rec.spent}
    if secs < 10 and not session.gained_exp:
        return None
    return {
        'started': time.strftime('%Y-%m-%d %H:%M', time.localtime((when or time.time())-secs)),
        'seconds': secs,
        'place': place,
        'start_level': session.start_level,
        'end_level': session.last_level,
        'gained_exp': int(session.gained_exp),
        'gained_percent': round(float(getattr(session, 'gained_percent', 0.0)), 2),
        'exp_per_hour': exp_per_hour(session) or 0,
        'potions': used,
        'potions_total': sum(used.values()),
    }


def append_hunt(record: dict | None, path: Path | None = None) -> list[dict]:
    rows = load_hunt_log(path)
    if record:
        rows.append(record)
        save_hunt_log(rows, path)
    return rows
