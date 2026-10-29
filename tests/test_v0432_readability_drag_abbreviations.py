"""v0.4.32: real trade abbreviations, customized colors and pointer scroll contract."""
import unittest
from pathlib import Path
from kain_maple_translator.chat_style import effective_font_color, DEFAULT_STYLE
from kain_maple_translator.natural_trade import split_market_location
from kain_maple_translator.translation import Translator


class MarketShorthandV0432(unittest.TestCase):
    def setUp(self):
        self.engine=Translator()
    def test_channel_first(self):
        self.assertEqual(split_market_location('S> SP resets 60k ch31 FM17'),
                         ('S> SP resets 60k','31채널 자유시장 17번 방'))
    def test_room_first(self):
        self.assertEqual(split_market_location('S> WG 220k FM17 ch31'),
                         ('S> WG 220k','31채널 자유시장 17번 방'))
    def test_location_only(self):
        self.assertEqual(self.engine.translate('ch31 FM17','en-ko'),'31채널 자유시장 17번 방')
    def test_sp_reset_sale(self):
        self.assertEqual(self.engine.translate('S> SP resets 60k ch31 FM17','en-ko'),
                         'SP 초기화권 팝니다. 가격 6만 메소 (31채널 자유시장 17번 방)')
    def test_channel_location_preserves_old_style(self):
        self.assertEqual(self.engine.translate('S> 60% scroll 2m @ FM4 CH9','en-ko'),
                         '60% 주문서 200만 메소에 팝니다 (9채널 자유시장 4번 방)')
    def test_not_partial_token(self):
        self.assertIsNone(split_market_location('support_ch31 FM17'))
    def test_invalid_zero(self):
        self.assertIsNone(split_market_location('S> WG ch0 FM17'))

class FontAndDragV0432(unittest.TestCase):
    def test_normal_source_black_ignored(self):
        self.assertEqual(effective_font_color(DEFAULT_STYLE,'message',True,'#020202'),'#ffffff')
        self.assertEqual(effective_font_color(DEFAULT_STYLE,'nickname',True,'#030303'),'#b5d6ff')
    def test_custom_style_overrides_source_even_when_enabled(self):
        custom={**DEFAULT_STYLE,'megaphone_message_color':'#abcdef','megaphone_nickname_color':'#fedcba',
                'message_color':'#efff00'}
        self.assertEqual(effective_font_color(custom,'megaphone_message',True,'#112233'),'#abcdef')
        self.assertEqual(effective_font_color(custom,'megaphone_nickname',True,'#334455'),'#fedcba')
        self.assertEqual(effective_font_color(custom,'message',True,'#000000'),'#efff00')
    def test_default_megaphone_original_color_kept(self):
        self.assertEqual(effective_font_color(DEFAULT_STYLE,'megaphone_message',True,'#991122'),'#991122')
    def test_overlay_scroll_does_not_block_game_until_enabled(self):
        root=Path(__file__).parents[1]
        code=(root/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn("passthrough = (not self.editing and not self.scroll_interactive",code)
        self.assertIn("kind == QEvent.Type.MouseButtonPress and can_drag",code)
        self.assertIn("start_scroll - (event.position().y() - start_y)",code)
        self.assertIn("self._auto_follow[feed] = (bar.value() >= bar.maximum() - 2)",code)
    def test_obs_uses_customized_and_safe_normal_colors(self):
        root=Path(__file__).parents[1]
        obs=(root/'kain_maple_translator/obs_source.py').read_text(encoding='utf-8')
        self.assertIn("selectedNick.toLowerCase()==='#fff38a'",obs)
        self.assertIn("selectedBody.toLowerCase()==='#ffffff'",obs)
        self.assertIn("?entry.text_color:selectedBody",obs)

if __name__=='__main__':unittest.main()
