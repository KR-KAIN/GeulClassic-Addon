"""Capture-frame message identities: one output per physical on-screen arrival.

This is deliberately independent of per-frame OCR admission. The first OCR
reading can be unconfirmed; once it is admitted, we still deliver that SAME
message ID once. Repeated text in a newly appearing bottom slot gets a NEW ID.
"""
from __future__ import annotations
from difflib import SequenceMatcher
import re
import unicodedata
from .core import normalized


def identity(row):
    def surface(value):
        text=unicodedata.normalize('NFKC',str(value))
        text=re.sub(r'[\u200b-\u200d\ufeff]','',text)
        # The same printed channel range was read as both 3-12 and 3–12
        # in the R14 recording. Normalize the glyph, never remove its sign.
        text=re.sub(r'[\u2010-\u2015\u2212]', '-', text)
        # A long attention suffix repeatedly acquired one trailing OCR
        # digit (including a circled digit after NFKC). Its count is not a
        # message identity. Only digits attached to a contiguous terminal @
        # run are removed; prices and words after it stay in the comparison.
        text=re.sub(r'(@{4,})[0-9]{1,2}$', r'\1', text.rstrip())
        # Presentation spacing around links is often unstable in OCR. Keep
        # numeric signs, decimals, quantities and trade direction intact.
        text=re.sub(r'\s*([\[\]])\s*',r'\1',text)
        return normalized(text)
    return surface(row.get('nickname','')),surface(row.get('body',''))


def _fold(text):
    # OCR reads plain Latin letters with accents ('ZombiéLupin').
    return ''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c))


def _one_glyph_apart(a,b):
    """Levenshtein distance <= 1 after accent folding."""
    a,b=_fold(a),_fold(b)
    if a==b:return True
    if abs(len(a)-len(b))>1:return False
    if len(a)>len(b):a,b=b,a
    i=0
    while i<len(a) and a[i]==b[i]:i+=1
    return a[i+(len(a)==len(b)):]==b[i+1:]


_NUMBERS=r'[+-]?\d+(?:[.,]\d+)*(?:\s*(?:%|[kmb]\b))?'


def strip_symbol_spam(text):
    """Drop '@@@@'-style attention spam tokens before comparing two reads.

    OCR reads long '@' runs with a different count each time and sprinkles
    look-alike glyphs into them ('@@660@', '@④@'), so the same trade line
    ('S> 60% ATK SCROLL BOW 100K @@@@...') never compared equal twice and
    was never confirmed. The words and prices around the spam must match.
    """
    kept=[]
    for t in str(text).split():
        if (t.count('@')>=3 and t.count('@')>=len(t)*.6) or '@@@' in t:
            # 'ore@@@@@@' keeps its word ('ore'); '@@660@' is pure spam.
            core=t.strip('@')
            if core.isalpha() and len(core)>=2 and '@' not in core:
                kept.append(core)
            continue
        kept.append(t)
    return ' '.join(kept)


def _leading_glyph_misread(a,b):
    """Same nickname except its FIRST glyph ('PoloYoloBen'/'2oloYoloBen'/
    'oloYoloBen'): the chat box edge clips or blurs the first character."""
    a,b=_fold(a),_fold(b)
    if len(a)<len(b):a,b=b,a
    if len(b)<5:return False
    return a[1:]==b or (len(a)==len(b) and a[1:]==b[1:])


def same(a,b):
    # An identical foreground key is evidence about the source pixels, not
    # just a similar OCR sentence. Still used only by ordered slot matching.
    if a.get('visual_key') and a.get('visual_key') == b.get('visual_key'):
        return True
    x,y=identity(a),identity(b)
    if x==y:return True
    if not x[0] or not y[0]:return False
    left,right=strip_symbol_spam(x[1]),strip_symbol_spam(y[1])
    if not left or not right:
        left,right=x[1],y[1]
    # One misread glyph on a re-read of the same line (real 1080p footage:
    # RoxasXI/RoxasXl/FoxasXI, BobDaSnail/BobDaSnait, jpq/lpq) used to be
    # delivered again as a brand-new message. Numbers must still match.
    if re.findall(_NUMBERS,left)==re.findall(_NUMBERS,right):
        # A short reply ('yes') from a one-glyph-different name may be a
        # different player; only longer identical bodies prove the sender.
        if (_fold(left)==_fold(right) and len(left)>=6 and min(len(x[0]),len(y[0]))>=4 and _one_glyph_apart(x[0],y[0])
                and re.findall(r'\d+',x[0])==re.findall(r'\d+',y[0])):
            return True
        if _fold(left)==_fold(right) and len(left)>=6 and _leading_glyph_misread(x[0],y[0]):
            return True
        if _fold(x[0])==_fold(y[0]) and min(len(left),len(right))>=3 and _one_glyph_apart(left,right):
            return True
        # One glyph off in BOTH sender and a not-too-short body
        # ('TelAvivIL : we need CC' / 'TelAvivL : _we need CC').
        if (min(len(x[0]),len(y[0]))>=4 and min(len(left),len(right))>=6
                and _one_glyph_apart(x[0],y[0]) and _one_glyph_apart(left,right)
                and re.findall(r'\d+',x[0])==re.findall(r'\d+',y[0])):
            return True
    # OCR may confuse one nickname glyph across consecutive reads of the
    # same *long* notice. Do not coalesce short ordinary messages by name.
    if x[0]!=y[0]:
        if min(len(left),len(right))<16 or SequenceMatcher(None,x[0],y[0]).ratio()<.84:
            return False
    # Never merge changing prices or numeric item stats as OCR jitter.
    if re.findall(r'[+-]?\d+(?:[.,]\d+)*(?:\s*(?:%|[kmb]\b))?',left)!=re.findall(r'[+-]?\d+(?:[.,]\d+)*(?:\s*(?:%|[kmb]\b))?',right):return False
    if min(len(left),len(right))<8:return False
    return SequenceMatcher(None,left,right).ratio()>=.91


def y(row):
    r=row.get('_tracking_rect') or row.get('rect') or (0,0,0,0)
    return float(r[1])+float(r[3])/2


def _slot_same(a, b):
    """OCR spelling drift, usable only after another row proves the scroll.

    The recording contains Hunnii/Hunnil and Iblade/lblade while the other
    rows remain stationary. This is not a global similar-name text filter.
    Prices, numeric linked stats, and buy/sell direction remain strict.
    """
    x,z=identity(a),identity(b)
    if not x[0] or not z[0]:return False
    if x[0]!=z[0] and (min(len(x[0]),len(z[0]))<4 or
            SequenceMatcher(None,x[0],z[0]).ratio()<.80):return False
    numbers=r'[+-]?\d+(?:[.,]\d+)*(?:\s*(?:%|[kmb]\b))?'
    if re.findall(numbers,x[1])!=re.findall(numbers,z[1]):return False
    directions=r'(?<!\w)[sbt]\s*>'
    if re.findall(directions,x[1])!=re.findall(directions,z[1]):return False
    # Decoration/spacing changes are common on the video's short party rows.
    # Keep letters, digits, brackets and relational signs in the comparison.
    compact=lambda text:re.sub(r'\s+','',text).rstrip('~!^_*\"\' .')
    left,right=compact(x[1]),compact(z[1])
    if left==right:return True
    return min(len(left),len(right))>=6 and SequenceMatcher(None,left,right).ratio()>=.87


class FrameMessageLedger:
    """Align whole visible rows; admit only message IDs not previously sent.

    Exact same words in multiple slots are separate events. An OCR dropout
    does not discard identities, and a megaphone-to-normal type flicker does
    not cause redelivery. No global text TTL blacklist.
    """
    def __init__(self, ghost_seconds=6.0):
        self.prev=[]
        self.ghosts=[]
        self.next_id=0
        self.delivered=set()
        self.ghost_seconds=float(ghost_seconds)
        self.suppressed=0

    def _new_id(self):
        self.next_id+=1
        return self.next_id

    @staticmethod
    def _align(old,new):
        """Ordered LCS, favor earliest current slots for existing messages."""
        n,m=len(old),len(new)
        def match(i,j):
            old_y=old[i]['y']
            new_y=y(new[j])
            # Existing Maple chat moves UP on new arrivals; a line moving
            # DOWN to the bottom is never the same physical message.
            # Permit a few pixels of OCR baseline jitter.
            height=(new[j].get('rect') or (0,0,0,15))[3]
            return (new_y <= old_y+max(4.,float(height)*.28)
                    and same(old[i]['row'],new[j]))
        dp=[[0]*(m+1) for _ in range(n+1)]
        for i in range(n-1,-1,-1):
            for j in range(m-1,-1,-1):
                dp[i][j]=(1+dp[i+1][j+1]) if match(i,j) else max(dp[i+1][j],dp[i][j+1])
        result={}
        i=j=0
        while i<n and j<m:
            if match(i,j) and dp[i][j]==1+dp[i+1][j+1]:
                result[j]=old[i]['id'];i+=1;j+=1
            elif dp[i+1][j]>dp[i][j+1]:
                i+=1
            else:
                j+=1
        return result

    def filter(self,admitted,visible,now):
        now=float(now)
        ordered=sorted(visible,key=lambda r:(y(r),float((r.get('rect') or (0,0,0,0))[0])))
        self.ghosts=[g for g in self.ghosts if now-g['at']<=self.ghost_seconds]
        if not ordered:return [] # transient blank OCR is not a new screen
        matches=self._align(self.prev,ordered)
        # Ordered matched neighbours establish the physical scroll offset.
        # Repeated party rows are valid anchors too when all displacements
        # agree; demanding unique text loses identities during OCR dropouts.
        # A repaired old row must still occupy its projected physical slot.
        prior={g['id']:g for g in self.prev}
        shifts=[]
        scroll_shift=None
        for ix,event in matches.items():
            g=prior[event]
            shifts.append(y(ordered[ix])-g['y'])
        if shifts:
            shift=sorted(shifts)[len(shifts)//2]
            if shift<=4 and all(abs(value-shift)<=4 for value in shifts):
                scroll_shift=shift
                used=set(matches.values())
                for ix,row in enumerate(ordered):
                    if ix in matches:continue
                    candidates=[g for g in self.prev if g['id'] not in used
                        and 0<=now-g['at']<=4
                        and abs(y(row)-(g['y']+shift))<=4
                        and _slot_same(g['row'],row)]
                    if len(candidates)!=1:continue
                    g=candidates[0]
                    # Never cross another matched physical row.
                    if any((other<ix and prior[event]['y']>=g['y']) or
                           (other>ix and prior[event]['y']<=g['y'])
                           for other,event in matches.items()):continue
                    matches[ix]=g['id'];used.add(g['id'])
        if scroll_shift is not None:
            # Missing rows scroll along with their surviving neighbours. A
            # ghost left at its old bottom position can otherwise steal the
            # ID of a genuinely repeated post that has just arrived there.
            self.ghosts=[{**g,'y':g['y']+scroll_shift} for g in self.ghosts]
        already=set(matches.values())
        fresh=[]
        for ix,row in enumerate(ordered):
            if ix not in matches:
                # Rescue a briefly invisible old line without muting a real
                # repeated post. Old line must have disappeared and reappeared
                # at essentially the SAME or a higher screen location.
                # Up to ~3 line heights of upward travel (65px at 768p chat;
                # a 1080p line is ~23px, so scale with the row height).
                reach=max(65.,3.2*float((row.get('rect') or (0,0,0,0))[3]))
                candidates=[g for g in self.ghosts if g['id'] not in already
                            and same(g['row'],row)
                            # Ghosts already moved with a proven scroll: same
                            # slot only. Without anchors, allow upward travel.
                            and (abs(g['y']-y(row))<=5 if scroll_shift is not None
                                 else -5 <= g['y']-y(row) <= reach)]
                if candidates:
                    g=min(candidates,key=lambda item:abs(item['y']-y(row)))
                    matches[ix]=g['id'];already.add(g['id'])
                else:
                    matches[ix]=self._new_id()
            fresh.append({'id':matches[ix],'row':row,'at':now,'y':y(row)})
        self.ghosts=[g for g in self.ghosts if g['id'] not in already]
        self.ghosts.extend({**g,'at':now,'y':g['y']+(scroll_shift or 0.)}
                           for g in self.prev if g['id'] not in matches.values())
        self.ghosts=self.ghosts[-96:]
        # Preserve an incomplete frame: one obscured or OCR-missed row must
        # not erase context and cause a full retranslation next time.
        self.prev=fresh
        for item in fresh:item['row']['_visual_event_id']=item['id']
        # The original dict objects are the admitted row objects (not copies).
        # Match by identity to avoid losing a pending OCR row on confirmation.
        accepted=[]
        seen_this_frame=set()
        for row in admitted:
            item=next((f for f in fresh if f['row'] is row),None)
            if item is None:
                item=next((f for f in fresh if id(f['row']) not in seen_this_frame and same(f['row'],row) and abs(f['y']-y(row))<9),None)
            if item is None:continue
            seen_this_frame.add(id(item['row']))
            if item['id'] in self.delivered:
                self.suppressed+=1
                continue
            self.delivered.add(item['id'])
            # Carry the *physical message event* through translation. Without
            # this, worker._record creates a brand-new ID on every OCR retry.
            row['_visual_event_id']=item['id']
            accepted.append(row)
        # Trim only IDs which are no longer held in the visual history.
        keep={g['id'] for g in self.prev+self.ghosts}
        if len(self.delivered)>1024:self.delivered.intersection_update(keep)
        return accepted
