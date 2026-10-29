"""v0.4.5 regression: no repeated repaint/flash and Korean meso precision."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kain_maple_translator.obs_source import OBSChatSource,OBS_HTML
from kain_maple_translator.natural_trade import polish_meso_units
from kain_maple_translator.translation import Translator
from kain_maple_translator.layout import hud_panel_geometry

class FlickerAndHud(unittest.TestCase):
    def test_qt_increments_rows_instead_of_full_repaint(self):
        src=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf8')
        section=src.split('    def put(self, message: dict):',1)[1].split('    def set_mode(',1)[0]
        self.assertIn('self._live_rows.append((widget,rows))',section)
        self.assertNotIn('self._render_messages()',section)
        self.assertIn('self._schedule_latest()',section)

    def test_window_stacking_does_not_reorder_on_every_poll(self):
        src=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf8')
        self.assertIn('state_changed =',src)
        self.assertIn('state_changed or not is_topmost',src)
        self.assertIn('self._last_foreground_context=context',src)

    def test_process_anchor_survives_transient_lookup_gap(self):
        src=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf8')
        self.assertIn('now-self._last_valid_game_at < 1.25',src)
        self.assertIn('if now-self._game_probe_at < 0.45:',src)

    def test_obs_updates_dom_without_removing_existing_rows(self):
        self.assertIn('dataset.messageId',OBS_HTML)
        self.assertIn('existing = new Map()',OBS_HTML)
        self.assertNotIn('normal.replaceChildren()',OBS_HTML)
        self.assertNotIn('mega.replaceChildren()',OBS_HTML)

    def test_obs_messages_stable_identity_and_order(self):
        server=OBSChatSource(port=0)
        try:
            url=server.start()
            messages=[{'id':17,'nickname':'Foo','translated':'안녕하세요','kind':'super','prefix':'[고확]','band_color':'#dd6688'},
                      {'id':18,'nickname':'Bar','translated':'메소','kind':'normal','prefix':'','band_color':''}]
            server.set_state(messages, split_ratio_general=70, megaphone_opacity=92)
            with urlopen(url+'state',timeout=4) as req:
                data=json.loads(req.read().decode('utf-8'))
            self.assertEqual([m['id'] for m in data['messages']],[17,18])
            self.assertEqual(data['messages'][0]['band_color'],'#dd6688')
            self.assertIn('id="mega-lines"', OBS_HTML.split('id="normal-lines"')[0])
        finally:
            server.close()

    def test_controls_use_independently_compact_bottom_aligned_heights(self):
        l,r=hud_panel_geometry((0,0,1366,768),(0,0,1366,768),None)
        self.assertEqual(l[1]+l[3],r[1]+r[3])
        self.assertEqual((l[3],r[3]),(126,126))

    def test_meso_units_and_commas_are_not_corrupted(self):
        for source,expected in [
            ('1,000만 메소','1,000만 메소'),
            ('130 천 mesos','13만 메소'),
            ('1.8 백만 mesos','180만 메소'),
            ('900k mesos','90만 메소'),
            ('140 천 메소','14만 메소'),
        ]:
            with self.subTest(source=source):
                self.assertEqual(polish_meso_units(source),expected)
        self.assertEqual(Translator().translate('a/w 10m','en-ko'),'즉시 구매가 1,000만 메소')

    def test_font_family_on_both_chat_spans(self):
        src=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf8')
        self.assertIn("nickname_style='megaphone_nickname' if is_announcement else 'nickname'", src)
        self.assertIn("message_style='megaphone_message' if is_announcement else 'message'", src)
        self.assertIn('font_css}{nick_css}', src)
        self.assertIn('font_css}{body_css}', src)

if __name__=='__main__':unittest.main()
