"""R19: the game's item tooltip on [item] links in the translated chat."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from kain_maple_translator.item_info import ItemInfo, ItemInfoDB, db_path, _key
from kain_maple_translator.item_options import options_for_label, seller_options


def _iron_ball(**kw):
    data = dict(id=1442001, name='Iron Ball', name_ko='아이언 볼', overall='Equip',
                category='Two-Handed Weapon', sub='Pole Arm', req_level=15, req_str=35, req_dex=15,
                req_job=1, tuc=7, attack_speed=8, stats={'incWAT': 40})
    data.update(kw)
    return ItemInfo(**data)


class SellerOptions(unittest.TestCase):
    def test_stats_and_slots(self):
        self.assertEqual(seller_options('[Work Gloves] S> 8 att 3 slots 9m'), {'incWAT': 8, 'slots': 3})
        self.assertEqual(seller_options('S> 6ATT WG 2.6m'), {'incWAT': 6})
        self.assertEqual(seller_options('[Earrings] +3 luk +2 crit clean'),
                         {'incLUK': 3, 'incCRT': 2, 'clean': True})
        self.assertEqual(seller_options('[Bronze Cap] 24 wdef 2 hp 1 acc 7 slots'),
                         {'incPDD': 24, 'incMHP': 2, 'incACC': 1, 'slots': 7})
        self.assertEqual(seller_options('S> Brown Work Gloves 3 att, no slots 1.2m ch12 fm'),
                         {'incWAT': 3, 'slots': 0})

    def test_prices_and_scroll_names_are_not_stats(self):
        self.assertEqual(seller_options('b>60% earring luk 50k each'), {})
        self.assertEqual(seller_options('B> 10% Overall LUK 11k'), {})
        self.assertEqual(seller_options('[Red Skull Overall] S> 35k pm (2)'), {})
        self.assertEqual(seller_options('[Iron Ball] lv 15 S> 50k'), {})

    def test_options_belong_to_their_link(self):
        text = '[Cat Soul] S> 550K [Devil Wings] 8 att 130K'
        self.assertEqual(options_for_label(text, 0), {})
        self.assertEqual(options_for_label(text, 1), {'incWAT': 8})


class StatLines(unittest.TestCase):
    def test_clean_item_shows_base_values(self):
        from kain_maple_translator.item_tooltip import stat_lines
        lines, note = stat_lines(_iron_ball(), {})
        self.assertEqual(lines, [('분류', '폴암'), ('공격 속도', '슬로우'), ('Weapon Attack', '+40'),
                                 ('업그레이드 가능 횟수', '7')])
        self.assertIn('노작', note)

    def test_seller_values_replace_base(self):
        from kain_maple_translator.item_tooltip import stat_lines
        lines, note = stat_lines(_iron_ball(), {'incWAT': 45, 'slots': 4})
        self.assertIn(('Weapon Attack', '+45'), lines)
        self.assertIn(('업그레이드 가능 횟수', '4'), lines)
        self.assertIn('판매자', note)
        # stats claimed but slots not: remaining upgrades are unknown
        lines, _ = stat_lines(_iron_ball(), {'incWAT': 45})
        self.assertIn(('업그레이드 가능 횟수', '?'), lines)
        # 'clean' keeps the base item
        lines, note = stat_lines(_iron_ball(), {'incWAT': 45, 'clean': True})
        self.assertIn(('Weapon Attack', '+40'), lines)
        self.assertIn('노작', note)


class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_equip_and_use_item_sizes(self):
        from kain_maple_translator.item_tooltip import render, part
        for name in ('Frame2_c', 'ItemIcon_base', 'Can_reqLEV', 'Job_enable_1', 'Dot_0', 'Dot_1'):
            self.assertFalse(part(name).isNull(), name)
        img = render(_iron_ball(), '아이언 볼', {})
        # the game's equip tooltip is 236 wide (wider only for long text; the
        # offscreen test platform has no Gulim, so its fallback glyphs are wider)
        self.assertGreaterEqual(img.width(), 236)
        self.assertLessEqual(img.width(), 260)
        self.assertGreater(img.height(), 200)
        orange = ItemInfo(id=2010004, name='Orange', name_ko='오렌지', overall='Use',
                          desc_ko='달콤하고 맛있는 오렌지다.\\nMP를 약 50 회복시켜 준다.')
        img = render(orange, '', {})
        self.assertEqual(img.height(), 110)
        self.assertGreaterEqual(img.width(), 286)
        self.assertEqual(orange.description(), '달콤하고 맛있는 오렌지다.\nMP를 약 50 회복시켜 준다.')

    def test_label_under_mouse_in_a_chat_row(self):
        from PySide6.QtCore import QPoint
        from kain_maple_translator.main import FloatingChat
        from kain_maple_translator.item_tooltip import label_at
        chat = FloatingChat()
        row = chat._make_row('[아확] EH10', '[이블 스컬] 45만 메소에 팝니다',
                             {'kind': 'normal', 'original': '[Evil Skull] S>450k'})
        row.resize(600, 40)
        hits = {label_at(row, QPoint(x, 10), row._chat_head_len) for x in range(0, 600, 3)}
        self.assertIn(('이블 스컬', 0), hits)
        self.assertNotIn(('아확', 0), hits)          # the megaphone tag is not an item
        self.assertEqual(row._chat_record['original'], '[Evil Skull] S>450k')


@unittest.skipUnless(db_path().exists(), 'item-info database not built')
class ClassicWorldData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = ItemInfoDB()

    def test_iron_ball_is_classic_world_data(self):
        info = self.db.find_name('Iron Ball')
        self.assertIsNotNone(info)
        self.assertEqual((info.req_level, info.req_str, info.req_dex, info.tuc), (15, 35, 15, 7))
        self.assertEqual(info.stats.get('incWAT'), 40)
        self.assertTrue(info.icon.startswith(b'\x89PNG'))

    def test_korean_and_original_labels(self):
        self.assertEqual(self.db.find_name('아이언 볼').id, self.db.find_name('Iron Ball').id)
        gloves = self.db.lookup('노가다 목장갑')
        self.assertEqual(gloves.name, 'Work Gloves')
        # the chat shows our Korean wording; the row's original decides
        hit = self.db.lookup('없는 이름', '[Work Gloves] S> 8 att', 0)
        self.assertEqual(hit.name, 'Work Gloves')
        self.assertIsNone(self.db.lookup('아무 말', 'hello there'))

    def test_korean_description(self):
        orange = self.db.find_name('Orange')
        self.assertIn('MP를 약 50', orange.description())

    def test_order_free_key(self):
        self.assertEqual(_key('장갑 공격력 60% 주문서'), _key('장갑 공격력 주문서 60%'))


if __name__ == '__main__':
    unittest.main()
