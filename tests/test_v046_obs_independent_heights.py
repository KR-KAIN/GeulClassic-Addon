"""v0.4.6 independent OBS Interaction pane heights & conservative market translation."""
import unittest
from kain_maple_translator.obs_source import OBS_HTML, OBSChatSource
from kain_maple_translator.natural_trade import priced_item_list,trade_override
from kain_maple_translator.translation import Translator

class OBSLayoutRegression(unittest.TestCase):
 def test_draggable_grips_for_both_categories(self):
  for token in ('id="mega-shell"','id="normal-shell"','id="split-handle"',
                'id="normal-resize-handle"','setPointerCapture','pointermove','dblclick'):
   self.assertIn(token,OBS_HTML)
 def test_obs_ratios_are_local_not_app_state(self):
  for token in ('kain_maple_obs_panes_v046','localStorage.setItem',
                'let obsHeights=null','defaultMega=(100-ratio)/100',
                'const usable=Math.max(1', 'OBS 상호작용'):
   self.assertIn(token,OBS_HTML)
  self.assertNotIn("fetch('/set-state'",OBS_HTML)
 def test_obs_source_keeps_application_ratio(self):
  server=OBSChatSource(port=0)
  server.set_state([],split_ratio_general=65)
  self.assertEqual(server.state()['split_ratio_general'],65)
 def test_known_listings_not_half_english(self):
  result=priced_item_list('S> Michael Wings 155k, Frameless Glasses 111k')
  self.assertEqual(result,'마이클 날개 15만 5천 메소, 무테 안경 11만 1천 메소 팝니다')
  self.assertEqual(Translator().translate('S> Michael Wings 155k, Frameless Glasses 111k','en-ko'),result)
 def test_unknown_suffix_not_hallucinated(self):
  self.assertIsNone(priced_item_list('S> some sword 100k, maybe tonight'))
  self.assertEqual(trade_override('S> Cromi +1 C/O 1.8m A/W 2.6m'),
                   '크로미 +1 팝니다. 현재 최고 제시가 180만 메소, 즉시 구매가 260만 메소')

if __name__ == '__main__':unittest.main()
