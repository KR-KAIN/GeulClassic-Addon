"""R9 fallback contracts (synthetic samples, no real player/private content)."""
import unittest
import numpy as np
import cv2
from kain_maple_translator.fast_vision import (
    ink_rows, ink_rows_border_retry, _bright_glyph_rows,
)


def sample_brick_chat(lines):
    h,w=77,619
    result=np.zeros((h,w,3),dtype=np.uint8)
    for y in range(h):
        # Simulates a translucent chat box over textured brown field.
        for x in range(w):
            mortar=(x//43+y//13)%4 == 0
            result[y,x]=[32 if mortar else 40, 48 if mortar else 63,
                         70 if mortar else 99]
    for index,line in enumerate(lines):
        cv2.putText(result,line,(7,10+index*17),cv2.FONT_HERSHEY_SIMPLEX,
                    .32,(219,219,221),1,cv2.LINE_AA)
    result[71:73,:]=(200,200,200)  # A straight chrome rule is NOT a glyph.
    result[:,-7:]=(176,181,194) # scrollbar; ignored by fallback
    return result


class R9BrightGlyphFallbackTests(unittest.TestCase):
    def test_video_like_light_text_over_bricks_has_independent_rows(self):
        frame=sample_brick_chat(['S> HELLO 123','B> BUYING WAND','J> ANY PQ', 'S> TRADING'])
        found, uncertain, used=ink_rows_border_retry(frame)
        self.assertGreaterEqual(len(found),3)
        self.assertTrue(all(6<=r.rect[3]<=26 for r in found))
        self.assertTrue(all(r.original.shape==r.neutral.shape for r in found))
    def test_no_ink_empty_scene_does_not_hallucinate_rows(self):
        frame=sample_brick_chat([])
        found, _,_=ink_rows_border_retry(frame)
        self.assertEqual(found,[])
    def test_single_short_chat_message_is_not_lost(self):
        frame=sample_brick_chat(['S> HELLO'])
        found,_,_=ink_rows_border_retry(frame)
        self.assertTrue(found)
    def test_existing_normal_segmentation_is_preserved(self):
        frame=np.full((77,619,3),35,dtype=np.uint8)
        cv2.putText(frame,'S> buying scroll',(14,26),cv2.FONT_HERSHEY_SIMPLEX,.50,
                    (241,241,241),1,cv2.LINE_AA)
        old,uncertain=ink_rows(frame)
        new,_,used=ink_rows_border_retry(frame)
        if old and not uncertain:
            self.assertEqual(used,0)
            self.assertEqual([r.rect for r in new],[r.rect for r in old])
    def test_pixels_not_text_are_in_cache_key(self):
        sample=sample_brick_chat(['S> HELLO','S> HELLO'])
        out=_bright_glyph_rows(sample)
        self.assertTrue(out)
        self.assertEqual(len(out[0].key),16)


if __name__=='__main__':
    unittest.main()
