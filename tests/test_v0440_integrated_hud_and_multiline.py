"""v0.4.40: seamless Maple HUD and wrapped OCR megaphone retention."""
import unittest
from pathlib import Path
from kain_maple_translator.layout import hud_panel_geometry
from kain_maple_translator.core import merge_chat_ocr,ChatFrameTracker
from kain_maple_translator.vision import Line

ROOT=Path(__file__).resolve().parents[1]

class IntegratedHUD(unittest.TestCase):
    def test_no_blank_horizontal_gutters_on_full_client(self):
        for w,h in [(1366,768),(1600,900),(1920,1080)]:
            with self.subTest(size=(w,h)):
                left,right=hud_panel_geometry((0,0,w,h),(0,0,w,h),None)
                self.assertEqual(left[0],0)
                self.assertEqual(right[0]+right[2],w)
                self.assertEqual(left[1],right[1])
                self.assertEqual(left[3],right[3])
                self.assertGreater(left[2],155)
                self.assertGreater(right[2],155)
    def test_no_round_corner_or_side_inset_in_hud_mode(self):
        code=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf8')
        # R15 classic theme: the HUD bars use the stat window's bottom strip.
        from kain_maple_translator.visual_theme import strip_stylesheet
        self.assertIn("strip_stylesheet('left')",code)
        self.assertIn("strip_stylesheet('right')",code)
        self.assertIn('border-right:0px;',strip_stylesheet('left'))
        self.assertIn('border-left:0px;',strip_stylesheet('right'))
        self.assertIn('border-radius:0px;',strip_stylesheet('left'))
        self.assertNotIn('if compact: height=min(height,88)',code)
    def test_wrapped_line_tolerates_padded_box_overlap(self):
        first=Line('GhostOfBlyat : ALL YOU LVL 20-29 NOOBS, PLAY KPQ, NOT TAKE SPACE A',.98,(0,0,742,23),ink_key='a')
        second=Line('T FARMING',.94,(30,22,119,23),ink_key='b')
        got=merge_chat_ocr([first,second])
        self.assertEqual(len(got),1)
        self.assertIn('FARMING',got[0]['body'])
    def test_scroll_movement_does_not_reemit_prior_message(self):
        tracker=ChatFrameTracker()
        r=lambda t: {'nickname':'Foo','body':t}
        self.assertEqual(len(tracker.new([r('first'),r('second')])),2)
        self.assertEqual(tracker.new([r('second')]),[])
        self.assertEqual([x['body'] for x in tracker.new([r('second'),r('third')])],['third'])

if __name__=='__main__':unittest.main()
