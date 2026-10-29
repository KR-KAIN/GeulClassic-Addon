"""Keep unconfirmed OCR fragments out of ordinary chat history."""
from collections import OrderedDict
import re
import copy
import hashlib

_CLASSIFIED_CACHE=OrderedDict()
_BADGE_VALIDATOR=None


def starts_inside_verified_badge(row, image, left, top):
    """Reject a detector crop that starts at CH instead of the sender.

    The new video repeatedly reads Sioo's CH03 badge as Ho3/o3/co3. Only
    inspect offset, unsplit coloured rows; a complete verified badge and its
    following delimiter must independently be visible in the source image.
    """
    global _BADGE_VALIDATOR
    x,y,w,h=row['rect']
    meta=row.get('source_meta') or {}
    if (x-left<=12 or row.get('kind','normal')=='normal' or
            row.get('announcement_hint') or meta.get('body_start',0)>0):
        return False
    a=max(0,y-top);b=min(image.shape[0],y-top+h)
    if b-a<8:return False
    from .badge_split import BadgeSplitter
    from .fast_vision import neutral_ink
    if _BADGE_VALIDATOR is None:_BADGE_VALIDATOR=BadgeSplitter()
    crop=image[a:b]
    split=_BADGE_VALIDATOR.split(crop,neutral_ink(crop))
    return bool(split and x-left>=split[0]-4 and x-left<split[1])


def classified_chat_rows(lines, image, left, top):
    from .core import merge_chat_ocr
    from .megaphone import row_appearance
    from .system_notices import merge_red_notices
    key=(hashlib.blake2b(image.tobytes()+str(image.shape).encode(),digest_size=16).digest(),left,top,
         tuple((line.text,float(line.confidence),tuple(line.rect),getattr(line,'channel_hint',False),
                getattr(line,'ink_key',''),repr(getattr(line,'source_meta',{}))) for line in lines))
    cached=_CLASSIFIED_CACHE.get(key)
    if cached is not None:
        _CLASSIFIED_CACHE.move_to_end(key)
        return copy.deepcopy(cached)
    origin = (left, top)
    rows = merge_chat_ocr(lines, background_at=lambda rect: row_appearance(image, rect, origin, '').get('tone'))
    for row in rows:
        row.update(row_appearance(image, row['rect'], origin, row['body'],row.get('source_meta')))
        if row.get('announcement_hint') and row.get('kind') == 'normal' and not row.get('source_white_body'):
            row.update(kind='unknown', prefix='[확성]', tone='uncertain')
        # No coloured banner or CH badge normally means general chat.
        # Exception: row_appearance has independently verified consistently
        # coloured BODY glyphs from the source pixels (not from OCR text and
        # not from a potentially wrong palette/foreground sample). v0.4.30
        # mistakenly discarded this evidence, breaking the real OCR replay.
        if (row.get('kind') != 'normal' and not row.get('band_color')
                and not row.get('announcement_hint')
                and row.get('glyph_color_confirmed') is not True):
            row.update(kind='normal', prefix='', tone='none', band_color='')
    for notice in merge_red_notices(lines, image, left, top):
        nx, ny, nw, nh = notice['rect']
        rows = [r for r in rows if not (ny <= r['rect'][1]+r['rect'][3]/2 <= ny+nh)]
    rows=dedupe_exact_overlaps([row for row in rows if not is_at_only_noise(row.get('body',''))
                               and not starts_inside_verified_badge(row,image,left,top)])
    rows=sorted(rows, key=lambda row: (row['rect'][1], row['rect'][0]))
    _CLASSIFIED_CACHE[key]=copy.deepcopy(rows)
    while len(_CLASSIFIED_CACHE)>16:_CLASSIFIED_CACHE.popitem(last=False)
    return rows


def is_at_only_noise(body):
    """Discard bare @ OCR artifacts, never @ inside ordinary chat or links.

    This is deliberately applied *after* raw OCR, never to the source image
    or the glyph learner. NFKC covers wide/fullwidth @ without touching text.
    """
    import unicodedata
    text=unicodedata.normalize('NFKC', str(body or ''))
    return '@' in text and all(char=='@' or char.isspace() for char in text)


def dedupe_exact_overlaps(rows):
    """Suppress only the SAME rendered text duplicated in the SAME rectangle.

    Identical trade postings at different screen positions are independent
    physical events and MUST survive. Never use a global 90%/10s blacklist.
    """
    kept=[]
    for row in rows:
        rect=row.get('rect') or (0,0,0,0)
        x,y,w,h=(int(v) for v in rect)
        if w<=0 or h<=0:
            kept.append(row)
            continue
        duplicate=False
        for previous in kept:
            if (previous.get('nickname'),previous.get('body'),previous.get('kind')) != (row.get('nickname'),row.get('body'),row.get('kind')):
                continue
            px,py,pw,ph=(int(v) for v in (previous.get('rect') or (0,0,0,0)))
            intersection=max(0,min(x+w,px+pw)-max(x,px))*max(0,min(y+h,py+ph)-max(y,py))
            union=w*h+pw*ph-intersection
            if union>0 and intersection/union>=.85:
                duplicate=True
                break
        if not duplicate:
            kept.append(row)
    return kept


class RowAdmission:
    def __init__(self):
        self.seen = OrderedDict()
        self.pending = 0
        self.rejected = 0
        self.announcements = OrderedDict()

    def _similar_sighting(self, key, occurrence, captured_at):
        """Second read of the same long line with tiny OCR jitter.

        Spam such as 'J>PQ @@@@@...' or a long trade line rarely reads
        character-identical twice ('@' counts, a stray glyph), so it never
        reached two sightings and was dropped. Accept the ledger's own
        same-message test: same sender, identical numbers, >=91% of the text.
        """
        from .visual_message_ledger import same
        row = {'nickname': key[0], 'body': key[1]}
        for seen_key in reversed(self.seen):
            if seen_key[2] != occurrence:
                continue
            previous = self.seen[seen_key]
            if captured_at-previous[1] >= 2.5:
                break
            if seen_key[:2] != key and same({'nickname': seen_key[0], 'body': seen_key[1]}, row):
                return previous
        return None

    def filter(self, rows, captured_at):
        accepted = []
        self.pending = 0
        occurrences = {}
        for row in rows:
            key = (row['nickname'], re.sub(r'\s+', ' ', row['body']).strip())
            # The same player can post identical text in ordinary chat and
            # then over a megaphone (or vice versa). Do not inherit channel
            # classification from text/history. Source pixels and the verified
            # CH marker must determine classification on EACH frame.
            if row.get('kind', 'normal') != 'normal':
                self.announcements[key] = (captured_at, {k: row.get(k, '') for k in ('kind','prefix','tone','band_color','text_color','nickname_color','item_color')})
                self.announcements.move_to_end(key)
                accepted.append(row)
                continue
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence+1
            seen_key = (*key, occurrence)
            previous = self.seen.get(seen_key)
            if previous is None:
                previous = self._similar_sighting(key, occurrence, captured_at)
            count = 1
            first_seen = captured_at
            elapsed=captured_at-previous[1] if previous else 0.
            ink=row.get('visual_key','')
            same_ink=bool(previous and len(previous)>3 and ink and previous[3]==ink)
            # A slow inference can outlive the old 2.5s admission window.
            # Extend only with identical source ink, not matching text alone.
            if previous and 0 < elapsed and (elapsed<2.5 or (same_ink and elapsed<12.)):
                count = previous[0]+1
                first_seen = previous[2]
            self.seen[seen_key] = (count, captured_at, first_seen, ink)
            self.seen.move_to_end(seen_key)
            # A sufficiently certain white-on-transparent player chat may
            # disappear from a four-line chat box before a second OCR pass.
            # Require a verified white body and a fully parsed, nontrivial
            # message. Uncertain/short fragments still need two sightings.
            confidence=float(row.get('confidence',0))
            body=str(row.get('body','')).strip()
            nickname=str(row.get('nickname','')).strip()
            verified_white=row.get('source_white_body') is True
            reliable_single = (verified_white and confidence >= .94
                               and len(body) >= 3 and len(nickname) >= 2)
            # In the 4-row game chat, a long, high-confidence trade notice
            # can disappear before we see the next frame. Admit a single
            # sighting ONLY when pixels independently confirm a white-body
            # general-chat line and it contains an unambiguous trade marker.
            # Avoid making generic OCR noise or coloured megaphones pass.
            clear_trade = bool(re.search(
                r'(?i)(?:^\s*(?:[SBTR]\s*[>＞〉]|WTS\b|WTB\b|WTT\b|SELLING\b|BUYING\b)|'
                r'\b(?:selling|buying|wts|wtb)\b)', body))
            fast_trade = (verified_white and confidence >= .87 and
                          len(body) >= 6 and len(nickname) >= 2 and clear_trade)
            # Two genuinely different preprocessings of this very frame can
            # confirm a line that scrolls out before the next capture. This
            # flag is produced by OCR agreement, never inferred from text.
            paired_read = (verified_white and confidence >= .82 and
                           len(body) >= 2 and len(nickname) >= 2 and
                           (row.get('source_meta') or {}).get('paired_read') is True)
            if (count >= 2 and confidence >= .55) or reliable_single or fast_trade or paired_read:
                row['first_observed_at'] = first_seen
                accepted.append(row)
            else:
                self.pending += 1
                if count >= 2:
                    self.rejected += 1
        while len(self.seen) > 512:
            self.seen.popitem(last=False)
        while len(self.announcements) > 512:
            self.announcements.popitem(last=False)
        return accepted
