"""Opt-in character bitmap dictionary: ONLY all-@ rows can bypass OCR.

For all ordinary body text the dictionary is shadow-only. Nickname prefixes and
[item links] never become dictionary-controlled text or shadow training data.
"""
from __future__ import annotations
from collections import Counter, OrderedDict
import hashlib
import json
import os
from pathlib import Path
import re

from .core import config_path
from .glyph_features import separate_glyphs, dominant_ink_color


STORE_DIR = config_path().parent / 'glyph-dictionaries'


def profile_key(resolution, dpi, row_height, color):
    return (str(resolution or 'unknown'), str(dpi if dpi is not None else 'unknown'),
            int(row_height), str(color or 'unknown'))


def profile_filename(profile):
    return 'glyph-' + hashlib.blake2b(json.dumps(profile,ensure_ascii=True).encode('utf-8'),
                                     digest_size=12).hexdigest()+'.json'


def _eligible_indices(text):
    """Only body characters can train/compare; protect nickname and links."""
    protected=set()
    colon=re.search(r'[:：]',text)
    if not colon:
        # Without a validated name/body separator, we cannot determine where
        # the nickname ends. Only OCR-verified @-only lines can be learned.
        return list(range(len(text))) if re.fullmatch(r'@+',text) else []
    protected.update(range(colon.end()))
    # Include unclosed links: never learn what might be a corrupted item link.
    inside=False
    for pos,ch in enumerate(text):
        if ch=='[': inside=True
        if inside: protected.add(pos)
        if ch==']': inside=False
    return [i for i,ch in enumerate(text) if i not in protected and not ch.isspace()]


class GlyphDictionary:
    def __init__(self, folder=None, max_items=4096):
        self.folder=Path(folder) if folder is not None else STORE_DIR
        self.max_items=int(max_items)
        self._loaded=OrderedDict()
        self._conflicts=Counter()
        self.shadow_compared=0
        self.shadow_mismatch=0
        self.shadow_pairs=Counter()

    def _open(self, profile):
        k=profile_key(*profile)
        if k in self._loaded:
            self._loaded.move_to_end(k)
            return self._loaded[k]
        path=self.folder/profile_filename(k)
        data={}
        if path.is_file():
            try:
                raw=json.loads(path.read_text('utf-8'))
                if raw.get('profile')==list(k) and isinstance(raw.get('items'),dict):
                    data=raw['items']
            except (ValueError,OSError,TypeError):
                data={}
        self._loaded[k]=data
        while len(self._loaded)>24:
            self._loaded.popitem(last=False)
        return data

    def _save(self, profile):
        k=profile_key(*profile)
        data=self._open(k)
        self.folder.mkdir(parents=True,exist_ok=True)
        path=self.folder/profile_filename(k)
        content=json.dumps({'schema':1,'profile':list(k),'items':data},ensure_ascii=False)
        temp=path.with_name(path.stem+f'.{os.getpid()}.tmp')
        temp.write_text(content,'utf-8')
        temp.replace(path)

    def lookup(self, profile, key):
        entry=self._open(profile).get(key)
        return entry['char'] if entry and entry.get('char') and entry.get('votes',0)>=3 else None

    def observe_vote(self, profile, key, char):
        if len(char)!=1 or char.isspace():return False
        entries=self._open(profile)
        entry=entries.get(key)
        if entry is None:
            entries[key]={'char':char,'votes':1}
        elif entry['char']==char:
            entry['votes']=min(9999,int(entry.get('votes',0))+1)
        else:
            # One disagreement invalidates a previously registered hash.
            # Start completely fresh; never use the old accepted character.
            self._conflicts[(profile_key(*profile),key)]+=1
            entries[key]={'char':char,'votes':1}
        while len(entries)>self.max_items:
            entries.pop(next(iter(entries)))
        self._save(profile)
        return self.lookup(profile,key)==char

    def resolved_at_only(self, profile, pieces):
        """Only a complete @@@... bitmap may bypass the existing OCR path."""
        return bool(pieces) and all(self.lookup(profile,key)=='@' for key,_ in pieces)

    def compare_and_train(self, profile, pieces, recognized, confidence):
        """Never alters recognized: only log shadow disagreement and high-confidence votes."""
        text=str(recognized or '')
        if not pieces or len(pieces)!=len(text):return False
        allowed=_eligible_indices(text)
        for i in allowed:
            found=self.lookup(profile,pieces[i][0])
            if found:
                self.shadow_compared+=1
                if found != text[i]:
                    self.shadow_mismatch+=1
                    self.shadow_pairs[(found,text[i])]+=1
        if float(confidence)>=.9:
            # A row of @@@@ is ONE independent observation, not four votes.
            # Do not treat the same OCR result as multiple confirmations.
            unique={}
            ambiguous=set()
            for i in allowed:
                key=pieces[i][0]
                char=text[i]
                if key in unique and unique[key]!=char:
                    ambiguous.add(key)
                else:
                    unique[key]=char
            for key,char in unique.items():
                if key not in ambiguous:
                    self.observe_vote(profile,key,char)
        return True

    def stats(self, profile=None):
        entries=self._open(profile) if profile else {}
        pairs=sorted(self.shadow_pairs.items(),key=lambda x:(-x[1],x[0]))[:10]
        return {'glyph_shadow_compared':self.shadow_compared,
                'glyph_shadow_mismatch':self.shadow_mismatch,
                'glyph_shadow_pairs':[{'dictionary':a,'ocr':b,'count':count} for (a,b),count in pairs],
                'glyph_shadow_mismatch_rate':round(self.shadow_mismatch/max(1,self.shadow_compared),4),
                'glyph_dict_size':sum(v.get('votes',0)>=3 for v in entries.values())}

    def clear_all(self):
        """Only own dictionary JSON files are affected; never touch OCR resources."""
        self._loaded.clear()
        if self.folder.is_dir():
            for path in self.folder.glob('glyph-*.json'):
                path.unlink()


def row_profile(row, resolution, dpi):
    return profile_key(resolution,dpi,row.neutral.shape[0],
                       dominant_ink_color(row.original,row.neutral))
