"""v0.4.0 regressions: natural trade, content-height layout, commercial themes."""
from __future__ import annotations
import tempfile
import json
import unittest
from pathlib import Path
from urllib.request import urlopen
from kain_maple_translator.visual_theme import normalize_variant, radius_px,panel_stylesheet
from kain_maple_translator.chat_render import soft_break_long_tokens
from kain_maple_translator.natural_trade import trade_override, general_chat_override
from kain_maple_translator.translation import Translator
from kain_maple_translator.core import load_config,save_config
from kain_maple_translator.obs_source import OBSChatSource,OBS_HTML

ROOT=Path(__file__).resolve().parents[1]
class ModernUIAndTranslationTests(unittest.TestCase):
    def test_trade_full_context(self):
        self.assertEqual(trade_override('S> Cromi +1 C/O 1.8m A/W 2.6m'),
                         '크로미 +1 팝니다. 현재 최고 제시가 180만 메소, 즉시 구매가 260만 메소')
        self.assertEqual(trade_override('S> INV SLOTS 40k ea 2 available pmo'),
                         '인벤토리 슬롯 팝니다. 개당 4만 메소, 재고 2개. 귓말 주세요')
        self.assertEqual(trade_override('S> Orange Hooded Vest highest wins'),
                         '오렌지 후드 조끼 팝니다. 가격 제안 받습니다')
        self.assertEqual(trade_override('B> IRON ORES bulk'),
                         '철광석 대량으로 삽니다')
    def test_fallback_preserves_uncertainty(self):
        self.assertIsNone(trade_override('C/O 5m'))
        self.assertIsNone(trade_override('Some player said 3m'))
        self.assertIsNone(general_chat_override('They are nerfing that other class maybe'))
        self.assertEqual(general_chat_override('bow got nerfed'),'활이 너프됐어요')
    def test_full_translation_without_model_known_trades(self):
        self.assertEqual(Translator().translate('S> Cromi +1 C/O 1.8m A/W 2.6m','en-ko'),
            '크로미 +1 팝니다. 현재 최고 제시가 180만 메소, 즉시 구매가 260만 메소')
    def test_unbroken_item_names_wrap_without_text_loss(self):
        message='X'*63+' 커닝 파퀘'
        visual=soft_break_long_tokens(message)
        self.assertIn('\u200b', visual)
        self.assertEqual(visual.replace('\u200b',''),message)
        self.assertNotIn('\u200b',soft_break_long_tokens('Cromi +1'))

    def test_theme_variants_stay_bounded(self):
        self.assertEqual(normalize_variant('rounded'),'rounded')
        self.assertEqual(normalize_variant('square'),'square')
        self.assertEqual(normalize_variant('oops'),'rounded')
        self.assertEqual(radius_px('square'),0)
        self.assertGreater(radius_px('rounded'),0)
        self.assertIn('border-radius:0px',panel_stylesheet('square'))
        self.assertIn('border-radius:12px',panel_stylesheet('rounded'))
    def test_theme_saved_and_obs(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'conf.json';c=load_config(file)
            c['theme_variant']='square'; save_config(c,file)
            self.assertEqual(load_config(file)['theme_variant'],'square')
        obs=OBSChatSource(port=0)
        try:
            url=obs.start()
            obs.set_state([('Nick','긴 한국어 채팅')],theme_variant='square')
            with urlopen(url+'state',timeout=3) as r:
                self.assertEqual(json.loads(r.read().decode())['theme_variant'],'square')
            self.assertIn("state.theme_variant==='square'",OBS_HTML)
            self.assertIn('normal.scrollTop=normal.scrollHeight',OBS_HTML)
            self.assertIn('mega.scrollTop=mega.scrollHeight',OBS_HTML)
            self.assertIn('overflow-y:auto',OBS_HTML)
        finally: obs.close()
    def test_qt_wrap_without_hardcoded_line_height(self):
        source=(ROOT/'kain_maple_translator/main.py').read_text(encoding='utf-8')
        self.assertIn('self.feed = QScrollArea()',source)
        self.assertIn('row.setWordWrap(True)',source)
        self.assertIn('QSizePolicy.Policy.Preferred',source)
        self.assertIn('row.setMinimumWidth(0)',source)
        self.assertIn('rows.addWidget(widget)',source)
        self.assertIn('self._live_rows.append((widget,rows))',source)
        self.assertIn('self.splitter = QSplitter',source)
        self.assertIn('theme_choice.addItem',source)
        self.assertIn('QTabWidget(self)',source)
        self.assertIn("make_tab('채팅 디자인')",source)
        self.assertIn("controller.chat.setWindowOpacity(1.0)",source)

if __name__=='__main__':unittest.main()
