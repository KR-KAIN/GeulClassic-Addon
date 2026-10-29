"""R18: EXP rate / level ETA, potion alerts, hunting log, keyword alerts, price log."""
import os
import tempfile
import unittest
from pathlib import Path

from kain_maple_translator.hunt_stats import HuntSession, SlotRecord
from kain_maple_translator import hunt_extras as HX
from kain_maple_translator.chat_alerts import KeywordAlerts, parse_keywords
from kain_maple_translator.price_log import extract_prices, PriceLog


def _session(minutes=10):
    clock = [0.]
    s = HuntSession(clock=lambda: clock[0])
    s.start()
    s.observe_exp(30, 10000, 40.0)
    clock[0] = minutes*60
    s.observe_exp(30, 13200, 52.8)
    return s, clock


class ExpRateAndEta(unittest.TestCase):
    def test_rate_and_eta(self):
        s, _ = _session(10)
        self.assertEqual(HX.exp_per_hour(s), 19200)          # 3,200 in 10 min
        # 13,200 at 52.8% -> 25,000 per level -> 11,800 left at 320/min
        self.assertAlmostEqual(HX.level_up_seconds(s), 11800/320*60, delta=5)
        self.assertEqual(HX.format_duration(HX.level_up_seconds(s)), '36분')

    def test_no_numbers_before_twenty_seconds(self):
        s, clock = _session(0)
        clock[0] = 5
        self.assertIsNone(HX.exp_per_hour(s))
        self.assertIsNone(HX.level_up_seconds(s))

    def test_formats(self):
        self.assertEqual(HX.format_amount(19200), '19,200')
        self.assertEqual(HX.format_amount(1234567), '123.5만')
        self.assertEqual(HX.format_amount(250_000_000), '2.5억')
        self.assertEqual(HX.format_duration(3*3600+5*60), '3시간 5분')
        self.assertEqual(HX.format_duration(30), '1분 미만')


class Potions(unittest.TestCase):
    def test_minutes_left_and_low_slots(self):
        s, _ = _session(10)
        s.slots['Ctrl'] = SlotRecord('a', 300, 100, 200)    # 200 used in 10 min
        s.slots['Del'] = SlotRecord('b', 50, 50, 0)
        self.assertAlmostEqual(HX.potion_minutes(s.slots['Ctrl'], s.elapsed_seconds), 5.0)
        self.assertIsNone(HX.potion_minutes(s.slots['Del'], s.elapsed_seconds))
        self.assertEqual(HX.low_potion_slots(s, 100), ['Ctrl', 'Del'])
        self.assertEqual(HX.low_potion_slots(s, 0), [])


class HuntLog(unittest.TestCase):
    def test_record_and_reload(self):
        s, _ = _session(10)
        s.slots['Ctrl'] = SlotRecord('a', 300, 100, 200)
        path = Path(tempfile.mkdtemp())/'hunt-log.json'
        rec = HX.session_record(s, 'Ant Tunnel')
        HX.append_hunt(rec, path)
        rows = HX.load_hunt_log(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['gained_exp'], 3200)
        self.assertEqual(rows[0]['exp_per_hour'], 19200)
        self.assertEqual(rows[0]['potions_total'], 200)
        self.assertEqual(rows[0]['place'], 'Ant Tunnel')


class Keywords(unittest.TestCase):
    def test_match_original_or_translation_once(self):
        clock = [0.]
        a = KeywordAlerts(parse_keywords('노가다 목장갑\nkpq, 일비'), clock=lambda: clock[0])
        self.assertEqual(a.check('Snowy', 'S> Work Gloves 11att 15m', '노가다 목장갑 공격력 11 팝니다'), '노가다 목장갑')
        self.assertIsNone(a.check('Snowy', 'S> Work Gloves 11att 15m', '노가다 목장갑 공격력 11 팝니다'))  # repeat
        self.assertEqual(a.check('Bob', 'LF KPQ rush', '커닝 파퀘'), 'kpq')
        self.assertIsNone(a.check('Bob', 'hello there', '안녕'))
        clock[0] = 500
        self.assertEqual(a.check('Snowy', 'S> Work Gloves 11att 15m', '노가다 목장갑'), '노가다 목장갑')

    def test_parse(self):
        self.assertEqual(parse_keywords('a\n일비, 일비\n  KPQ '), ['일비', 'KPQ'])


class Prices(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_prices('S> Work Gloves 11att 15m'), [('S', 'Work Gloves 11att', 15_000_000)])
        self.assertEqual(extract_prices('B> 60%Scrolls Claw140k Dagger135k'),
                         [('B', 'Claw 60%', 140_000), ('B', 'Dagger 60%', 135_000)])
        self.assertEqual(extract_prices('[Angel Halo] S> 1.2m obo'), [('S', 'Angel Halo', 1_200_000)])
        self.assertEqual(extract_prices('S> 17.5K NX hat'), [])          # cash, not mesos
        self.assertEqual(extract_prices('hello 5m guys'), [])           # no trade marker

    def test_log_summary_and_dedupe(self):
        log = PriceLog(Path(tempfile.mkdtemp())/'p.sqlite3')
        self.assertEqual(log.record('a', 'S> Work Gloves 11att 15m'), 1)
        self.assertEqual(log.record('a', 'S> Work Gloves 11att 15m'), 0)   # same megaphone again
        log.record('b', 'S> Work Gloves 11att 13m')
        row = log.summary('work gloves')[0]
        self.assertEqual(row['sell'][0], 13_000_000)
        self.assertEqual(row['sell'][2], 15_000_000)
        self.assertEqual(row['sell'][3], 2)
        self.assertIn('노가다 목장갑', row['korean'])


class Windows(unittest.TestCase):
    def test_windows_build(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        os.environ['LOCALAPPDATA'] = tempfile.mkdtemp()
        from kain_maple_translator.classic_windows import HuntLogWindow, PriceLogWindow, KeywordToast
        h = HuntLogWindow(path=Path(os.environ['LOCALAPPDATA'])/'h.json')
        p = PriceLogWindow(PriceLog(Path(os.environ['LOCALAPPDATA'])/'p.sqlite3'))
        t = KeywordToast('일비', 'Bob', 'S> ilbis 15m')
        for w in (h, p, t):
            self.assertFalse(w.grab().isNull())
            w.close()


class ConfigKeeps(unittest.TestCase):
    def test_new_settings_survive_reload(self):
        import json
        from kain_maple_translator.core import load_config
        path = Path(tempfile.mkdtemp())/'config.json'
        path.write_text(json.dumps({'alert_keywords': ['PQ'], 'alert_popup': False, 'hunt_potion_warn': 50,
                                    'price_log_enabled': False}), encoding='utf-8')
        cfg = load_config(path)
        self.assertEqual(cfg['alert_keywords'], ['PQ'])
        self.assertFalse(cfg['alert_popup'])
        self.assertEqual(cfg['hunt_potion_warn'], 50)
        self.assertFalse(cfg['price_log_enabled'])


class InspectionFixes(unittest.TestCase):
    """Lines from the R18 live Free Market inspection (fast path, no model)."""
    def test_lines(self):
        from unittest.mock import patch
        from kain_maple_translator.translation import Translator
        tr = Translator(body_only=True)
        cases = {
            '1>PQ BONUs @@@@@@@@@@@@@②@④@@@②②': '파티 퀘스트 보너스 구간 참가 원해요',
            'R>Last for bonus': '파티 퀘스트 보너스 구간 1명 모집해요',
            'R> RUSH (1)': '파티 퀘스트 연속 진행 1명 모집해요',
            'JPOQQQQQ.': '파티 퀘스트 참가 원해요',
            'R>ORANGE POTS 120FAL': '주황 포션 삽니다. 개당 120',
            'S> PAN UID 65k': '냄비 뚜껑 팝니다. 가격 6만 5천 메소',
            '[Battle Scar] Sell PMO': '[바람의 흉터] 팝니다. 귓말 주세요',
            'iame 4 fame @@@@@@@@@@': '맞인기도 해요 (서로 인기도 올려 주기)',
        }
        with patch('kain_maple_translator.translation.translate_generic_many',
                   side_effect=AssertionError('AI called')):
            for source, expected in cases.items():
                self.assertEqual(tr.translate_fast(source), expected, source)
            out = tr.translate_fast('[에메랄드 귀고리] +4 crit damage and 3 slot left! taking offers')
            for part in ('크리티컬 데미지 +4', '업그레이드 가능 3회', '가격 제안 받습니다'):
                self.assertIn(part, out)
            out = tr.translate_fast('B> Pure Water 740@@@@@White Potion 250C@@@@@@@@@ c0@@@@@@@@@6c@e2cc@@@@')
            # R19: a consumable price list keeps one price per item
            self.assertEqual(out, '맑은 물 740, 하얀 포션 250 삽니다')

    def test_hallucination_guard(self):
        from kain_maple_translator.chat_fixups import guard_hallucination
        self.assertEqual(guard_hallucination('gamba', '뚱 베어'), 'gamba')
        self.assertEqual(guard_hallucination('RONIS', 'RONIS의 특징'), 'RONIS')
        self.assertEqual(guard_hallucination('hello', '안녕'), '안녕')


class PanelButtonsToggle(unittest.TestCase):
    def test_toggle_methods(self):
        from types import SimpleNamespace
        from kain_maple_translator import main as M
        shown = []
        meter = SimpleNamespace(visible=False)
        meter.isVisible = lambda: meter.visible
        meter.hide = lambda: setattr(meter, 'visible', False)
        app = SimpleNamespace(hunt_widget=meter)
        app.show_hunt_stats = lambda: (setattr(meter, 'visible', True), shown.append(1))
        M.Controller.toggle_hunt_stats(app)
        self.assertTrue(meter.visible)
        M.Controller.toggle_hunt_stats(app)
        self.assertFalse(meter.visible)

    def test_meter_stays_open_while_measuring(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from kain_maple_translator.hunt_widget import HuntWindow
        w = HuntWindow({}, None)
        w.show()
        w.session.start()
        self.assertFalse(w.request_hide())
        self.assertTrue(w.isVisible())
        self.assertIn('종료', w.hint.text())
        w.session.finish()
        self.assertTrue(w.request_hide())
        self.assertFalse(w.isVisible())
        w.shutdown() if hasattr(w, 'shutdown') else None


class LevelMisreads(unittest.TestCase):
    """R18 live: idle in the Free Market, the meter showed '+1,952~'."""
    def test_misread_level_is_not_a_level_up(self):
        s = HuntSession(); s.start()
        s.observe_exp(1, 1952, 14.23)     # '18' read as '1'
        s.observe_exp(18, 1952, 14.23)
        s.observe_exp(18, 1952, 14.23)
        self.assertEqual(s.gained_exp, 0)
        self.assertFalse(s.exp_estimated)

    def test_real_level_up_still_counts(self):
        s = HuntSession(); s.start()
        s.observe_exp(18, 9500, 95.0)     # requirement 10,000
        s.observe_exp(19, 200, 1.0)
        self.assertEqual(s.gained_exp, 500+200)

    def test_too_high_level_reanchors(self):
        s = HuntSession(); s.start()
        s.observe_exp(81, 1952, 14.23)    # '18' read as '81' first
        for _ in range(3):
            s.observe_exp(18, 1952, 14.23)
        s.observe_exp(18, 2052, 14.96)
        self.assertEqual(s.gained_exp, 100)
