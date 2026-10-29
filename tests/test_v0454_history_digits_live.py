"""Regression cases from real quickslots and the live shared Maple screen."""
import json
import hashlib
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np
from kain_maple_translator.hunt_capture import locate_keyboard,potion_crops,read_potion_amounts,recognize_amount,_amount_consensus
from kain_maple_translator.stack_digits import match_stack_digits
from kain_maple_translator.potion_icon_db import PotionIconLibrary,ROOT as POTION_ROOT
from kain_maple_translator.image_io import read_image
from kain_maple_translator.chat_history import ChatHistoryStore
from kain_maple_translator.visual_message_ledger import FrameMessageLedger
from kain_maple_translator.translation import Translator
ROOT=Path(__file__).resolve().parents[1]


class RealQuickslotTests(unittest.TestCase):
    def test_actual_numbers_in_both_capture_sizes_without_language_ocr(self):
        expected={'hunt-keyboard-counts-user.png':{'Ctrl':40,'Del':1,'End':None,'PgDn':1},
                  'hunt-keyboard-real.png':{'Ctrl':37,'Del':None,'End':10,'PgDn':2}}
        for filename,want in expected.items():
            image=read_image(ROOT/'tests/fixtures'/filename)
            crops=potion_crops(image,locate_keyboard(image))
            with self.subTest(filename=filename):self.assertEqual(read_potion_amounts(None,crops),want)

    def test_wrong_word_fragments_and_weak_single_read_are_rejected(self):
        for text in ['i1','1S','年67','Ctrl 99','99 5','10000','-3']:
            self.assertIsNone(recognize_amount(text))
        self.assertIsNone(_amount_consensus([('87',.6894),('年67',.4119)]))
        self.assertEqual(_amount_consensus([('40',.916),('40',.872),('40',.893),('4',.534)]),40)
        self.assertIsNone(_amount_consensus([('40',.96),('48',.95)]))

    def test_blank_chrome_and_coloured_blocks_are_not_numeric_counts(self):
        for value in [0,32,128,220,255]:self.assertIsNone(match_stack_digits(np.full((44,49,3),value,np.uint8)))

    def test_png_assets_load_from_korean_exe_path_when_imread_cannot(self):
        with tempfile.TemporaryDirectory(prefix='글클메-검증-') as td:
            resource=Path(td)/'글클메 애드온/resources/hunt/potions'
            shutil.copytree(POTION_ROOT,resource)
            with patch('cv2.imread',return_value=None):
                db=PotionIconLibrary(resource,user=Path(td)/'empty')
                self.assertEqual(len(db.templates),54)
                self.assertEqual(len(db._references),4)
                image=read_image(ROOT/'tests/fixtures/hunt-keyboard-counts-user.png')
                crops=potion_crops(image,locate_keyboard(image,read_image(ROOT/'resources/hunt/keyboard-reference.png')))
                self.assertEqual(db.identify(crops['Ctrl'])[0],'2000000')
                self.assertEqual(db.identify(crops['Del'])[0],'2002002')
                self.assertIsNone(db.identify(crops['End']))

    def test_recognition_glyph_provenance_and_hashes(self):
        folder=ROOT/'resources/hunt/digits';data=json.loads((folder/'manifest.json').read_text())
        # Validate every downloaded glyph, independent of manifest field names.
        for path in folder.glob('*.png'):
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(digest,json.dumps(data))
            self.assertIsNotNone(read_image(path,cv2.IMREAD_UNCHANGED))
        self.assertEqual(len(list(folder.glob('*.png'))),10)


class PersistentHistoryTests(unittest.TestCase):
    def record(self,index):
        return {'id':f'session-{index}','captured_unix':1700000000+index,
                'nickname':'검증 사용자','original':f'hello {index}',
                'translated':f'안녕하세요 {index}','kind':'normal'}

    def test_restart_keeps_all_rows_beyond_overlay_budget(self):
        with tempfile.TemporaryDirectory(prefix='번역-내역-') as td:
            path=Path(td)/'내역.sqlite3';store=ChatHistoryStore(path)
            for i in range(207):self.assertTrue(store.append(self.record(i)))
            self.assertFalse(store.append(self.record(206)))
            store.close();restored=ChatHistoryStore(path)
            self.assertEqual(restored.count(),207)
            self.assertEqual(len(restored.recent()),95)
            self.assertEqual(restored.recent()[0]['original'],'hello 112')
            self.assertEqual(restored.page(200)[-1]['original'],'hello 0')
            restored.close()

    def test_capture_order_search_literal_wildcards_and_explicit_clear(self):
        with tempfile.TemporaryDirectory() as td:
            store=ChatHistoryStore(Path(td)/'history.sqlite3')
            for i in [2,0,1]:store.append(self.record(i))
            self.assertEqual([r['original'] for r in store.recent()],['hello 0','hello 1','hello 2'])
            self.assertEqual(store.count('hello 1'),1)
            self.assertEqual(store.count('%'),0)
            store.clear();store.close()
            again=ChatHistoryStore(Path(td)/'history.sqlite3');self.assertEqual(again.count(),0);again.close()

    def test_corrupt_file_is_not_replaced_and_lost(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'history.sqlite3';path.write_bytes(b'preserve-corrupt-history')
            with self.assertRaises(Exception):ChatHistoryStore(path)
            self.assertEqual(path.read_bytes(),b'preserve-corrupt-history')


class PhysicalEventTests(unittest.TestCase):
    def row(self,body,y=30,left=200,top=300,height=100):
        return {'nickname':'Seller','body':body,'rect':(left,top+y,250,16),
                '_tracking_rect':(0,y-height,250,16)}

    def test_game_window_move_has_no_duplicate_and_new_bottom_is_kept(self):
        ledger=FrameMessageLedger()
        old=[self.row('S> scroll 5m',10),self.row('hello there',30)]
        self.assertEqual(len(ledger.filter(old,old,1)),2)
        moved=[self.row('S> scroll 5m',10,left=600,top=800),self.row('hello there',30,left=600,top=800)]
        self.assertEqual(ledger.filter(moved,moved,1.2),[])
        incoming=[self.row('hello there',10,left=600,top=800),self.row('S> scroll 5m',30,left=600,top=800)]
        self.assertEqual([r['body'] for r in ledger.filter(incoming,incoming,1.4)],['S> scroll 5m'])

    def test_auto_roi_top_height_drift_keeps_bottom_anchor(self):
        ledger=FrameMessageLedger();old=[self.row('Selling red potion 30k',30)]
        ledger.filter(old,old,1)
        shifted=[self.row('Selling red potion 30k',50,top=280,height=120)]
        self.assertEqual(ledger.filter(shifted,shifted,1.3),[])

    def test_link_spacing_jitter_same_event_but_changed_stat_is_new(self):
        ledger=FrameMessageLedger();a=[self.row('S> [장갑 공격력 주문서] 5m')];ledger.filter(a,a,1)
        b=[self.row('S>  [ 장갑 공격력 주문서 ] 5m')];self.assertEqual(ledger.filter(b,b,1.2),[])
        c=[self.row('S> [장갑 공격력 주문서] 6m')];self.assertEqual(ledger.filter(c,c,1.3),c)


class LiveTextTests(unittest.TestCase):
    def translate(self,text):
        with patch('kain_maple_translator.translation.translate_generic',side_effect=AssertionError('Unexpected generic translation')):
            return Translator().translate(text,'en-ko')

    def test_greetings_address_people_naturally(self):
        self.assertEqual(self.translate('hello guy'),'안녕!')
        for text in ['hi guys','hello, everyone!','hey bro','hello dude!']:
            result=self.translate(text);self.assertIn('안녕',result);self.assertNotIn('남자',result)
        from kain_maple_translator.natural_chat import phrase_override
        self.assertIsNone(phrase_override('The guy sells scrolls for 10m','en-ko'))

    def test_live_glove_buy_message_and_offer_request(self):
        result=self.translate('Buy Gloves Att scroll 10%')
        self.assertIn('장갑 공격력 10% 주문서',result);self.assertIn('삽니다',result)
        result=self.translate('[별 귀고리] S> a/w 800k leave offer!')
        self.assertIn('[별 귀고리]',result);self.assertIn('즉시 구매가 80만 메소',result)
        self.assertIn('가격 제안',result);self.assertNotIn('leave',result)

    def test_exact_item_title_echo_is_shown_once_without_merging_distinct_items(self):
        result=self.translate('[장갑] S> 장갑 800k')
        self.assertEqual(result.count('장갑'),1);self.assertIn('80만',result)
        result=self.translate('S> [장갑] 800k [망토] 900k')
        self.assertIn('[장갑]',result);self.assertIn('[망토]',result)
        self.assertIn('80만',result);self.assertIn('90만',result)

    def test_live_come_buy_it_is_a_sale_and_unknown_link_stays_intact(self):
        text='[Soft Chocolate Fondue Scepter] 1.8m come buy it'
        result=self.translate(text)
        self.assertIn('[사르르 초코퐁듀 스틱]',result)
        self.assertIn('180만 메소에 팝니다',result)
        self.assertNotIn('삽니다',result)


class HistoryWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_real_restore_archive_and_sample_does_not_persist(self):
        from kain_maple_translator.main import FloatingChat
        from kain_maple_translator.history_dialog import HistoryDialog
        with tempfile.TemporaryDirectory() as td:
            store=ChatHistoryStore(Path(td)/'history.sqlite3');chat=FloatingChat(store)
            for i in range(101):chat.put({'nickname':'User','original':f'hi {i}','translated':f'안녕 {i}',
                'message_id':f'run-{i}','order':(100+i,0)})
            chat.put({'nickname':'KAIN_TEST','translated':'번역창 표시 확인','persist':False})
            self.assertEqual(store.count(),101);self.assertEqual(len(chat._live_rows),95)
            chat.close();store.close();store=ChatHistoryStore(Path(td)/'history.sqlite3')
            restored=FloatingChat(store);restored.restore_history()
            self.assertEqual(len(restored._records),95)
            self.assertEqual(restored._records[-1]['original'],'hi 100')
            viewer=HistoryDialog(store);viewer.search.setText('hi 0')
            self.assertIn('원문: hi 0',viewer.contents.toPlainText())
            viewer.close();restored.close();store.close()

    def test_restart_initial_pixels_are_not_appended_but_a_new_repeat_is(self):
        from kain_maple_translator.main import FloatingChat
        with tempfile.TemporaryDirectory() as td:
            store=ChatHistoryStore(Path(td)/'history.sqlite3');chat=FloatingChat(store)
            record=dict(nickname='User',original='hello',translated='안녕',source_ink='same-pixels',
                        source_local_rect=(0,-20,100,17),captured_unix=time.time())
            chat.put({**record,'message_id':'old-session-1'})
            restarted=FloatingChat(store);restarted.restore_history()
            restarted.put({**record,'message_id':'new-session-1','startup_visible':True})
            self.assertEqual(store.count(),1)
            restarted.put({**record,'message_id':'new-session-2','startup_visible':False})
            self.assertEqual(store.count(),2)
            chat.close();restarted.close();store.close()

    def test_canonical_png_renders_whole_sprite_and_unknown_clears_it(self):
        from kain_maple_translator.hunt_widget import HuntWindow
        win=HuntWindow({});png=(POTION_ROOT/'2000000.png').read_bytes()
        win._show_slot('Ctrl',png)
        pix=win.slot_icons['Ctrl'].pixmap();raw=read_image(POTION_ROOT/'2000000.png',-1)
        self.assertEqual((pix.width(),pix.height()),(raw.shape[1],raw.shape[0]))
        self.assertEqual((win.slot_icons['Ctrl'].width(),win.slot_icons['Ctrl'].height()),(34,34))
        win._show_slot('Ctrl',b'');self.assertTrue(win.slot_icons['Ctrl'].pixmap().isNull())
        win.close()


class SlowInferenceTests(unittest.TestCase):
    def test_first_slow_read_does_not_expire_its_own_row_cache(self):
        from kain_maple_translator.fast_vision import IncrementalChatOCR
        clock=[0.];calls=[]
        class Reader:
            def __init__(self):self.ocr=self
            def recognize_txt(self,images):
                calls.append(len(images));clock[0]+=3.
                return SimpleNamespace(txts=['Alice: hello there']*len(images),scores=[.99]*len(images))
            def detect(self,*args):raise AssertionError('Unexpected detector')
        engine=IncrementalChatOCR(Reader(),clock=lambda:clock[0])
        image=np.full((50,400,3),25,np.uint8)
        cv2.putText(image,'Alice: hello there',(4,25),cv2.FONT_HERSHEY_SIMPLEX,.5,(245,245,245),1,cv2.LINE_AA)
        with patch.object(engine.badges,'split',return_value=None),patch.object(engine.badges,'split_plain',return_value=None):
            engine.detect(image,0,0);clock[0]+=.2;engine.detect(image,0,0)
            self.assertEqual(calls,[1])
            clock[0]+=3.;engine.detect(image,0,0);self.assertEqual(calls,[1,1])

    def test_slow_frame_can_confirm_unchanged_ink_but_not_arbitrary_old_text(self):
        from kain_maple_translator.row_admission import RowAdmission
        def row(key):return dict(nickname='Alice',body='hello there',confidence=.80,kind='normal',visual_key=key)
        gate=RowAdmission();self.assertEqual(gate.filter([row('pixels-a')],1),[])
        self.assertEqual(len(gate.filter([row('pixels-a')],6)),1)
        gate=RowAdmission();gate.filter([row('pixels-a')],1)
        self.assertEqual(gate.filter([row('different-ink')],6),[])

    def test_price_units_and_signed_stats_remain_separate_events(self):
        for a,b in [('S> scroll 5m','S> scroll 5k'),('S> glove ATT +2 5m','S> glove ATT -2 5m')]:
            ledger=FrameMessageLedger()
            def row(t):return dict(nickname='Seller',body=t,rect=(0,20,250,17))
            old=[row(a)];ledger.filter(old,old,1);new=[row(b)]
            self.assertEqual(ledger.filter(new,new,1.2),new)

if __name__=='__main__':unittest.main()
