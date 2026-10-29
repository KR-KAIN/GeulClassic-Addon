"""R6 safety regression: glyph dictionary never authoritatively reads ordinary chat."""
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from kain_maple_translator.fast_vision import IncrementalChatOCR, InkRow
from kain_maple_translator.glyph_features import separate_glyphs
from kain_maple_translator.glyph_dictionary import (GlyphDictionary, row_profile,
                                                     profile_key, profile_filename)


SHAPES = {
    '@': [".###.","#...#","#.###","#.#.#","#.###","#....",".####"],
    'a': [".....",".....",".###.","#...#","#####","#...#","#...#"],
    'b': ["#....","#....","####.","#...#","#...#","#...#","####."],
    ':': [".....","..##.","..##.",".....","..##.","..##.","....."],
    '[': [".###.",".#...",".#...",".#...",".#...",".#...",".###."],
    ']': [".###.","...#.","...#.","...#.","...#.","...#.",".###."],
}


def make_row(chars):
    h=17
    neutral=np.full((h, len(chars)*8+5,3),255,np.uint8)
    for i,char in enumerate(chars):
        pat=SHAPES[char]
        x=i*8+2
        for y,line in enumerate(pat):
            for dx,v in enumerate(line):
                if v=='#':neutral[y+5,x+dx]=0
    pieces=separate_glyphs(neutral)
    return InkRow((5,7,neutral.shape[1],h),neutral.copy(),neutral,b'row-'+chars.encode()) , pieces


class FakeReader:
    def __init__(self):self.calls=0
    def detect(self,*args):self.calls+=1;return []



class GlyphShadowUnittest(unittest.TestCase):
    """Runs under the Windows builder's stdlib unittest runner."""

    def setUp(self):
        sandbox = tempfile.TemporaryDirectory(prefix="gca-r6-test-")
        self.addCleanup(sandbox.cleanup)
        self.tmp_path = Path(sandbox.name)

    def test_same_glyph_three_votes_and_at_only_lookup(self):
        db=GlyphDictionary(self.tmp_path)
        row,pieces=make_row('@@@')
        assert len(pieces)==3
        profile=row_profile(row,'1920x1080','1.25')
        for n in range(1,4):
            assert db.compare_and_train(profile,pieces,'@@@',.96)
            assert db.resolved_at_only(profile,pieces) == (n>=3)
        assert db.stats(profile)['glyph_dict_size']==1
        assert (self.tmp_path/profile_filename(profile)).exists()


    def test_opposing_vote_deletes_confirmed_and_requires_retraining(self):
        db=GlyphDictionary(self.tmp_path)
        profile=profile_key('1920x1080','1.0',20,'abc')
        for i in range(3): db.observe_vote(profile,'identical-hash','@')
        assert db.lookup(profile,'identical-hash')=='@'
        db.observe_vote(profile,'identical-hash','a')
        assert db.lookup(profile,'identical-hash') is None
        for i in range(2): db.observe_vote(profile,'identical-hash','a')
        assert db.lookup(profile,'identical-hash')=='a'


    def test_profile_isolation_persisted(self):
        a=profile_key('1920x1080','1.0',20,'fff')
        b=profile_key('1600x900','1.0',20,'fff')
        db=GlyphDictionary(self.tmp_path)
        for i in range(3):db.observe_vote(a,'hash','@')
        assert db.lookup(a,'hash')=='@'
        assert db.lookup(b,'hash') is None
        reloaded=GlyphDictionary(self.tmp_path)
        assert reloaded.lookup(a,'hash')=='@'
        assert reloaded.lookup(b,'hash') is None


    def test_unknown_glyph_falls_back_to_old_ocr(self):
        db=GlyphDictionary(self.tmp_path)
        row,pieces=make_row('@@a')
        profile=row_profile(row,'1920x1080','1.0')
        for i in range(3):db.observe_vote(profile,pieces[0][0],'@')
        assert not db.resolved_at_only(profile,pieces)
        reader=FakeReader()
        engine=IncrementalChatOCR(reader)
        engine.glyph_dictionary=db;engine.glyph_dictionary_enabled=True
        engine.glyph_resolution='1920x1080';engine.glyph_dpi='1.0'
        with patch('kain_maple_translator.fast_vision.ink_rows',return_value=([row],False)), \
             patch.object(engine,'_read_rows',return_value=[('@@a',.8)]) as ocr:
            engine.detect(np.zeros((100,300,3),np.uint8),0,0)
            assert ocr.call_count==1
            assert engine.stats['glyph_lines_fallback']==1
            assert engine.stats['glyph_at_only_skipped']==0


    def test_only_at_line_skipped_without_any_ocr(self):
        db=GlyphDictionary(self.tmp_path)
        row,pieces=make_row('@@@@')
        profile=row_profile(row,'1920x1080','1.0')
        for i in range(3):db.compare_and_train(profile,pieces,'@@@@',.97)
        reader=FakeReader()
        engine=IncrementalChatOCR(reader)
        engine.glyph_dictionary=db;engine.glyph_dictionary_enabled=True
        engine.glyph_resolution='1920x1080';engine.glyph_dpi='1.0'
        with patch('kain_maple_translator.fast_vision.ink_rows',return_value=([row],False)), \
             patch.object(engine,'_read_rows',side_effect=AssertionError('OCR must not run')):
            lines=engine.detect(np.zeros((100,300,3),np.uint8),0,0)
        assert lines==[]
        assert reader.calls==0
        assert engine.stats['glyph_at_only_skipped']==1
        assert engine.stats['glyph_lines_resolved']==1
        assert engine.stats['detector_recoveries']==0


    def test_nickname_and_item_excluded_from_shadow_and_training(self):
        db=GlyphDictionary(self.tmp_path)
        row,pieces=make_row('a:b[a]')
        profile=row_profile(row,'1920x1080','1.0')
        assert len(pieces)==len('a:b[a]')
        db.compare_and_train(profile,pieces,'a:b[a]',.98)
        db.compare_and_train(profile,pieces,'a:b[a]',.98)
        db.compare_and_train(profile,pieces,'a:b[a]',.98)
        assert db.lookup(profile,pieces[0][0]) is None  # nickname never taught
        assert db.lookup(profile,pieces[2][0])=='b'  # ordinary body is shadow-only
        assert db.lookup(profile,pieces[3][0]) is None  # bracket excluded
        assert db.lookup(profile,pieces[5][0]) is None
        body,pieces=make_row('a:bbb')
        profile=row_profile(body,'1920x1080','1.0')
        for _ in range(3):db.compare_and_train(profile,pieces,'a:bbb',.98)
        assert db.lookup(profile,pieces[0][0]) is None  # nickname
        assert db.lookup(profile,pieces[1][0]) is None  # colon
        assert db.lookup(profile,pieces[2][0])=='b' # body-only learning


    def test_shadow_mismatch_logs_but_does_not_output_dictionary_text(self):
        db=GlyphDictionary(self.tmp_path)
        row,pieces=make_row('a:b')
        profile=row_profile(row,'1920x1080','1.0')
        db.observe_vote(profile,pieces[-1][0],'a')
        db.observe_vote(profile,pieces[-1][0],'a')
        db.observe_vote(profile,pieces[-1][0],'a')
        db.compare_and_train(profile,pieces,'a:b',.94)
        stats=db.stats(profile)
        assert stats['glyph_shadow_compared']==1
        assert stats['glyph_shadow_mismatch']==1
        assert stats['glyph_shadow_pairs'][0]=={'dictionary':'a','ocr':'b','count':1}
        assert db.lookup(profile,pieces[-1][0]) is None  # conflict removes entry


    def test_without_colon_no_nickname_is_learned(self):
        db=GlyphDictionary(self.tmp_path)
        row,pieces=make_row('aaa')
        profile=row_profile(row,'1920x1080','1.0')
        for _ in range(5):db.compare_and_train(profile,pieces,'aaa',.99)
        assert db.lookup(profile,pieces[0][0]) is None
        assert db.stats(profile)['glyph_shadow_compared']==0


    def test_default_off_no_dictionary_io_and_normal_ocr(self):
        reader=FakeReader()
        engine=IncrementalChatOCR(reader)
        engine.glyph_dictionary=GlyphDictionary(self.tmp_path)
        assert engine.glyph_dictionary_enabled is False
        row,_=make_row('@@@')
        with patch('kain_maple_translator.fast_vision.ink_rows',return_value=([row],False)), \
             patch.object(engine,'_read_rows',return_value=[('@@@',.95)]) as ocr:
            engine.detect(np.zeros((100,300,3),np.uint8),0,0)
            assert ocr.call_count==1
        assert not list(self.tmp_path.glob('glyph-*.json'))
        assert engine.stats['glyph_at_only_skipped']==0


    def test_reset_only_own_dictionary_files(self):
        db=GlyphDictionary(self.tmp_path)
        p=profile_key('x','1',14,'fff')
        for _ in range(3):db.observe_vote(p,'key','@')
        other=self.tmp_path/'keep.txt';other.write_text('keep')
        db.clear_all()
        assert db.lookup(p,'key') is None
        assert other.read_text()=='keep'
        assert not list(self.tmp_path.glob('glyph-*.json'))
