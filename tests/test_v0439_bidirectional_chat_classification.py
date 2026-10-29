"""Prevents accidental ordinary/megaphone switching and source link false positives."""
import unittest
import cv2
import numpy as np
from kain_maple_translator.vision import Line
from kain_maple_translator.row_admission import classified_chat_rows, RowAdmission, _CLASSIFIED_CACHE
from kain_maple_translator.megaphone import row_appearance


def scene(bg=(25,25,25), fg=(245,245,245), name='Alice : ', body='S> GFA 60%'):
    im=np.full((39,620,3),bg,dtype=np.uint8)
    cv2.putText(im,name,(5,26),cv2.FONT_HERSHEY_SIMPLEX,.66,fg,1,cv2.LINE_AA)
    cv2.putText(im,body,(105,26),cv2.FONT_HERSHEY_SIMPLEX,.66,fg,1,cv2.LINE_AA)
    return im

class ClassificationCorrections(unittest.TestCase):
    def setUp(self): _CLASSIFIED_CACHE.clear()
    def test_same_text_mega_then_general_must_not_inherit_class(self):
        gate=RowAdmission()
        mega={'nickname':'Alice','body':'S> GFA 60%','kind':'super','band_color':'#efb4ba','confidence':.99,'rect':(2,2,350,25)}
        self.assertEqual(gate.filter([dict(mega)],1.)[0]['kind'],'super')
        ordinary={**mega,'kind':'normal','band_color':'','tone':'none','prefix':'','source_white_body':True}
        out=gate.filter([ordinary],1.15)
        self.assertEqual(out[0]['kind'],'normal')
    def test_identical_text_general_then_pink_megaphone(self):
        normal=scene(); pink=scene(bg=(222,211,244),fg=(90,30,130))
        for im in (normal,pink):
            row=classified_chat_rows([Line('Alice : S> GFA 60%',.99,(2,4,320,24))],im,0,0)[0]
            if im is normal:self.assertEqual(row['kind'],'normal')
            else:self.assertNotEqual(row['kind'],'normal')
    def test_coloured_item_in_white_chat_does_not_trigger_glyph_vote(self):
        image=scene(body='',name='Alice : ')
        cv2.putText(image,'[Hat]',(110,26),cv2.FONT_HERSHEY_SIMPLEX,.66,(200,100,240),1,cv2.LINE_AA)
        cv2.putText(image,' S> 5m',(192,26),cv2.FONT_HERSHEY_SIMPLEX,.66,(245,245,245),1,cv2.LINE_AA)
        result=row_appearance(image,(2,4,325,24),(0,0),'[Hat] S> 5m',{'body_start':99,'name_end':78,'item_ranges':[(105,197)]})
        self.assertEqual(result['kind'],'normal',result)
        self.assertFalse(result.get('glyph_color_confirmed',False))
    def test_bannerless_colored_message_without_item_still_detected(self):
        image=scene(fg=(200,100,240))
        row=row_appearance(image,(2,4,325,24),(0,0),'S> GFA 60%',{'body_start':99,'name_end':78,'item_ranges':[]})
        self.assertNotEqual(row['kind'],'normal',row)
    def test_pastel_background_white_body_remains_announcement(self):
        im=scene(bg=(228,213,248),fg=(248,248,248))
        row=classified_chat_rows([Line('Alice : S> GFA 60%',.99,(2,4,325,24))],im,0,0)[0]
        self.assertNotEqual(row['kind'],'normal',row)

if __name__=='__main__': unittest.main()
