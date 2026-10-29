"""Offline regression tests for the actual bottom-chat-only UI contract."""
from dataclasses import dataclass
from pathlib import Path
import unittest
from kain_maple_translator.core import (
    ChatFrameTracker, merge_chat_ocr, parse_chat_line, load_config,
)


@dataclass
class OCRBox:
    text: str
    rect: tuple[int,int,int,int]
    confidence: float = .92


def msg(who, what):
    return {'nickname':who, 'body':what}


class BottomChatOnlyTests(unittest.TestCase):
    def test_nickname_colon_message_only(self):
        self.assertEqual(parse_chat_line('UncleStatus : cleric was my main'), ('UncleStatus','cleric was my main'))
        self.assertEqual(parse_chat_line('iLuvMyRabbit : Silly head :P'), ('iLuvMyRabbit','Silly head :P'))
        self.assertEqual(parse_chat_line('CH17'), None)
        self.assertEqual(parse_chat_line('13:25:14 UncleStatus : hello'), ('UncleStatus','hello'))
        self.assertEqual(parse_chat_line('MemoryShadow ✿ : S>kumbi 380k'), ('MemoryShadow','S>kumbi 380k'))

    def test_split_ocr_nick_message_are_reassembled(self):
        result = merge_chat_ocr([
            OCRBox('cleric was my main',(425,630,174,17)),
            OCRBox('UncleStatus :',(285,630,138,17)),
            OCRBox('Italian : ayo?',(285,651,135,17)),
            OCRBox('Level 12',(280,685,60,15)),
        ])
        self.assertEqual([(r['nickname'], r['body']) for r in result],
                         [('UncleStatus','cleric was my main'),('Italian','ayo?')])

    def test_changed_lines_do_not_reappear(self):
        frames=ChatFrameTracker()
        self.assertEqual(frames.new([msg('A','hello'),msg('B','PQ')]),
                         [msg('A','hello'),msg('B','PQ')])
        self.assertEqual(frames.new([msg('A','hello'),msg('B','PQ')]), [])
        self.assertEqual(frames.new([msg('B','PQ')]), [])
        self.assertEqual([(x['nickname'],x['body']) for x in frames.new([msg('B','PQ'),msg('C','cc plz')])], [('C','cc plz')])
        self.assertEqual([(x['nickname'],x['body']) for x in frames.new([msg('B','PQ'),msg('C','cc plz'),msg('C','cc plz')])], [('C','cc plz')])

    def test_legacy_three_zone_saved_setting_is_not_scanned(self):
        source=Path(__file__).resolve().parents[1]
        main=(source/'kain_maple_translator'/'main.py').read_text(encoding='utf-8')
        worker=(source/'kain_maple_translator'/'worker.py').read_text(encoding='utf-8')
        self.assertIn("'enabled']={'bubble':False,'chat':True,'trade':False}", main)
        self.assertIn('targets = ["chat"]', worker)
        self.assertNotIn('for zone in ZONES',worker)
        chat_class=main.split('class FloatingChat',1)[1].split('class CompactSettings',1)[0]
        self.assertNotIn('QTabWidget',chat_class)  # settings dialog may have tabs
        self.assertIn('self._render_messages()',main)
        self.assertIn('self.feed = QScrollArea()',main)
        self.assertIn('row.setWordWrap(True)',main)
        self.assertIn('html.escape',main)


if __name__ == '__main__':
    unittest.main()
