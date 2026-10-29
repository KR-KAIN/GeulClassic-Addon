"""R18 full re-inspection: lines from a 2-minute live Free Market sample."""
import unittest

from kain_maple_translator.chat_cleanup import party_post, prepare_chat, polish_leftover
from kain_maple_translator.chat_fixups import casual_request, collapse_repeats, guard_hallucination
from kain_maple_translator.core import should_translate_body


class MesoAmounts(unittest.TestCase):
    def test_glued_meso_is_not_million(self):
        clean = prepare_chat('B< PureWATER ea750MESO BLUE PO ea 160MESO@@@@@')
        self.assertNotIn('750M ', clean)
        self.assertIn('750 meso', clean)
        self.assertIn('160 meso', clean)
        self.assertTrue(clean.startswith('B> '))

    def test_each_price_list(self):
        out = polish_leftover('맑은 물 ea 750 meso 파란 포션 ea 160 meso 삽니다')
        self.assertEqual(out, '맑은 물 개당 750 메소, 파란 포션 개당 160 메소 삽니다')
        self.assertNotIn('억', out)

    def test_price_crumb_and_or(self):
        self.assertIn('330k', prepare_chat('S> kumbi 330kE'))
        self.assertNotIn('330kE', prepare_chat('S> kumbi 330kE'))
        self.assertEqual(polish_leftover('어둠의 소악마 모자, 40k or price 삽니다'),
                         '어둠의 소악마 모자, 4만 메소 또는 가격 제안 삽니다')
        self.assertEqual(polish_leftover('금비 표창 34만 메소 only 팝니다'), '금비 표창 34만 메소 (메소 거래만) 팝니다')


class PartyPosts(unittest.TestCase):
    def check(self, text, expected):
        self.assertEqual(party_post(prepare_chat(text)), expected, text)

    def test_spaced_and_dashed_markers(self):
        self.check('J Rush', '파티 퀘스트 연속 진행 참가 원해요')
        self.check('J RUSH PQ', '파티 퀘스트 연속 진행 참가 원해요')
        self.check('J-pq', '파티 퀘스트 참가 원해요')
        self.check('J-oq!!', '파티 퀘스트 참가 원해요')
        self.check('IPT', '파티 참가 원해요')
        self.check('J>PQQ', '파티 퀘스트 참가 원해요')
        self.check('JPQ JPQ JPQJPQ !!!', '파티 퀘스트 참가 원해요')

    def test_recruit_variants(self):
        self.check('R> RUSH no trolls', '파티 퀘스트 연속 진행 모집해요 (트롤 사절)')
        self.check('B> BUSH no trolls @', '파티 퀘스트 연속 진행 모집해요 (트롤 사절)')
        self.check('R PQ Bonus NEED 2@@@@@@@cΦ@@2@@@@@@@e@ @@@', '파티 퀘스트 보너스 구간 2명 모집해요')

    def test_spam_crumbs(self):
        self.check('JPQ BonusQ@@@@@@②@@@@@@②@@c@@@@②@@0 ②②②②@②', '파티 퀘스트 보너스 구간 참가 원해요')
        self.check('1> Rush②@@@②@@@@@@②@@@e@@②@@@', '파티 퀘스트 연속 진행 참가 원해요')
        self.check('1 > Bonus @@@@@@2@@@2@@Φ2 @@@aa@aa@@a@@a@@@@a@@aaaa@@aa', '파티 퀘스트 보너스 구간 참가 원해요')
        self.check('R> RUSH FAST RUNS 6 © @ ② 6 @ @ @', '파티 퀘스트 연속 진행 모집해요 (빠르게)')
        self.check('R> RUSH FAST RU NS @ @ @ @', '파티 퀘스트 연속 진행 모집해요 (빠르게)')
        self.check('R> RUSH FAST RUNS @ @ ② @ C @ @ @', '파티 퀘스트 연속 진행 모집해요 (빠르게)')

    def test_need_count_survives_spaced_tail(self):
        self.assertIn('2', prepare_chat('R> PQ need 2 @ @ @'))


class CasualLines(unittest.TestCase):
    def test_short_replies(self):
        self.assertEqual(casual_request('me'), '저요')
        self.assertEqual(casual_request('Always'), '항상')
        self.assertEqual(casual_request('ing@'), '진행 중')

    def test_party_chat(self):
        self.assertEqual(casual_request('add me'), '저 추가해 주세요')
        self.assertEqual(casual_request('Add me, level 39'), '저 추가해 주세요 (레벨 39)')
        self.assertEqual(casual_request('LEAVE PARTY'), '파티 나갈게요')
        self.assertEqual(casual_request('TASTYDEW LEAVE PT IDIOT'), 'TASTYDEW 파티에서 나가, 바보야')
        self.assertEqual(casual_request('im not in pt'), '저 파티에 없어요')
        self.assertEqual(casual_request('joining pq'), '파티 퀘스트 참가할게요')

    def test_repeated_spam_once(self):
        self.assertEqual(collapse_repeats('Add me, level 39Add me, level 39Add me, level 39Add me, level 3'),
                         'Add me, level 39')
        self.assertEqual(collapse_repeats('S> Kumbi 340k'), 'S> Kumbi 340k')


class SecondLivePass(unittest.TestCase):
    """The rebuilt app's own 2-minute sample (same day)."""

    def party(self, text, expected):
        self.assertEqual(party_post(prepare_chat(text)), expected, text)

    def test_party_variants(self):
        self.party('.IPQ++++++++++++++++++', '파티 퀘스트 참가 원해요')
        self.party('LV37 JPQ RUSH @', '파티 퀘스트 연속 진행 참가 원해요 (37레벨)')
        self.party('i honus', '파티 퀘스트 보너스 구간 참가 원해요')
        self.party('I>>>>>>>>>>PQPQPQPQPQPPQPQanv', '파티 퀘스트 참가 원해요 (아무 파티나)')
        self.party('j> papapapapappapa any', '파티 퀘스트 참가 원해요 (아무 파티나)')
        self.party('IPo@e@@@@@@@@@@@@@@@④@@@c@@qe@@@ee ②②②②②', '파티 퀘스트 참가 원해요')
        self.party('JPQ@②②@@@Q@@②@@②2@Q@②@@2Qa @@@@a@@mb@aa@a@@@@a@@aa@@a@@@', '파티 퀘스트 참가 원해요')

    def test_ocr_trade_words(self):
        self.assertTrue(prepare_chat('h>60% earing luk 50k each').startswith('b>60% earring'))
        self.assertIn('blue potion 180 each', prepare_chat('R> Rlue notion 180 ach'))
        self.assertTrue(prepare_chat('S 60% Earrings DEX PMO').startswith('S> 60%'))
        self.assertEqual(prepare_chat('B>Halloween NX items T>Mokbi for Halloween Nx@..@@@'),
                         'B>Halloween NX items T>Mokbi for Halloween Nx')
        self.assertIn('NEW NX', prepare_chat('s> NEN NX dracula cape'))

    def test_polish(self):
        # no currency is invented when the player did not type one
        self.assertEqual(polish_leftover('파란 포션 삽니다. 개당 180'), '파란 포션 삽니다. 개당 180')
        self.assertEqual(polish_leftover('60% 귀고리 행운 . 삽니다'), '60% 귀고리 행운 삽니다')
        self.assertEqual(polish_leftover('아대 공격력 60 170k or OFFER! ! 팝니다'),
                         '아대 공격력 60 17만 메소 또는 가격 제안! 팝니다')
        self.assertEqual(polish_leftover('전신갑옷 armor 힘 100 삽니다'), '전신갑옷 힘 100 삽니다')

    def test_market_words(self):
        self.assertEqual(polish_leftover('Trash stats 귀고리 삽니다'), '저옵 귀고리 삽니다')
        self.assertEqual(polish_leftover('60% 귀고리 행운 6만 메소 cc12 fm 팝니다'),
                         '60% 귀고리 행운 6만 메소 12채널 자유시장 팝니다')
        self.assertEqual(polish_leftover('캐시 아이템 전부 show me 삽니다'), '캐시 아이템 전부 삽니다 · 물건 보여주세요')

    def test_bare_scroll_price(self):
        from kain_maple_translator.chat_fixups import bare_scroll_price
        self.assertEqual(bare_scroll_price('Pet Equip Speed Scroll 60%(53K)'), '펫 장비 이동속도 60% 주문서 5만 3천 메소')
        self.assertIsNone(bare_scroll_price('I need a scroll 60% now'))

    def test_r_items_is_buy(self):
        from kain_maple_translator.chat_cleanup import recruit_as_buy
        self.assertTrue(recruit_as_buy('R>Halloween NX items T>Mokhi').startswith('B> '))
        self.assertTrue(recruit_as_buy('R> PQ items rush').startswith('R>'))


class ThirdLivePass(unittest.TestCase):
    """R19 final sample of the rebuilt app."""

    def party(self, text, expected):
        self.assertEqual(party_post(prepare_chat(text)), expected, text)

    def test_party(self):
        self.party('PQ RUSHI', '파티 퀘스트 연속 진행 참가 원해요')
        self.party('PO RUSH', '파티 퀘스트 연속 진행 참가 원해요')
        self.party('J: RUSH', '파티 퀘스트 연속 진행 참가 원해요')
        self.party('1>Pa RusH@q2c@@@@@@@@@@@@@bce@@@e@@@@@', '파티 퀘스트 연속 진행 참가 원해요')
        self.party('IPQ ANYYYYYYYYYYY', '파티 퀘스트 참가 원해요 (아무 파티나)')
        self.party('Join PQ Bonus!!l@@@@@@@@@@@@@@e Q@@@②@②@@@@@22', '파티 퀘스트 보너스 구간 참가 원해요')

    def test_trade(self):
        self.assertIn('60% 800K', prepare_chat('B>GFA 60%800K'))
        self.assertEqual(polish_leftover('가죽 80 meso EA 삽니다'), '가죽 개당 80 메소 삽니다')
        self.assertEqual(guard_hallucination('gojo', '토토사이트'), 'gojo')

    def test_more_ocr_variants(self):
        self.assertIn('50k each', prepare_chat('B>ear dex 60% 50k cach0@@@@@@@@@@C@@@@@@@06'))
        self.assertNotIn(' 0', prepare_chat('B>ear dex 60% 50k cach0@@@@@@@@@@C@@@@@@@06'))
        self.assertIn('offer', prepare_chat('[별 귀고리]S> Ofer|'))
        self.assertTrue(prepare_chat('S>Devil Horns c/o 150k1').endswith('150k'))
        self.assertIn('c/o 2.5m', prepare_chat('S>14 Speed Shoes C/ 2.5m aw = 5m'))
        self.assertTrue(prepare_chat('h>hat warrior lvl 35').startswith('b>'))
        self.party('> pqpqpqpqpqppqpq any', '파티 퀘스트 참가 원해요 (아무 파티나)')
        self.party('I>pq BONus :Iyh 26 @@@@@@@@@@@@@@@@@@@@@②', '파티 퀘스트 보너스 구간 참가 원해요 (26레벨)')

    def test_swap_names(self):
        from kain_maple_translator.chat_patterns import explicit_trade
        out = explicit_trade('T> my Cat Soul for Evil Skull')
        self.assertTrue(out.endswith('교환'), out)
        self.assertNotIn('my ', out)


class Guards(unittest.TestCase):
    def test_hallucinated_symbols(self):
        self.assertEqual(guard_hallucination('O O', '₢ 킹'), 'O O')
        self.assertEqual(guard_hallucination('ing@', '(주)에이치'), 'ing@')
        self.assertEqual(guard_hallucination('J-ng', 'J-ng, 영국'), 'J-ng')

    def test_link_only_megaphone_is_translated(self):
        self.assertTrue(should_translate_body('[Evil Skull]', 0.9))
        self.assertFalse(should_translate_body('[구룡도]', 0.9))


if __name__ == '__main__':
    unittest.main()
