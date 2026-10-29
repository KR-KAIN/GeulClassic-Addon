"""Native potion assets, bracket integrity, and wrapped source colours."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import unittest
from unittest.mock import patch
import cv2
import numpy as np

from kain_maple_translator.potion_icon_db import PotionIconLibrary, POTIONS, ROOT
from kain_maple_translator.hunt_capture import potion_crops, locate_keyboard
from kain_maple_translator.translation import Translator
from kain_maple_translator.linked_ocr import LinkedItemOCR, link_regions
from kain_maple_translator.chat_render import colored_item_html
from kain_maple_translator.core import merge_chat_ocr
from kain_maple_translator.source_palette import sample_palette
from kain_maple_translator.vision import Line


def render_slot(raw, scale=1., count='37'):
    sprite=cv2.resize(raw,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    slot=np.full((round(44*scale)+6,round(49*scale)+6,3),220,np.uint8)
    h,w=sprite.shape[:2];y=slot.shape[0]-h-3;x=slot.shape[1]-w-2
    alpha=sprite[:,:,3:4]/255.
    slot[y:y+h,x:x+w]=np.uint8(sprite[:,:,:3]*alpha+slot[y:y+h,x:x+w]*(1-alpha))
    cv2.putText(slot,count,(1,slot.shape[0]-3),cv2.FONT_HERSHEY_SIMPLEX,.32*scale,
                (255,255,255),1,cv2.LINE_AA)
    return slot


class BundledPotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(1)
        cls.db=PotionIconLibrary(user=Path('/no-user-potions'))

    def test_current_classic_assets_complete_and_hashes_intact(self):
        data=json.loads((ROOT/'manifest.json').read_text('utf8'))
        self.assertEqual(len(data['icons']),59)
        self.assertTrue(all(str(i['item_id']) in POTIONS for i in data['icons']))
        self.assertEqual(sum(i['size_bytes'] for i in data['icons']),62831)
        self.assertTrue(all('/data/current/' in i['source_url'] for i in data['icons']))
        for entry in data['icons']:
            blob=(ROOT/entry['file']).read_bytes()
            self.assertTrue(blob.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(hashlib.sha256(blob).hexdigest(),entry['sha256'])
        # Classic's 2002000 is Warrior Potion, unlike old GMS's numbering.
        self.assertEqual(POTIONS['2002000'],'Warrior Potion')
        self.assertIn('Sharpness Potion',POTIONS.values())

    def test_all_distinct_potions_on_scaled_slots_with_count_overlay(self):
        for name,_,png in self.db.templates:
            raw=cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_UNCHANGED)
            for scale in (.65,.8,1.,1.15):
                with self.subTest(potion=name,scale=scale):
                    found=self.db.identify(render_slot(raw,scale))
                    self.assertIsNotNone(found)
                    self.assertEqual(found[0],name)
                    self.assertEqual(found[1],png)

    def test_native_capture_red_blue_and_empty_slot(self):
        fixtures=Path(__file__).parent/'fixtures'
        for filename in ('hunt-keyboard-real.png','hunt-keyboard-counts-user.png'):
            image=cv2.imread(str(fixtures/filename))
            slots=potion_crops(image,locate_keyboard(image))
            expected=[('Ctrl','2000000'),('PgDn','2000003')]
            if filename=='hunt-keyboard-real.png':expected.append(('End','2010005'))
            else:expected.append(('Del','2002002'))
            for key,name in expected:
                found=self.db.identify(slots[key])
                self.assertIsNotNone(found)
                self.assertEqual(found[0],name)
                self.assertEqual(found[1],(ROOT/(name+'.png')).read_bytes())
            empty='Del' if filename=='hunt-keyboard-real.png' else 'End'
            self.assertIsNone(self.db.identify(slots[empty]))

    def test_blank_and_coloured_squares_are_not_potions(self):
        for color in ((220,220,220),(0,0,0),(0,0,255),(255,0,0),(0,255,255)):
            self.assertIsNone(self.db.identify(np.full((44,49,3),color,np.uint8)))

    def test_identical_art_has_one_visual_identity(self):
        for alias,base in [('2000007','2000000'),('2000008','2000003')]:
            self.assertEqual(self.db.aliases[alias],base)

    def test_changing_count_reuses_the_same_confirmed_artwork(self):
        db=PotionIconLibrary(user=Path('/no-user-potions'))
        first=db.identify(render_slot(db._raw['2000003'],1.,'37'))
        self.assertEqual(first[0],'2000003')
        with patch.object(db,'_slot_scores',side_effect=AssertionError('count triggered another scan')):
            second=db.identify(render_slot(db._raw['2000003'],1.,'36'))
        self.assertEqual(first,second)


class BracketTranslationTests(unittest.TestCase):
    def translate(self,text):
        with patch('kain_maple_translator.translation.translate_generic',
                   side_effect=AssertionError('unnecessary sentence model')):
            result=Translator(body_only=True).translate_fast(text)
        self.assertIsNotNone(result)
        return result

    def test_full_scroll_name_resolves_before_partial_dictionary(self):
        result=self.translate('S> [Gloves Attack Scroll: Intermediate] 180k S> Gloves Attack Scroll 60% 170k')
        self.assertIn('[장갑 공격력 60% 주문서]',result)
        for part in ('18만','17만','팝니다'):self.assertIn(part,result)
        self.assertNotIn('Intermediate',result)
        self.assertNotIn('Attack',result)

    def test_observed_mixed_scroll_typo_is_repaired_inside_complete_link(self):
        result=self.translate('S> [장갑Atack주문서:중급] 180k')
        self.assertIn('[장갑 공격력 주문서:중급]',result)
        self.assertIn('18만',result)

    def test_native_korean_and_mixed_bonuses_survive_verbatim(self):
        for label in ('[옐로우 스퀘어]','[천사 헤일로]','[장갑 공격력 주문서 60%]',
                      '[한글 ATT +2 장갑]','[알 수 없는 한글 아이템 +10]'):
            self.assertIn(label,self.translate('S> '+label+' 220k'))

    def test_fullwidth_korean_link_and_two_labels(self):
        result=self.translate('S> ［천사 헤일로］ 190k S> [옐로우 스퀘어] 220k')
        for part in ('[천사 헤일로]','[옐로우 스퀘어]','19만','22만'):self.assertIn(part,result)

    def test_unknown_name_is_not_guessed_as_attack_scroll(self):
        result=self.translate('S> [Unknown Attack Wing] 220k')
        self.assertIn('[Unknown Attack Wing]',result)
        self.assertNotIn('주문서',result)

    def test_korean_ocr_can_use_real_brackets_after_ctc_offsets_change(self):
        image=np.full((24,130,3),255,np.uint8)
        for x,right in [(5,False),(105,True)]:
            image[3:5,x:x+6]=0;image[19:21,x:x+6]=0
            image[3:21,x+(4 if right else 0):x+(6 if right else 2)]=0
        text='[人回 60%] S> 220k'
        self.assertEqual(len(link_regions(text,None,image)),1)
        class Korean:
            def recognize_txt(self,images):
                return SimpleNamespace(txts=['[장갑 공격력 주문서 60%]']*len(images),scores=[.98]*len(images))
        reader=LinkedItemOCR(Korean())
        result=reader.correct([(text,.99)],[(image,image)],[None])[0][0]
        self.assertEqual(result,'[장갑 공격력 주문서 60%] S> 220k')


class SourceColourTests(unittest.TestCase):
    def test_whole_row_recovery_replaces_failed_split_item_bounds(self):
        from kain_maple_translator.fast_vision import IncrementalChatOCR
        from collections import OrderedDict
        engine=object.__new__(IncrementalChatOCR)
        engine.clock=lambda:0.
        engine.badges=SimpleNamespace(split=lambda *a:(4,8,1.))
        engine.stage=dict(badge_ms=0.,prefix_cache_hits=0,delimiter_split_rows=0,badge_split_rows=0)
        engine.piece_cache=OrderedDict();engine.piece_links={};engine.piece_ends={}
        engine.piece_paired={}
        engine.row_meta={};engine.split_keys=set()
        image=np.full((24,220,3),255,np.uint8)
        row=SimpleNamespace(key=b'row',neutral=image,original=image,rect=(0,0,220,24),isolated_white=False)
        calls=[]
        def candidates(tasks,confirm_indices=()):
            calls.append(tasks)
            engine._candidate_paired=[False]*len(tasks)
            if len(calls)==1:
                engine._candidate_regions=[[],[]];engine._candidate_ends=[None,None]
                return [('',.2),('[아이템] S> 220k',.99)]
            engine._candidate_regions=[[(8,13,80,150)]];engine._candidate_ends=[200]
            return [('Alice : [아이템] S> 220k',.99)]
        engine._candidates=candidates
        self.assertEqual(engine._read_rows([row])[0][0],'Alice : [아이템] S> 220k')
        self.assertEqual(engine.row_meta[row.key]['item_ranges'],[(80,150)])

    def test_recognize_button_starts_preview_and_shows_embedded_png(self):
        from PySide6.QtWidgets import QApplication
        from unittest.mock import MagicMock
        from kain_maple_translator.hunt_widget import HuntWindow
        app=QApplication.instance() or QApplication([])
        capture=MagicMock()
        window=HuntWindow({})
        try:
            with patch('kain_maple_translator.hunt_widget.HuntCaptureThread',return_value=capture):
                window.redetect_btn.click()
            capture.start.assert_called_once()
            self.assertFalse(window.session.running)
            window.receive({'found_keyboard':True,'slots':[{'slot':'Ctrl','icon':'potion:2000000',
                'potion_id':'2000000','count':123,'png':(ROOT/'2000000.png').read_bytes()}]})
            self.assertFalse(window.slot_icons['Ctrl'].pixmap().isNull())
            self.assertEqual(window.slot_labels['Ctrl'].text(),'123')
            self.assertEqual(window.slot_icons['Ctrl'].toolTip(),'Red Potion')
            self.assertFalse(window.session.running)
            window.receive({'found_keyboard':True,'slots':[]})
            self.assertEqual(window.slot_labels['Ctrl'].text(),'—')
            self.assertEqual(window._preflight_slots,{})
        finally:
            window.close();window.deleteLater()
        self.assertIsNotNone(app)

    def test_link_only_row_does_not_supply_body_colour(self):
        im=np.full((24,120,3),(5,182,229),np.uint8)
        cv2.putText(im,'[ITEM]',(4,18),cv2.FONT_HERSHEY_SIMPLEX,.5,(148,251,254),1)
        got=sample_palette(im,'#e5b605',{'body_start':0,'item_ranges':[(0,120)]})
        self.assertIn('item_color',got)
        self.assertNotIn('text_color',got)

    def test_wrapped_links_do_not_exclude_same_x_on_next_line(self):
        im=np.full((48,310,3),(5,182,229),np.uint8)
        cv2.putText(im,'Alice:',(2,17),cv2.FONT_HERSHEY_SIMPLEX,.4,(6,65,99),1)
        cv2.putText(im,'[ITEM]',(75,17),cv2.FONT_HERSHEY_SIMPLEX,.5,(148,251,254),1)
        cv2.putText(im,'S> 180k',(3,42),cv2.FONT_HERSHEY_SIMPLEX,.5,(6,85,121),1)
        lines=[Line('Alice: [아이템]',.99,(0,0,310,23),source_meta={'body_start':74,'item_ranges':[(74,140)]}),
               Line('S> 180k',.99,(0,24,200,23),source_meta={'body_start':0})]
        row=merge_chat_ocr(lines)[0]
        self.assertIn('180k',row['body'])
        colors=sample_palette(im,'#e5b605',row['source_meta'])
        self.assertEqual(colors['text_color'],'#795506')
        self.assertEqual(colors['item_color'],'#fefb94')

    def test_qt_resets_body_colour_after_each_link(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QTextDocument,QTextCursor
        app=QApplication.instance() or QApplication([])
        document=QTextDocument()
        document.setHtml(colored_item_html('[한글 아이템] 본문 [다음 아이템] 뒷글','#fffe99','#795506'))
        plain=document.toPlainText()
        for word,color in [('한글','#fffe99'),('본문','#795506'),('다음','#fffe99'),('뒷글','#795506')]:
            cursor=QTextCursor(document);cursor.setPosition(plain.index(word))
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter,QTextCursor.MoveMode.KeepAnchor)
            self.assertEqual(cursor.charFormat().foreground().color().name(),color)
        self.assertIsNotNone(app)


if __name__=='__main__':unittest.main()
