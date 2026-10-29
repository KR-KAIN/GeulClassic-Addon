"""User's four real rows, separator-first parsing and Korean item retention."""
from pathlib import Path
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.badge_split import BadgeSplitter
from kain_maple_translator.core import parse_chat_line,should_translate_body
from kain_maple_translator.fast_vision import ink_rows
from kain_maple_translator.frame_context import inspect_scrollbar,without_scrollbar
from kain_maple_translator.ink_background import row_background
from kain_maple_translator.megaphone import row_appearance
from kain_maple_translator.megaphone_item_translation import localized_item_text
from kain_maple_translator.row_admission import classified_chat_rows,RowAdmission
from kain_maple_translator.translation import Translator
from kain_maple_translator.vision import Line

ROOT=Path(__file__).resolve().parents[1]


def draw(text,color=(245,245,245),background=(25,25,25)):
    image=np.full((32,650,3),background,dtype=np.uint8)
    cv2.putText(image,text,(5,24),cv2.FONT_HERSHEY_SIMPLEX,.65,color,1,cv2.LINE_AA)
    return image


class SeparatorTests(unittest.TestCase):
    def test_ascii_and_fullwidth_delimiters_preserve_body(self):
        for sep in ':：;；':
            self.assertEqual(parse_chat_line('Alice '+sep+' [DEX +3 장갑] 150k'),
                             ('Alice','[DEX +3 장갑] 150k'))

    def test_body_punctuation_and_item_punctuation_are_not_split_again(self):
        self.assertEqual(parse_chat_line('Alice; [Hat: A;B] meet 12:30; later'),
                         ('Alice','[Hat: A;B] meet 12:30; later'))

    def test_item_alone_and_clipped_badge_are_not_a_sender(self):
        for source in ('[Hat; Name] S> 150k','CH05 ; S> 150k','[아이템: 이름] 150k'):
            self.assertIsNone(parse_chat_line(source))

    def test_body_punctuation_cannot_create_another_sender_in_translation(self):
        tr=Translator(body_only=True)
        with patch('kain_maple_translator.translation.translate_generic',return_value='번역 결과'):
            result=tr.translate('lantern; any offers?','en-ko')
        self.assertNotIn('lantern :',result)

    def test_no_channel_icon_is_required_for_pixel_separator(self):
        image=draw('Alice ; S> WG 220k')
        row=ink_rows(image)[0][0]
        splitter=BadgeSplitter()
        self.assertIsNone(splitter.split(row.original,row.neutral))
        split=splitter.split_plain(row.original,row.neutral)
        self.assertIsNotNone(split)
        self.assertLess(split[0],split[1])

    def test_plain_message_without_delimiter_is_not_split_at_random(self):
        image=draw('hello everyone')
        row=ink_rows(image)[0][0]
        self.assertIsNone(BadgeSplitter().split_plain(row.original,row.neutral))


class RealScreenshotPixels(unittest.TestCase):
    def setUp(self):
        self.image=cv2.imread(str(ROOT/'tests/fixtures/user-four-colour-rows.png'))
        self.clean=without_scrollbar(self.image,inspect_scrollbar(self.image))

    def test_real_scrollbar_does_not_pause_new_messages(self):
        self.assertIs(inspect_scrollbar(self.image).at_bottom,True)

    def test_panel_edges_do_not_merge_adjacent_real_rows(self):
        rows,uncertain=ink_rows(self.clean)
        chat=[row for row in rows if row.rect[1]>=22]
        self.assertFalse(uncertain)
        self.assertEqual(len(chat),4)
        self.assertTrue(all(row.rect[3]<=26 for row in chat))

    def test_dense_first_row_does_not_choose_letters_as_background(self):
        background=row_background(self.image[22:45,:763])
        self.assertLess(float(np.max(np.abs(background[10]-background[9]))),15)

    def test_yellow_keeps_dark_sender_and_light_item_ink(self):
        rows,_=ink_rows(self.clean)
        yellow=next(row for row in rows if 65<=row.rect[1]<85)
        self.assertGreater(np.count_nonzero(yellow.neutral[:,:75,0]<120),40)
        self.assertGreater(np.count_nonzero(yellow.neutral[:,160:430,0]<120),100)

    def test_four_real_badges_confirm_separator_without_reading_ch_digits(self):
        rows,_=ink_rows(self.clean)
        splitter=BadgeSplitter()
        chat=[row for row in rows if row.rect[1]>=22]
        self.assertEqual(len(chat),4)
        self.assertTrue(all(splitter.split(row.original,row.neutral) is not None for row in chat))


class SourceColourTests(unittest.TestCase):
    def test_white_body_without_icon_is_normal(self):
        image=draw('Alice ; hello everyone')
        appearance=row_appearance(image,(2,5,260,24),(0,0),'hello everyone')
        self.assertEqual(appearance['kind'],'normal')

    def test_coloured_body_without_icon_or_background_is_megaphone(self):
        image=draw('Alice ; hello everyone',(200,100,240))
        appearance=row_appearance(image,(2,5,260,24),(0,0),'hello everyone')
        self.assertNotEqual(appearance['kind'],'normal')
        self.assertEqual(appearance['tone'],'pink')

    def test_coloured_background_without_icon_is_megaphone(self):
        image=draw('Alice ; hello everyone',(30,70,80),(195,220,95))
        self.assertNotEqual(row_appearance(image,(2,5,260,24),(0,0),'hello everyone')['kind'],'normal')

    def test_coloured_name_does_not_change_white_body_to_megaphone(self):
        image=draw('Alice ;',(200,100,240))
        cv2.putText(image,'hello everyone',(95,24),cv2.FONT_HERSHEY_SIMPLEX,.65,(245,245,245),1,cv2.LINE_AA)
        self.assertEqual(row_appearance(image,(2,5,270,24),(0,0),'hello everyone')['kind'],'normal')

    def test_coloured_item_link_does_not_override_white_body(self):
        image=draw('Alice ; [Hat]',(200,100,240))
        cv2.putText(image,'S> offer please',(155,24),cv2.FONT_HERSHEY_SIMPLEX,.65,(245,245,245),1,cv2.LINE_AA)
        self.assertEqual(row_appearance(image,(2,5,340,24),(0,0),'[Hat] S> offer please')['kind'],'normal')


class KoreanLinkTests(unittest.TestCase):
    def test_all_korean_body_and_item_stay_in_ordinary_chat(self):
        image=draw('Alice ; hello')
        lines=[Line('Alice ; [한글 아이템] 팝니다',.97,(2,5,260,24))]
        rows=classified_chat_rows(lines,image,0,0)
        self.assertEqual(rows[0]['body'],'[한글 아이템] 팝니다')
        gate=RowAdmission()
        gate.filter(rows,1.)
        accepted=gate.filter(rows,1.2)
        self.assertEqual(accepted[0]['body'],'[한글 아이템] 팝니다')

    def test_korean_link_cannot_be_changed_even_by_a_catalog_entry(self):
        label='[DEX +3 장갑]'
        with patch('kain_maple_translator.item_catalog.current_catalog') as catalog:
            catalog.return_value.replace.side_effect=lambda s:s.replace('DEX','changed').replace('장갑','changed')
            self.assertEqual(localized_item_text(label),label)

    def test_reverse_trade_keeps_korean_link_and_converts_price(self):
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('model called')):
            out=Translator().translate('[DEX +3 장갑] S> 150k','en-ko')
        self.assertIn('[DEX +3 장갑]',out)
        self.assertIn('15만',out)
        self.assertTrue(should_translate_body('[DEX +3 장갑] S> 150k',.97))

    def test_all_korean_message_does_not_call_a_model(self):
        source='[한글 아이템] 팝니다'
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('model called')):
            self.assertEqual(Translator().translate(source,'en-ko'),source)

    def test_two_korean_links_are_kept_exactly(self):
        source='[DEX +3 장갑] S> 150k; [별빛 모자] B> 220k'
        out=Translator().translate_fast(source)
        self.assertIn('[DEX +3 장갑]',out)
        self.assertIn('[별빛 모자]',out)
        self.assertIn('15만',out)
        self.assertIn('22만',out)


class ScreenshotTradeTests(unittest.TestCase):
    def test_linked_slash_listing_translates_both_prices_without_a_model(self):
        source='[Michael Wings] S> Michael wings 150k / White beanie 50k'
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('model called')):
            result=Translator(body_only=True).translate_fast(source)
        self.assertIsNotNone(result)
        self.assertIn('15만',result)
        self.assertIn('5만',result)
        self.assertIn('흰색 비니',result)

    def test_unpunctuated_four_item_listing_keeps_each_amount(self):
        source='S> trash NX 18k mustache 80k beanie 55k ears 50k'
        result=Translator(body_only=True).translate_fast(source)
        self.assertEqual(result,'잡캐시템 1만 8천 메소, 콧수염 8만 메소, 비니 5만 5천 메소, 귀 5만 메소 팝니다')

    def test_linked_offer_please_does_not_remain_english(self):
        source='[Soft Chocolate Fondue Scepter] S> this. offer please.'
        result=Translator(body_only=True).translate_fast(source)
        self.assertEqual(result,'[사르르 초코퐁듀 스틱] 팝니다. 가격을 제안해 주세요')

    def test_incomplete_price_chain_is_not_consumed(self):
        from kain_maple_translator.natural_trade import priced_item_list
        self.assertIsNone(priced_item_list('S> trash NX 18k mustache 80k offer later'))


if __name__=='__main__':unittest.main()
