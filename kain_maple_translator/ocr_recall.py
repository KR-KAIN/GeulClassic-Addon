"""Conservative OCR recall helpers: preserve independently readable rows."""
from __future__ import annotations
import re

from .core import parse_chat_line


def same_read(first, second):
    """Two preprocessings must agree exactly, including case and prices."""
    return bool(str(first).strip()) and ' '.join(str(first).split()) == ' '.join(str(second).split())


def merge_recovery_lines(primary, recovered):
    """Use detector reads per baseline, never erase unrelated primary rows.

    A detector may miss perfectly good lines while rescuing one weak line.
    Keep its fragments together on the same baseline; never concatenate two
    complete versions of a row. Preserve primary link metadata when possible.
    """
    if not recovered:
        return list(primary)
    kept = list(primary)
    groups = []
    for line in sorted(recovered, key=lambda r: (r.rect[1]+r.rect[3]/2, r.rect[0])):
        mid = line.rect[1]+line.rect[3]/2
        group = next((g for g in groups if abs(mid-(g[0].rect[1]+g[0].rect[3]/2))
                      <= min(7., max(3., min(line.rect[3], g[0].rect[3])*.40))), None)
        if group is None:
            groups.append([line])
        else:
            group.append(line)
    for group in groups:
        group.sort(key=lambda r: r.rect[0])
        # A complete detector row can overlap its separate CH badge/icon
        # boxes. Those boxes are not additional words in the seller's body.
        complete=[r for r in group if parse_chat_line(r.text) and r.confidence >= .8]
        # A recognizer can include one stray CH glyph in the full nickname
        # ('Corrupy c: ...'). That must not make its contained low-confidence
        # prefix ('Comupy :B') concatenate into a second sender/body. Source
        # containment on this same baseline is the evidence, not name fuzzing.
        broad=[r for r in group if r.confidence>=.90 and
               re.match(r'^[\w.\- ]{2,28}\s*[:：;；]\s*\S',r.text)]
        for candidate in broad:
            x,y,w,h=candidate.rect
            if any(other is not candidate and other.confidence<candidate.confidence
                   and w>=other.rect[2]*2
                   and other.rect[0]>=x-2
                   and other.rect[0]+other.rect[2]<=x+w+2 for other in group):
                complete.append(candidate)
        if complete:
            anchor=max(complete,key=lambda r:r.rect[2])
            ax,ay,aw,ah=anchor.rect
            group=[r for r in group if r is anchor or not
                   (r.rect[0] >= ax-2 and r.rect[0]+r.rect[2] <= ax+aw+2)]
        y0 = min(r.rect[1] for r in group)
        y1 = max(r.rect[1]+r.rect[3] for r in group)
        mid = (y0+y1)/2
        overlaps = [r for r in kept if abs(r.rect[1]+r.rect[3]/2-mid)
                    <= max(4., min(r.rect[3], y1-y0)*.45)]
        new_text = ' '.join(r.text for r in group)
        new_score = min(r.confidence for r in group)
        if not overlaps:
            kept.extend(group)
            continue
        old_text = ' '.join(r.text for r in sorted(overlaps, key=lambda r: r.rect[0]))
        old_score = min(r.confidence for r in overlaps)
        old_parsed, new_parsed = parse_chat_line(old_text), parse_chat_line(new_text)
        # Preserve R10's detector authority on an uncertain baseline. An
        # average confidence cannot validate every digit; selecting a high-
        # confidence primary here regressed 100MESO -> 10MESO in replay.
        # The change is spatial preservation, not a new numeric guesser.
        replace = bool(new_parsed and new_score >= .65 and
                       not same_read(old_text,new_text))
        # The full-frame detector reads the CH badge as letters, so on a
        # real 1080p megaphone it turned 'HolyArrow' into 'HolVAFERS' and
        # dropped every space, replacing a correct split read 8 times out of
        # 8. A confident row whose sender came from the badge/colon split
        # keeps its sender; the detector still repairs digits on rows
        # whose sender it reads identically, and any weak/unparsed row.
        if (replace and old_parsed and old_score >= .80 and
                old_parsed[0].casefold() != new_parsed[0].casefold()):
            replace = False
        if replace:
            ids = {id(r) for r in overlaps}
            kept = [r for r in kept if id(r) not in ids]
            kept.extend(group)
    return sorted(kept, key=lambda r: (r.rect[1], r.rect[0]))


def cache_ttl(text, confidence, stable_reads):
    """Do not spend every frame re-running deterministic OCR on identical ink.

    Weak/empty reads remain eligible for recovery; only repeated readable
    results get the long reuse window. Pixel-key changes bypass this policy.
    """
    parsed=parse_chat_line(text)
    if stable_reads >= 2 and parsed and ':' not in parsed[1]:
        from .uncertain_links import contains_uncertain_link
        if not contains_uncertain_link(text):
            if confidence >= .92:
                return 30.
            if confidence >= .82:
                return 8.
    return 2.5 if confidence >= .92 else (.45 if confidence >= .80 else .20)
