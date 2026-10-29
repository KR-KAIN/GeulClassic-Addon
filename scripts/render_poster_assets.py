"""Render the addon's real windows with sample data for the how-to poster
(docs/poster/poster.html -> resources/help/how-to-use.png).

Usage: python scripts/render_poster_assets.py [out_dir]   (default docs/poster)
Then render the page headless, e.g.
  msedge --headless=new --hide-scrollbars --window-size=1240,3400 --screenshot=poster.png poster.html
"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)
from kain_maple_translator import classic_ui as CU
CU.set_game_size(1920, 1080)
app.setPalette(CU.light_palette())
from kain_maple_translator import main as M
from kain_maple_translator.classic_windows import PriceLogWindow
from kain_maple_translator.item_info import current_db
from kain_maple_translator.item_options import seller_options
from kain_maple_translator import item_tooltip as TT
out = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / 'docs' / 'poster')
os.makedirs(out, exist_ok=True)


class Log:
    def summary(self, q):
        rows = [('pure water', '맑은 물', (700, 750, 850, 9), (500, 700, 760, 112), 750, 'B', 5),
                ('Work Gloves', '노가다 목장갑', (6000000, 7500000, 9000000, 14), (5500000, 6500000, 7000000, 8), 9000000, 'S', 12),
                ('Wolbi Throwing Stars', '월비 표창', (1400, 1500, 2000, 22), None, 1500, 'S', 31),
                ('Earring INT 60%', '귀고리 지력 60% 주문서', (45000, 50000, 60000, 17), (40000, 45000, 50000, 9), 50000, 'S', 44),
                ('Steel Igor', '스틸 이고르', (8000, 8000, 9000, 4), None, 8000, 'S', 70),
                ('Angel Halo', '천사의 헤일로', (330000, 370000, 450000, 47), (350000, 350000, 350000, 1), 360000, 'S', 95)]
        import time
        now = time.time()
        return [{'item': a, 'korean': b, 'sell': c, 'buy': d, 'last_price': e, 'last_side': f, 'last': now - g * 60,
                 'count': (c[3] if c else 0) + (d[3] if d else 0)} for a, b, c, d, e, f, g in rows]

    def clear(self):
        pass


shots = {}
panel = M.CompactSettings(); panel.fit_bottom_hud(390, 126); panel.update_live(True)
panel.set_status('번역 표시됨 · MinnowD'); panel.show(); shots['panel'] = panel
chat = M.FloatingChat(); chat.apply_style({}, 100); chat.resize(470, 560); chat.show(); chat.set_split_ratio(55)
mega = [('Seller', '[노가다 목장갑] 공격력 8 업그레이드 가능 3회 팝니다. 가격 900만 메소', '[고확]', 'pink', '#e7a6c4', '#3d0f24', '#3d0f24'),
        ('Genifly', '맑은 물 개당 750 메소, 장어구이 개당 400 메소 삽니다', '[아확]', 'yellow', '#e6b400', '#1a0906', '#1a0906')]
for i, (n, t, pre, tone, band, tc, nc) in enumerate(mega):
    chat.put({'nickname': n, 'translated': t, 'kind': 'item', 'prefix': pre, 'tone': tone, 'band_color': band,
              'text_color': tc, 'nickname_color': nc, 'message_id': i + 1, 'persist': False})
for i, (n, t) in enumerate([('Lxcifer', '파티 퀘스트 보너스 구간 참가 원해요'),
                            ('Amiibo', '월비 표창 팝니다. 개당 1천 500 메소'),
                            ('vnxy', 'MP 포션 남는 분 있나요? 메소가 다 떨어졌어요'),
                            ('Leo', '커닝 파퀘 연속 진행 모집해요 (30레벨 이상)')]):
    chat.put({'nickname': n, 'translated': t, 'kind': 'normal', 'message_id': 20 + i, 'persist': False})
shots['chat'] = chat
price = PriceLogWindow(Log()); price.resize(860, 330); price.show(); shots['price'] = price
comp = M.CompactComposer(); comp.fit_bottom_hud(390, 126); comp.show()
from kain_maple_translator.translation import Translator
_src = '노가다 목장갑 8공 3작 900만에 팝니다'
comp.input.setText(_src); comp.result.setText(Translator(body_only=True).translate(_src, 'ko-en'))
shots['composer'] = comp
try:
    from kain_maple_translator.hunt_widget import HuntWindow
    hw = HuntWindow({}); hw.show(); shots['meter'] = hw
except Exception as e:
    print('meter skipped', e)


def go():
    for name, w in shots.items():
        w.grab().save(os.path.join(out, name + '.png'))
        print('saved', name)
    info = current_db().lookup('Work Gloves')
    if info is not None:
        img = TT.render(info, '노가다 목장갑', seller_options('S> Work Gloves 8 att 3 slots 9m'))
        TT.scaled_pixmap(img).save(os.path.join(out, 'tooltip.png'))
        print('saved tooltip')
    app.quit()


QTimer.singleShot(1500, go)
app.exec()
