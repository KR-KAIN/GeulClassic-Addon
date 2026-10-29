"""Build, licensing and user-scrollback regression without Qt installation."""
from pathlib import Path
import tempfile
import unittest
from scripts.compare_authorized_item_names import compare

ROOT=Path(__file__).resolve().parents[1]

class WheelAndBuilderTests(unittest.TestCase):
    def test_scroll_area_accepts_mouse_input_and_hides_scrollbar(self):
        s=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('scroll.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,False)',s)
        self.assertIn('scroll.viewport().installEventFilter(self)',s)
        self.assertIn('content.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)',s)
        self.assertIn('Qt.ScrollBarPolicy.ScrollBarAlwaysOff',s)

    def test_user_wheel_disables_following_until_bottom(self):
        s=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('event.type() == QEvent.Type.Wheel',s)
        self.assertIn('self._auto_follow[feed] = (bar.value() >= bar.maximum() - 2)',s)
        self.assertIn('if self._auto_follow.get(feed, True):',s)
        self.assertIn('for feed in (self.general_feed,self.mega_feed):',s)

    def test_scroll_button_exposes_input_mode(self):
        s=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn("Button('휠 OFF')",s)
        self.assertIn('self.left.scroll_mode_changed.connect(self.toggle_scroll_mode)',s)
        self.assertIn('not self.scroll_interactive',s)
        self.assertIn('self.chat.set_scroll_interactive(enabled)',s)

    def test_venv_is_outside_deep_downloads_folder_and_essentials(self):
        ps=(ROOT/'scripts/BUILD-WINDOWS.ps1').read_text(encoding='utf-8-sig')
        bat=(ROOT/'START-SOURCE.bat').read_text(encoding='ascii')
        req=(ROOT/'requirements.txt').read_text(encoding='utf-8')
        self.assertIn("Join-Path $env:LOCALAPPDATA 'KAINMapleTranslator\\BuildVenv0418'",ps)
        self.assertIn('%LOCALAPPDATA%\\KAINMapleTranslator\\BuildVenv0418',bat)
        self.assertIn('PySide6-Essentials>=',req)
        self.assertNotIn('PySide6>=',req)

    def test_id_join_excludes_ambiguous_english_names(self):
        english=[{'item_id':'1','name_en':'Same Sword'}, {'item_id':'2','name_en':'Same Sword'}, {'item_id':'3','name_en':'Potion'}, {'item_id':'4','name_en':'Food'}]
        korean=[{'id':1,'name_ko':'검'},{'id':2,'name_ko':'칼'},{'id':3,'name_ko':'물약'},{'id':4,'name_ko':'빵'}, {'id':4,'name_ko':'떡'}]
        result=compare(english,korean)
        self.assertEqual(result['matched_ids'],3)
        self.assertEqual(result['conflicting_korean_ids'],1)
        self.assertEqual(result['ambiguous_english_ids'],2)
        self.assertEqual(result['unambiguous_for_text_replacement'],1)
        self.assertEqual(result['safe_for_glossary'][0]['name_ko'],'물약')

    def test_no_unauthorized_web_scrapers_added(self):
        s=(ROOT/'scripts/compare_authorized_item_names.py').read_text(encoding='utf-8')
        self.assertNotIn('urllib.request',s)
        self.assertNotIn('requests.get(',s)

if __name__=='__main__': unittest.main()
