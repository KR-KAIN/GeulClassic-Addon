"""Real user-crop replay. This is not a live Windows gameplay certification."""
from kain_maple_translator.console_io import configure_utf8_console
configure_utf8_console()
from pathlib import Path
import cv2
import numpy as np

from kain_maple_translator.vision import TextRecognizer
from kain_maple_translator.fast_vision import IncrementalChatOCR
from kain_maple_translator.row_admission import classified_chat_rows
from kain_maple_translator.frame_context import inspect_scrollbar,without_scrollbar


def replay():
    root=Path(__file__).resolve().parents[1]/'tests/fixtures'
    if not root.is_dir():
        # public clone: the real game screenshots are not published
        print('OCR REPLAY SKIPPED: tests/fixtures is not in the public repository',flush=True)
        return
    engine=IncrementalChatOCR(TextRecognizer())
    gray=cv2.imread(str(root/'gray-blue-megaphone.png'))
    lines=engine.detect(gray,0,0)
    rows=classified_chat_rows(lines,gray,0,0)
    assert len(rows)==1 and rows[0]['tone']=='gray' and rows[0]['kind']!='normal', rows
    assert 'KPQ' in rows[0]['body'] and 'FARMING' in rows[0]['body'], rows
    print('REAL GRAY BLUE PASS:',rows[0]['body'],engine.stats,flush=True)
    # A real OCR invocation can take seconds; meanwhile the deliberate
    # 0.15s confidence-cache TTL may expire (especially while logging through
    # Windows PowerShell Out-File). No change in pixels must mean no change in
    # recognized chat, but a later model refresh is allowed and desirable.
    again=classified_chat_rows(engine.detect(gray,0,0),gray,0,0)
    assert [(r['nickname'],r['body'],r['tone']) for r in again] == [
        (r['nickname'],r['body'],r['tone']) for r in rows],(rows,again,engine.stats)
    print('REAL UNCHANGED FRAME CONTENT STABILITY PASS:',engine.stats,flush=True)
    red=cv2.imread(str(root/'red-system-excluded.png'))
    lines=engine.detect(red,0,0)
    assert classified_chat_rows(lines,red,0,0)==[], lines
    assert any('obtained' in line.text for line in lines), lines
    print('REAL RED SYSTEM EXCLUSION PASS:',[line.text for line in lines],flush=True)
    partial=cv2.imread(str(root/'partial-coloured-chat.png'))
    lines=engine.detect(partial,0,0)
    rows=classified_chat_rows(lines,partial,0,0)
    assert not rows, rows  # cropped-out nicknames must not be manufactured
    print('REAL CLIPPED NICKNAME / NO PHANTOM GENERAL CHAT PASS',flush=True)
    # This fixture combines the user's real CH sprite with a synthetic full
    # name. It tests split/cache mechanics, not unseen native-font accuracy.
    prefix=cv2.imread(str(root/'calibrated-badge-full-prefix.png'))
    engine=IncrementalChatOCR(TextRecognizer())
    first=engine.detect(prefix,0,0)
    assert any(line.channel_hint and line.text.startswith('Alice :') for line in first),first
    changed=prefix.copy()
    changed[:,130:]=tuple(int(v) for v in np.median(prefix,axis=(0,1)))
    cv2.putText(changed,'S> WG 220k',(138,19),cv2.FONT_HERSHEY_SIMPLEX,.5,(140,50,90),1,cv2.LINE_AA)
    second=engine.detect(changed,0,0)
    # Cache TTL is intentionally short; an OCR refresh is allowed.
    # Verify that the changed body is actually read instead.
    assert any('220k' in line.text for line in second),second
    print('CALIBRATED BADGE / PREFIX CACHE REUSE PASS',flush=True)
    actual=cv2.imread(str(root/'user-four-colour-rows.png'))
    context=inspect_scrollbar(actual)
    assert context.at_bottom is True,context
    actual=without_scrollbar(actual,context)
    engine=IncrementalChatOCR(TextRecognizer())
    lines=engine.detect(actual,0,0)
    rows=classified_chat_rows(lines,actual,0,0)
    assert [row['nickname'] for row in rows]==['Nahoona','Nahoona','Galaciya','papa'],rows
    assert [row['tone'] for row in rows]==['cyan','cyan','yellow','pink'],rows
    for row,fragment in zip(rows,['150k / White beanie 50k','trash NX 15K','[Soft Chocolate Fondue Scepter]','mustache 80k beanie 55k ears 50k']):
        assert fragment in row['body'],row
    assert all(row['kind']!='normal' for row in rows),rows
    assert engine.stats['detector_recoveries']==0,engine.stats
    print('REAL FOUR COLOUR ROWS / DELIMITER / PRICES PASS:',rows,flush=True)
    from kain_maple_translator.translation import Translator
    translator=Translator(body_only=True)
    translated=[translator.translate_fast(row['body']) for row in rows]
    assert all(translated),translated
    assert all(amount in translated[3] for amount in ('1만 8천','8만','5만 5천','5만')),translated
    assert '[사르르 초코퐁듀 스틱]' in translated[2] and '제안' in translated[2],translated
    print('REAL FOUR ROWS / FAST RULE TRANSLATION / ALL PRICES PASS:',translated,flush=True)
    repeated=classified_chat_rows(engine.detect(actual,0,0),actual,0,0)
    assert [(r['nickname'],r['body'],r['tone']) for r in repeated] == [
        (r['nickname'],r['body'],r['tone']) for r in rows],(rows,repeated,engine.stats)
    print('REAL FOUR ROWS / NO REPEATED CONTENT PASS',flush=True)
    for foreground,background,kind in [((245,245,245),(25,25,25),'normal'),
                                       ((200,100,240),(25,25,25),'megaphone'),
                                       ((30,70,80),(195,220,95),'megaphone')]:
        generated=np.full((32,650,3),background,dtype=np.uint8)
        cv2.putText(generated,'Alice ; S> WG 220k',(5,24),cv2.FONT_HERSHEY_SIMPLEX,.65,foreground,1,cv2.LINE_AA)
        lines=engine.detect(generated,0,0)
        rows=classified_chat_rows(lines,generated,0,0)
        assert len(rows)==1 and rows[0]['nickname']=='Alice' and '220k' in rows[0]['body'],rows
        assert (rows[0]['kind']=='normal')==(kind=='normal'),rows
        print('SYNTHETIC ICONLESS SEMICOLON / SOURCE COLOUR PASS:',rows,flush=True)
    stat_frame=np.full((32,700,3),(199,221,95),dtype=np.uint8)
    cv2.putText(stat_frame,'Alice: S> glove att 60% Kfan +1 100% scrolls',(5,23),
                cv2.FONT_HERSHEY_SIMPLEX,.55,(50,100,80),1,cv2.LINE_AA)
    lines=engine.detect(stat_frame,0,0)
    rows=classified_chat_rows(lines,stat_frame,0,0)
    assert len(rows)==1 and rows[0]['nickname']=='Alice',rows
    import re
    assert re.findall(r'\d+',rows[0]['body'])==['60','1','100'],rows
    translated=Translator(body_only=True).translate_fast(rows[0]['body'])
    assert translated and '장갑 공격력 60% 주문서' in translated and '태극부채 +1' in translated and '100%' in translated,translated
    print('SYNTHETIC SCROLL OCR / ATTACK / BONUSES / RATES PASS:',rows[0]['body'],'=>',translated,flush=True)
    repeated=classified_chat_rows(engine.detect(stat_frame,0,0),stat_frame,0,0)
    assert [(r['nickname'],r['body']) for r in repeated] == [
        (r['nickname'],r['body']) for r in rows],(rows,repeated,engine.stats)
    print('SYNTHETIC SCROLL / UNCHANGED CONTENT PASS',flush=True)
    actual=cv2.imread(str(root/'user-native-palette-rows.png'))
    lines=engine.detect(actual,0,0)
    rows=classified_chat_rows(lines,actual,0,0)
    assert [r['nickname'] for r in rows]==['FaceTank','Bobindeck','Slicing','Xcarlet'],rows
    assert [r['tone'] for r in rows]==['cyan','pink','yellow','gray'],rows
    assert all(r['kind']!='normal' for r in rows),rows
    assert rows[2]['item_color']!=rows[2]['text_color'],rows[2]
    translated=Translator(body_only=True).translate_fast(rows[2]['body'])
    assert '[청 주름 치마]' in translated and '3만' in translated and '협의' in translated,translated
    print('REAL NATIVE PALETTE / ICONLESS GRAY / LINK RETENTION PASS:',translated,flush=True)
    ko=cv2.imread(str(root/'linked-labels-v28/ko-26.png'))
    lines=engine.detect(ko,0,0)
    rows=classified_chat_rows(lines,ko,0,0)
    assert len(rows)==1 and '[아대공격력주문서60%]' in ''.join(rows[0]['body'].split()),rows
    translated=Translator(body_only=True).translate_fast(rows[0]['body'])
    assert '60%' in translated and '22만' in translated,translated
    print('SYNTHETIC KOREAN ITEM-ONLY OCR / LINK AND PRICE PRESERVATION PASS:',translated,flush=True)


if __name__=='__main__':replay()
