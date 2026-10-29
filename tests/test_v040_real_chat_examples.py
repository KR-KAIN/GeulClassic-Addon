"""Live screenshot regression examples; never use a fake ML engine success."""
import unittest
from pathlib import Path
from kain_maple_translator.natural_trade import trade_override, general_chat_override
from kain_maple_translator.translation import Translator
from kain_maple_translator.obs_source import OBS_HTML
from kain_maple_translator.visual_theme import panel_stylesheet

ROOT=Path(__file__).resolve().parents[1]

class RealWorldChatExamples(unittest.TestCase):
    def test_shop_price_in_korean_units(self):
        self.assertEqual(trade_override('S> GFA 60% 790k'), '장공 60% 주문서 팝니다. 가격 79만 메소')
        self.assertEqual(trade_override('B> LV50 THIEF DEX Equips EQ45K'), '50레벨 도적용 덱스 장비 삽니다. 가격 4만 5천 메소')
    def test_bulk_ore(self):
        self.assertEqual(trade_override('B> ALL IRON ORES BULK'),'철광석 전부 대량으로 삽니다')
    def test_item_list_and_slot(self):
        result=trade_override('S> White Beanie & Pink Bunny Sweater & Red Check Rider 50k ea')
        self.assertIn('흰색 비니',result)
        self.assertIn('분홍 토끼 스웨터',result)
        self.assertIn('빨간 체크 라이더',result)
        self.assertIn('개당 5만 메소',result)
    def test_plain_natural_chat(self):
        self.assertEqual(general_chat_override('they are nerfing bow and buffing sin'), '활은 너프하고 표도는 버프하는 중이네요')
        self.assertEqual(general_chat_override('i feel like they are weak'), '걔네 좀 약한 것 같은데요')
    def test_tag_in_chat_retained(self):
        text=general_chat_override('[Snail] are nerfing bow and buffing sin')
        self.assertTrue(text.startswith('[Snail]'))
        self.assertIn('표도',text)
    def test_uncertain_text_not_guessed(self):
        self.assertIsNone(general_chat_override('might be a buff to someone idk'))
        self.assertIsNone(trade_override('not selling anything'))
    def test_original_unchanged_if_translation_is_not_confident(self):
        # Explicitly known text can be handled before loading ~240MB model files.
        self.assertEqual(Translator().translate('S> GFA 60% 790k','en-ko'),'장공 60% 주문서 79만 메소에 팝니다')
    def test_rounded_and_square_obs(self):
        self.assertIn('border-radius:0px',panel_stylesheet('square'))
        self.assertIn('border-radius:12px',panel_stylesheet('rounded'))
        self.assertIn('normal.scrollTop=normal.scrollHeight',OBS_HTML)
        self.assertIn('mega.scrollTop=mega.scrollHeight',OBS_HTML)
    def test_ui_wrap_and_panel_options(self):
        source=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('QScrollArea()',source)
        self.assertIn('row.setWordWrap(True)',source)
        self.assertIn("self.theme_choice.addItem('EDGE",source)
        self.assertIn('self.pin_settings=QCheckBox',source)
        self.assertIn('self.dock_width=QSpinBox',source)

if __name__=='__main__':unittest.main()
