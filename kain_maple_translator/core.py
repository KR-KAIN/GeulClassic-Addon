"""Pure logic for regions, OCR filtering, de-duplication, and preferences."""
from __future__ import annotations
import json
import os
import re
import time
from pathlib import Path

ZONES = ("bubble", "chat", "trade")
ZONE_KO = {"bubble": "캐릭터 말풍선", "chat": "하단 채팅", "trade": "거래창"}
DEFAULTS = {
    "enabled": {"bubble": False, "chat": True, "trade": False},
    "regions": {"bubble": None, "chat": None, "trade": None},
    "intervals": {"bubble": 0.80, "chat": 0.55, "trade": 1.0},
    "output": "overlay", "opacity": 86, "font_size": 13, "theme_variant": "rounded",
    "floating_mode": "overlay", "top_mode": "game", "hud_panels_match": True, "pin_settings_above_game": False, "game_title_keyword": "maple",
    "game_resolution": "auto", "region_source": "manual", "relative_chat_region": None,
    "engine": "argos", "libre_url": "", "libre_key": "",
    "ocr_scale": 1.8, "show_original": False, "capture_interval": 0.08, "capture_backend": "wgc", "auto_chat_region": True, "source_chat_colors": True,
    "game_priority": False, "glyph_debug_enabled": False, "glyph_dictionary_enabled": False,
    "chat_geometry": {"width": 470, "height": 140, "free_x": None, "free_y": None,
                      "overlay_dx": 0, "overlay_dy": 0, "dock_match_height": True, "dock_width":470, "hud_match_height": False},
    # R18: chat keyword alerts, Free Market price log, low-potion warning
    "alert_keywords": [], "alert_popup": True, "alert_sound": True,
    "price_log_enabled": True, "hunt_potion_warn": 30,
    # Kept across restarts (load_config drops unknown keys): EXP meter
    # position / pin / hand-picked key area, and the one-time Z-order rescue
    # (without it 'top_mode' went back to 'game' on every start).
    "hunt_widget_pos": None, "hunt_widget_always_on_top": False,
    "hunt_window_order_v050_migrated": False, "hunt_keyboard_roi_rel": None,
    "stacking_v037_initialized": False,
    "split_ratio_general": 70, "megaphone_opacity": 92, "font_path": "", "font_url": "", "font_size": 13, "float_edit": False,
    "chat_style":{"nickname_color":"#b5d6ff","message_color":"#ffffff",
                  "background_color":"#111d31","nickname_bold":False,
                  "nickname_underline":False,"message_bold":False,
                  "message_underline":False},
}


def config_path() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".config")
    return Path(root) / "KAINMapleTranslator" / "config.json"


def load_config(path: Path | None = None) -> dict:
    dest = path or config_path()
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        data = {}
    base = json.loads(json.dumps(DEFAULTS))
    if isinstance(data, dict):
        for key in ("enabled", "regions", "intervals", "chat_style"):
            if isinstance(data.get(key), dict):
                for zone in base[key]:
                    if zone in data[key]:
                        base[key][zone] = data[key][zone]
        for key in base:
            if key not in ("enabled", "regions", "intervals", "chat_style", "chat_geometry") and key in data:
                base[key] = data[key]
    if isinstance(data.get("chat_geometry"), dict):
        base["chat_geometry"].update({k: v for k, v in data["chat_geometry"].items()
                                      if k in base["chat_geometry"]})
    return base


def save_config(data: dict, path: Path | None = None) -> None:
    dest = path or config_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write so a power failure does not destroy the saved regions.
    staging = dest.with_suffix(".tmp")
    staging.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(staging, dest)


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def likely_english(text: str, confidence: float = 1.0) -> bool:
    if confidence < 0.30 or len(text.strip()) < 2 or len(text) > 230:
        return False
    outside = re.sub(r'\[[^\]\n]*\]', ' ', text)
    latin = len(re.findall(r"[a-zA-Z]", outside))
    hangul = len(re.findall(r"[가-힣]", outside))
    if re.match(r"\s*[SBTRJ]\s*[>＞〉]\s*\S", text, re.I):
        return confidence >= 0.30
    return latin >= 2 and latin >= hangul * 2



def should_translate_body(text: str, confidence: float = 1.0) -> bool:
    """Pass mixed Korean/English market notices to the translator too.

    Previously these were misclassified as 'already Korean' and forwarded
    verbatim, leaving S>, PMO, scroll names etc. untranslated. The actual
    Korean item titles are preserved later in the translation pipeline.
    """
    if confidence < 0.30 or len(text.strip()) < 2 or len(text) > 240:
        return False
    if re.match(r'^\s*(?:[SBTRJ]\s*[>＞〉]|WTS\b|WTB\b|WTT\b|SELLING\b|BUYING\b|TRADING\b|LF\s*[>＞〉])', text, re.I):
        return True
    # A linked Korean item may be followed by a short English trade phrase;
    # the Hangul count must not suppress these mixed-language announcements.
    from .megaphone_item_translation import _TRADE_MARKERS, _BRACKETED_ITEM_OFFER, _OFFER_REQUEST
    if _TRADE_MARKERS.search(text):
        return True
    if re.search(r'\b(?:for\s+\d+(?:\.\d+)?\s*[kmb]|also\s+have|pm\s+offer)\b',text,re.I):
        return True
    if re.search(r'[A-Za-z]{3,}',text) and re.search(r'(?:팝니다|삽니다|판매|구매)',text):
        return True
    offer=_BRACKETED_ITEM_OFFER.fullmatch(text.strip())
    if offer and _OFFER_REQUEST.fullmatch(offer.group(2)):
        return True
    outside=re.sub(r'\[[^\]]*\]','',text).strip()
    # R18 live: a megaphone that is only an English item link ('[Evil Skull]')
    # must reach the translator so the item name is localized.
    if not outside and re.search(r'\[[^\]]*[A-Za-z]{3,}[^\]]*\]',text):
        return True
    if re.search(r'(?i)\b(?:selling|buying|wts|wtb|pmo|obo|pls|plz|ty|thx)\b',outside):
        return True
    # Recognizable equipment abbreviations and scroll phrases can be mixed
    # with Hangul without being an already-translated Korean chat line.
    if re.search(r'(?i)(?<![A-Za-z0-9_])(?:m\.att|matt|w\.atk|att|atk|str|dex|int|luk|gfa|gfma|gma|css|ws|cs|pmo|obo|scrolls?|slots?|offers?|mesos?|clean|no\s+slots\s+left)(?![A-Za-z0-9_])',outside):
        return True
    if re.search(r'(?i)(?<![A-Za-z0-9_])\d+(?:\.\d+)?\s*[kmb](?![A-Za-z0-9_])',outside):
        return True
    return likely_english(outside, confidence)

def is_valid_region(box: dict | None) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        return (int(box["width"]) >= 50 and int(box["height"]) >= 25
                and -50000 <= int(box["left"]) <= 50000
                and -50000 <= int(box["top"]) <= 50000)
    except (ValueError, KeyError, TypeError):
        return False


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


class RepeatGuard:
    def __init__(self, seconds: float = 1.8):
        self.seconds = seconds
        self.entries: dict[tuple[str, str], float] = {}

    def is_new(self, zone: str, text: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        key = (zone, normalized(text))
        last = self.entries.get(key)
        new = last is None or now - last >= self.seconds
        if new:
            self.entries[key] = now
        if len(self.entries) > 350:
            self.entries = {k: v for k, v in self.entries.items() if now - v < 30}
        return new


def glossary_exact(text: str, direction: str) -> str | None:
    """Compatibility entrypoint for game-specific fast translation rules."""
    from .glossary import rule_translate
    return rule_translate(text, direction)


# Maple's bottom chat shows speaker and message on the same row. Never translate
# the speaker handle. When OCR splits a line into boxes, join adjacent boxes
# on their screen-space baseline before parsing.
# Maple channel badges are often placed between nickname and colon, e.g.
# "bByou CH 09 (red badge) : S> item 2m". Treat them as UI metadata,
# never send them to MT and never mistake them for nicknames.
CHAT_PATTERN = re.compile(r"^([\w][\w.\-]{1,23})\s*[:：;；]\s*(\S.*)$", re.UNICODE)
CHANNEL_TAG = re.compile(r"(?i)(?:\[|\()?\s*CH\s*[O0-9]{1,3}\s*(?:\]|\))?")
CHATTEXT_SUFFIX = re.compile(r"^[\s\|\-:：<>\[\](){}○●◉◎⑨◌〃•·♣♢♥♡+]*")


def parse_chat_line(text: str) -> tuple[str, str] | None:
    # URLs also contain a colon; never mistake https://domain for a player
    # called "https" when OCR inserts spaces around the delimiter.
    from .chat_safety import has_url_or_domain
    if has_url_or_domain(text) and re.match(r'^\s*https?\s*:', text, re.I):
        return None
    value = re.sub(r"\s+", " ", text).strip()
    value = re.sub(r"^(?:\[)?\d{1,2}:\d{2}(?::\d{2})?(?:\])?\s+", "", value)
    # A nickname + optional CH badge + colon, with OCR decorations between.
    # Do not permit arbitrary long gap: prevents unrelated text from being named speaker.
    leading = re.match(r"^([\w][\w.\-]{1,23})\s*(.*)$", value, re.UNICODE)
    if not leading:
        return None
    nick, tail = leading.groups()
    if not (2 <= len(nick) <= 24):
        return None
    # A clipped left edge can leave ONLY the CH05 badge. OCR often reads it
    # as CHOS/cHos; it is channel metadata, not an invented player nickname.
    if re.fullmatch(r'CH[0-9OS]{1,3}', nick, re.I):
        return None
    tail = tail.lstrip()
    channel = CHANNEL_TAG.match(tail)
    if channel:
        tail = tail[channel.end():].lstrip()
        # Channel badge OCR frequently adds one tiny non-ASCII symbol before ':'
        tail = re.sub(r"^[^\w:：;；<>]{0,5}(?=[:：;；])", "", tail)
    # Channel-badge messages may have the colon lost by OCR. In that case
    # require the badge; avoid guessing speaker for arbitrary prose.
    if tail.startswith((':','：',';','；')):
        tail = tail[1:].lstrip()
    elif not channel:
        tail = re.sub(r'^[^\w:：;；<>]{1,5}(?=\s*[:：;；])', '', tail).lstrip()
        if tail.startswith((':','：',';','；')):
            tail = tail[1:].lstrip()
        else:
            return None
    else:
        tail = CHATTEXT_SUFFIX.sub('', tail).lstrip()
    if not tail or len(tail) > 240:
        return None
    # When OCR glued the badge to the nickname (e.g. NickCH09:), prefer
    # conservative behavior and let another frame retry rather than inventing.
    return nick, tail


def _source_regions(lines, x, y, *, continuation=False):
    """Keep palette bounds on their own visual row when text wraps."""
    body=[];items=[]
    for line in lines:
        lx,ly,lw,lh=line.rect
        meta=getattr(line,'source_meta',{}) or {}
        start=0 if continuation else meta.get('body_start',min(lw//3,110))
        body.append((lx-x+int(start),ly-y,lx-x+lw,ly-y+lh))
        for x0,x1 in meta.get('item_ranges',[]):
            items.append((lx-x+int(x0),ly-y,lx-x+int(x1),ly-y+lh))
    return body,items


def merge_chat_ocr(lines: list, background_at=None) -> list[dict]:
    """Join OCR text boxes from the same baseline, returning chat rows only.

    Accepts records exposing .text, .rect=(x,y,w,h), .confidence. Pure Python,
    so tests can run without RapidOCR, OpenCV, or the actual Maple game.
    """
    accepted = [line for line in lines if getattr(line, 'text', '').strip() and
                float(getattr(line, 'confidence', 0)) >= 0.30]
    accepted.sort(key=lambda item: (item.rect[1] + item.rect[3] / 2, item.rect[0]))
    rows: list[list] = []
    for line in accepted:
        mid = line.rect[1] + line.rect[3] / 2
        nearest = None
        nearest_distance = float('inf')
        for row in rows:
            median = sum(box.rect[1] + box.rect[3] / 2 for box in row) / len(row)
            dist = abs(mid - median)
            tolerance = min(7.0, max(3.0, min(line.rect[3], row[0].rect[3]) * 0.40))
            if dist <= tolerance and dist < nearest_distance:
                nearest, nearest_distance = row, dist
        if nearest is None:
            rows.append([line])
        else:
            nearest.append(line)
    result = []
    for row in sorted(rows, key=lambda group: min(item.rect[1] for item in group)):
        row.sort(key=lambda item: item.rect[0])
        contiguous=[]
        for item in row:
            if contiguous:
                right=max(v.rect[0]+v.rect[2] for v in contiguous)
                prefix=' '.join(v.text.strip() for v in contiguous)
                if parse_chat_line(prefix) and item.rect[0]-right > max(32,item.rect[3]*2.2):
                    break
            contiguous.append(item)
        row=contiguous
        joined = ' '.join(item.text.strip() for item in row)
        parsed = parse_chat_line(joined)
        if not parsed:
            # A wrapped attention-only tail is not message content. Its OCR
            # confidence must not invalidate the fully readable first line.
            # Preserve any leading digit/letter (it may finish a wrapped
            # price or word); only @-starting decoration may be ignored.
            decoration=joined.strip()
            if (decoration.startswith('@') and decoration.count('@')>=4 and
                    all(c in '@ \t0123456789①②③④⑤⑥⑦⑧⑨⓪' for c in decoration)):
                continue
            # A message spanning two in-game chat rows has no nickname on
            # its second line. Attach *only* a nearby visual continuation;
            # never turn unrelated text or a new speaker into a continuation.
            # A failed name/body split is still evidence of a separate
            # speaker. In the R14 recording, losing bihh's delimiter made
            # that entire offer attach to DUSTIN's wrapped announcement.
            # Keep the genuine continuation above it, but wait for another
            # read of this independent row instead of changing its author.
            independent_prefix = any(
                0 < (getattr(item, 'source_meta', {}) or {}).get('name_end', 0)
                < (getattr(item, 'source_meta', {}) or {}).get('body_start', 0)
                < item.rect[2]
                for item in row)
            if (result and joined and not independent_prefix
                    and not re.search(r'\bhttps?://|[:：;；]',joined,re.I)):
                prev=result[-1]
                current_y=min(item.rect[1] for item in row)
                prev_x,prev_y,prev_w,prev_h=prev['rect']
                # Expanded line crops may overlap by several pixels: this is
                # still the same vertically wrapped Maple message.
                gap=current_y-(prev_y+prev_h)
                start_x=min(item.rect[0] for item in row)
                current_rect = (start_x, current_y,
                    max(item.rect[0]+item.rect[2] for item in row)-start_x,
                    max(item.rect[1]+item.rect[3] for item in row)-current_y)
                if background_at is not None and background_at(current_rect) != prev.get('source_band_tone'):
                    continue
                if -5<=gap<=11 and start_x>=prev_x-15 and start_x<=prev_x+max(60,int(prev_w*.6)):
                    if len(prev['body'])+len(joined)<240:
                        prev['body'] += ' '+joined
                        body_regions,item_regions=_source_regions(row,prev_x,prev_y,continuation=True)
                        prev['source_meta']['body_regions'].extend(body_regions)
                        prev['source_meta']['item_regions'].extend(item_regions)
                        if prev.get('visual_key') and all(getattr(item,'ink_key','') for item in row):
                            prev['visual_key']+='/'+'/'.join(item.ink_key for item in row)
                        else:prev['visual_key']=''
                        prev['rect']=(prev_x,prev_y,max(prev_w,max(item.rect[0]+item.rect[2] for item in row)-prev_x),
                                      max(item.rect[1]+item.rect[3] for item in row)-prev_y)
                        prev['confidence']=min(prev['confidence'],*(float(item.confidence) for item in row))
                        prev['source_meta']['paired_read'] = bool(prev['source_meta'].get('paired_read')) and all(
                            (getattr(item,'source_meta',{}) or {}).get('paired_read') is True for item in row)
            continue
        name, body = parsed
        x = min(item.rect[0] for item in row)
        y = min(item.rect[1] for item in row)
        r = max(item.rect[0] + item.rect[2] for item in row)
        b = max(item.rect[1] + item.rect[3] for item in row)
        source_meta=dict(getattr(row[0],'source_meta',{}) or {})
        source_meta['paired_read'] = all((getattr(item,'source_meta',{}) or {}).get('paired_read') is True for item in row)
        source_meta['body_regions'],source_meta['item_regions']=_source_regions(row,x,y)
        result.append({'nickname': name, 'body': body, 'rect': (x,y,r-x,b-y),
                       'source_band_tone': background_at((x,y,r-x,b-y)) if background_at else None,
                       'announcement_hint': any(getattr(item,'channel_hint',False) for item in row) or bool(re.match(r'^[\w.\-]{2,24}\s*[\[(]?\s*CH\s*[O0-9]{1,3}\b', joined, re.I)),
                       'confidence': min(float(item.confidence) for item in row),
                       'source_meta':source_meta,
                       'visual_key':'/'.join(getattr(item,'ink_key','') for item in row) if all(getattr(item,'ink_key','') for item in row) else ''})
    return result


class ChatFrameTracker:
    """Deduplicate unchanged screen rows, but permit an identical new message.

    Based on sequence overlap between *consecutive OCR frames*. Repeated text
    later in the history doesn't reappear until it is observed as a new row.
    """
    def __init__(self):
        self.previous: list[str] = []

    @staticmethod
    def _same(a, b, *, moved_visual=False) -> bool:
        # Each record is (normalized_text, visual_key, repeated_in_frame).
        # Text is stable when the translucent background animates. Visual
        # identity is only a tie-breaker for repeated identical visible rows,
        # or a rescue for small OCR drift with unchanged pixels.
        at, av, ad = a
        bt, bv, bd = b
        if at == bt:
            # An animated chat background changes the pixel hash even when
            # repeated text is unchanged. However, a stable visual key moving
            # to a different row is evidence of a real scroll/new arrival.
            if moved_visual and ad and bd and av and bv and av != bv:
                return False
            return True
        an, _, am = at.partition(':')
        bn, _, bm = bt.partition(':')
        if an != bn:
            return False
        if re.findall(r'\d+(?:[.,]\d+)*', am) != re.findall(r'\d+(?:[.,]\d+)*', bm):
            return False
        if av and bv and av == bv:
            # A weak/colliding ink signature is not proof that two DIFFERENT
            # messages are the same. Only rescue small OCR spelling jitter;
            # never suppress a new short message on visual-hash collision.
            from difflib import SequenceMatcher
            if len(am)>=6 and len(bm)>=6 and SequenceMatcher(None,am,bm).ratio()>=.83:
                return True
            # A single misread Hangul glyph (장갑 → 장감) on the exact
            # unchanged ink patch is an OCR retry, not a new message.
            if (2<=len(am)==len(bm)<=5 and
                    any('가'<=c<='힣' for c in am+bm) and
                    sum(x!=y for x,y in zip(am,bm))<=1):
                return True
        if len(am) < 12 or len(bm) < 12:
            return False
        ca = re.sub(r'[\s.!?,;~…]+', '', am)
        cb = re.sub(r'[\s.!?,;~…]+', '', bm)
        return ca == cb

    def new(self, rows: list[dict]) -> list[dict]:
        # The game background moves under translucent chat rows. Exact ink
        # bytes drift even when the *same* message stays on screen. Use OCR
        # identity first, not visual hash; keep visual fallback for unreadable
        # fragments only. Deliberately do NOT globally suppress repeated text:
        # repeated messages entering below the overlap are legitimate events.
        strings = [normalized(str(row.get('nickname','')) + ':' + str(row.get('body','')))
                   if str(row.get('nickname','')).strip() and str(row.get('body','')).strip()
                   else 'ink:' + str(row.get('visual_key','')) for row in rows]
        duplicates = {item for item in strings if strings.count(item)>1}
        current = [(item, str(row.get('visual_key','')), item in duplicates)
                   for item,row in zip(strings,rows)]
        # An identical repeated row whose stable visual signature moved from
        # index 1 to index 0 indicates a scroll. Treat identical strings at
        # the same index as stationary only if no such movement is observed.
        previous_keys={v:i for i,(_t,v,dup) in enumerate(self.previous) if dup and v}
        moved_visual=any(dup and v in previous_keys and previous_keys[v]!=i
                         for i,(_t,v,dup) in enumerate(current))
        if not current or (len(current) == len(self.previous) and all(self._same(a, b, moved_visual=moved_visual) for a, b in zip(current, self.previous))):
            return []
        # A momentarily incomplete OCR frame must not erase prior context:
        # the next full frame would otherwise re-emit old chat history.
        if len(current) < len(self.previous) and all(any(self._same(x, p, moved_visual=moved_visual) for p in self.previous) for x in current):
            return []
        if not self.previous:
            self.previous = current
            return rows
        overlap = 0
        for count in range(min(len(current), len(self.previous)), 0, -1):
            if all(self._same(a, b, moved_visual=moved_visual) for a, b in zip(self.previous[-count:], current[:count])):
                overlap = count
                break
        # When the OCR changes a single old line slightly, avoid spamming the
        # whole log: only accept new rows at the bottom after matching a suffix.
        anchors = []
        if overlap == 0 and current:
            # Screen-scroll anchors may move even with a one-line OCR dropout.
            # Match stable previous rows, then admit only content BELOW the
            # latest anchor; NEVER re-emit the entire old screen as a fallback
            # when at least one old row is still visible.
            anchors = [i for i, x in enumerate(current) if any(self._same(x, old) for old in self.previous)]
            # Older unmatched lines ABOVE a known anchor are OCR drift, not
            # newly arriving bottom chat. Keep only the suffix after it.
            new_rows = rows[max(anchors)+1:] if anchors else rows
        else:
            new_rows = rows[overlap:]
        self.previous = current
        if overlap or anchors or moved_visual:
            # A newly arriving suffix after a MATCHED older row is bottom
            # entry evidence, even if the same nickname/text was posted again
            # within 2 seconds and occupies the previous bottom row's Y.
            # Do not use text-only TTL to suppress this legitimate repeat.
            for item in new_rows:
                item['_bottom_arrival'] = True
                if moved_visual:
                    item['_new_visual_evidence'] = True
        return new_rows
