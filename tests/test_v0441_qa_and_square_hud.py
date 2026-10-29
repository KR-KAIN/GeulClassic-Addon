"""v0.4.41: fixed replay stage and fused square-control HUD contract."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class UnchangedFrameReplay(unittest.TestCase):
    def test_replay_preserves_content_not_expired_cache_call_count(self):
        code=(ROOT/'scripts/replay_ocr_fixtures.py').read_text('utf-8')
        self.assertNotIn("engine.stats['recognition_batches']==0",code)
        self.assertIn('REAL UNCHANGED FRAME CONTENT STABILITY PASS',code)
        self.assertIn('REAL FOUR ROWS / NO REPEATED CONTENT PASS',code)
        self.assertIn('SYNTHETIC SCROLL / UNCHANGED CONTENT PASS',code)
        self.assertIn("r['nickname'],r['body'],r['tone']",code)

class SquareMapleHUD(unittest.TestCase):
    def test_both_windows_square_down_to_buttons_and_fields(self):
        code=(ROOT/'kain_maple_translator/main.py').read_text('utf-8')
        self.assertIn("class CompactSettings(Glass):",code)
        self.assertIn("class CompactComposer(Glass):",code)
        self.assertEqual(code.count("super().set_theme_variant('square' if getattr(self,'_hud_compact',False)"),2)
        self.assertEqual(code.count("self.set_theme_variant(getattr(self,'_requested_theme_variant',self.theme_variant))"),2)
        # R15 classic theme: edges come from strip_stylesheet, and square
        # mode makes buttons and fields square too.
        from kain_maple_translator.visual_theme import strip_stylesheet, panel_stylesheet
        self.assertIn('border-right:0px;',strip_stylesheet('left'))
        self.assertIn('border-left:0px;',strip_stylesheet('right'))
        self.assertIn('border-radius:0px;',strip_stylesheet('right'))
        controls=lambda qss:[l for l in qss.splitlines()
                             if l.startswith(('QPushButton','QLineEdit')) and 'border-radius' in l]
        self.assertTrue(controls(panel_stylesheet('square')))
        self.assertTrue(all('border-radius:0px' in l for l in controls(panel_stylesheet('square'))))
        self.assertTrue(all('border-radius:3px' in l for l in controls(panel_stylesheet('rounded'))))

if __name__=='__main__':unittest.main()
