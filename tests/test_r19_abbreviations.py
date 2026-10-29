"""R19 audit: game-only abbreviations and short chat forms (user glossary)."""
import unittest

from kain_maple_translator.chat_cleanup import party_post, polish_leftover, prepare_chat
from kain_maple_translator.chat_fixups import game_question
from kain_maple_translator.user_glossary import glossary_leftover, glossary_sentence


class GlossaryLines(unittest.TestCase):
    def check(self, text, expected):
        self.assertEqual(glossary_sentence(text), expected, text)

    def test_skills_and_builds(self):
        self.check('need SB pls', 'SB(슬래시 블러스트·세비지 블로우) 필요해요')
        self.check('TP', '텔레포트')
        self.check('need mw please', '메이플 용사 필요해요')
        self.check('Sindit', '표도(신딧) 빌드')
        self.check('pure luk sin', '올럭 어쌔신')
        self.check('dexless sin', '덱스리스 어쌔신')
        self.check('im a Fizard', '저 불 위자드예요')

    def test_party_and_places(self):
        self.check('LF HB pls', '하이퍼 바디 구해요')
        self.check('LF Sindit for party', '표도(신딧) 빌드 파티원 구해요')
        self.check('lf ht party need bucc', '혼테일 파티 구해요, 바이퍼 필요해요')
        self.check('need sin for HT', '혼테일 갈 어쌔신 필요해요')
        self.check('going to Vic', '빅토리아 아일랜드 가는 중이에요')
        self.check('LF MM party', 'MM(머쉬맘·신궁) 파티 구해요')

    def test_chat(self):
        self.check('carry me pls', '캐리해 주세요')
        self.check('gtg ty all', '이제 가야 해요 모두 고마워요')
        self.check('im ks free', '스틸 안 해요')
        self.check('mule lvl 30', '부캐 레벨 30')
        self.check('need Buff pls', '버프 필요해요, 부탁해요')
        self.check('srs?', '진심이에요?')
        self.check('cc pls ks', '스틸이에요, 채널 바꿔 주세요')

    def test_job_advancement_and_congrats(self):
        self.check('1st', '1차 전직')
        self.check('4th job', '4차 전직')
        self.check('gz on 2nd job!', '2차 전직 축하해요!')
        self.check('grats on 30', '30레벨 축하해요')
        self.check('im 2nd job now', '저 이제 2차 전직이에요')
        self.check('im a sin', '저 어쌔신이에요')
        self.check('LF1M', '1명 구해요')
        self.check('AW', '즉결가')

    def test_no_double_annotation(self):
        out = glossary_leftover('need SB pls', 'SB(슬래시 블러스트·세비지 블로우) 필요해요')
        self.assertEqual(out.count('('), 1)
        # 'G I FA 60%' (OCR of GFA) is a scroll, not Final Attack
        self.assertEqual(glossary_leftover('4x G I FA 60% 1m', '4x G I FA 60% 교환'), '4x G I FA 60% 교환')
        # lower-case ordinary words are never read as abbreviations
        self.assertEqual(glossary_leftover('i saw sw today', 'sw 봤어요'), 'sw 봤어요')


class GameQuestions(unittest.TestCase):
    def test_questions(self):
        self.assertEqual(game_question('anyone selling hp pots?'), 'HP 물약 파시는 분 있나요?')
        self.assertEqual(game_question('anyone buying fame?'), '인기도 사시는 분 있나요?')
        self.assertEqual(game_question('any cleric for hb?'), '하이퍼 바디 해 줄 클레릭 있나요?')
        self.assertEqual(game_question('ign is MapleKnight'), '제 닉네임은 MapleKnight이에요')
        self.assertEqual(game_question('pm me ur ign'), '닉네임 귓말로 알려 주세요')
        self.assertEqual(game_question('sell me se?'), '샤프 아이즈 파실래요?')
        self.assertEqual(game_question('anyone at nath?'), '엘나스에 계신 분 있나요?')
        self.assertEqual(game_question('farming for dsg'), '다크 스톤 골렘 사냥 중이에요')
        self.assertEqual(game_question('need door to fm'), '자유시장 가는 미스틱 도어 필요해요')
        self.assertEqual(game_question('leech at ulu 1 per hour'), '울루 1 쩔')
        self.assertIsNone(game_question('hello how are you'))


class TradeWords(unittest.TestCase):
    def test_price_labels_without_slash(self):
        self.assertEqual(polish_leftover('노가다 목장갑 co 5m bo 8m 팝니다'),
                         '노가다 목장갑 현재가 500만 메소 즉시 구매가 800만 메소 팝니다')
        self.assertIn('최저가', polish_leftover('망토 res 3m 팝니다'))

    def test_state_and_items(self):
        out = polish_leftover('노가다 목장갑 godly 팝니다')
        self.assertIn('옵 좋은', out)
        self.assertIn('망한 작', polish_leftover('모자 bricked 팝니다'))
        self.assertIn('영구 캐시템', polish_leftover('perm nx 1:10 삽니다'))
        self.assertIn('업그레이드 가능 3회', polish_leftover('목장갑 8 공격력 3 slots 팝니다'))
        self.assertNotIn('업그레이드', polish_leftover('30 slot ring 팝니다'))

    def test_million_words(self):
        self.assertIn('10m', prepare_chat('S> 10 mil'))

    def test_more_pq_names(self):
        self.assertEqual(party_post('lfm hpq 2 more'), '헤네 파퀘 2명 구해요')
        self.assertEqual(party_post('LF1M KPQ 2/4'), '커닝 파퀘 1명 구해요 (현재 2/4)')
        self.assertEqual(party_post('J> OPQ'), '오르비스 파퀘 참가 원해요')


class LiveChatR19(unittest.TestCase):
    """Lines repeated in the rebuilt app's own chat history."""

    def test_consumable_price_list(self):
        from kain_maple_translator.chat_cleanup import consumable_prices
        clean = prepare_chat('B< UNAG1IS 500 @@@@ WHITE POTS 250@ ORANGE POTS 125 PURE WATER 700 @12')
        self.assertEqual(consumable_prices(clean), '장어구이 500, 하얀 포션 250, 주황 포션 125, 맑은 물 700 삽니다')
        self.assertIsNone(consumable_prices('S> Work Gloves 500 Claw 300'))

    def test_spam_crumbs_and_mash(self):
        self.assertEqual(prepare_chat('B> pet speed 60% @2@@2Q@@2@ @QQ@C2 @@@2Q Q0 Q@@@@@@@@@②@@@②'),
                         'B> pet speed 60%')
        self.assertEqual(prepare_chat('B> pet speed 60% @G@QGGQ@Φ@ @Q@@C2 @@@@@ @0 ②②②@@@②@@'), 'B> pet speed 60%')
        self.assertNotIn('sd', prepare_chat('B>ELIXIR 500 @@@@asdasd'))
        self.assertEqual(prepare_chat('email me a@b.com'), 'email me a@b.com')

    def test_ocr_markers_and_words(self):
        self.assertTrue(prepare_chat('§> Pure Water 700 each').startswith('S> '))
        self.assertIn('dex 10%', prepare_chat('S>Overall dey 10% offer'))
        self.assertIn('B> Gloves Magic attack 60% 180k each', prepare_chat('Buy Gloves Magic Attac 60% at 180k each'))
        self.assertIn('White pot', prepare_chat('B> Pots White -- Orange'))

    def test_party_lines(self):
        from kain_maple_translator.chat_fixups import casual_request
        self.assertEqual(casual_request('leave pt rondog'), 'rondog, 파티에서 나가 주세요')
        self.assertEqual(casual_request('RONDOG YOURE IN PARTY'), 'RONDOG, 파티에 들어왔어요')
        # 'v30+' is level 30 and up (the '+' after a level form counts)
        self.assertEqual(party_post(prepare_chat('R>v30+ RUSH RUsH RusH@@@@@@@@@@@')),
                         '파티 퀘스트 연속 진행 모집해요 (30레벨 이상)')
        self.assertEqual(party_post(prepare_chat('J>PQ ANY v 26 @@@@@@@@@@@@6@02@c@Φ@@@@@e')),
                         '파티 퀘스트 참가 원해요 (26레벨, 아무 파티나)')

    def test_final_sample(self):
        from kain_maple_translator.chat_fixups import casual_request
        self.assertEqual(prepare_chat('B > Ice Wand !@!@l@!@'), 'B > Ice Wand')
        self.assertEqual(party_post(prepare_chat('R> 2 People 30+ BoNUs@@@@@@@@@@@')),
                         '파티 퀘스트 보너스 구간 2명 모집해요 (30레벨 이상)')
        self.assertEqual(party_post('jpq bonnus'), '파티 퀘스트 보너스 구간 참가 원해요')
        self.assertEqual(party_post('need 2 rush'), '파티 퀘스트 연속 진행 2명 구해요')
        self.assertEqual(casual_request('trade fame anyone?'), '맞인기도 하실 분 있나요?')
        self.assertEqual(casual_request('sent inv again'), '초대 다시 보냈어요')
        self.assertEqual(casual_request('zaubi me'), 'zaubi, 저요')
        self.assertTrue(prepare_chat('Tradind Male dark suit for Female Dark suit').startswith('T> '))
        self.assertEqual(prepare_chat('B> EARRING INT 60% Bunzai leFrog').lower(), 'b> earring int 60% bunzai')
        self.assertNotIn('Fro', prepare_chat('B< Korean fan. Pm price and statseFroq'))
        self.assertNotIn('www', prepare_chat('B>Pure Water 700 wwwwwwwww'))
        self.assertNotIn('22', prepare_chat('BUYING PAN LID! iNT@@@@@22 22222@@@@@@@@@'))
        self.assertIn('frog', prepare_chat('I sent you a frog'))

    def test_corpus_audit_fixes(self):
        """The user's own 2,000 latest chat lines, re-read with this build."""
        from kain_maple_translator.chat_cleanup import consumable_prices, party_split
        from kain_maple_translator.chat_fixups import casual_request, rmt_advert
        clean = prepare_chat('R> Rlue Pots 130 Inaai 40n Red Pots 30 PureWater 60r')
        from kain_maple_translator.chat_cleanup import recruit_as_buy
        self.assertEqual(consumable_prices(recruit_as_buy(clean)), '파란 포션 130, 장어구이 400, 빨간 포션 30, 맑은 물 600 삽니다')
        self.assertIn('S> LV', prepare_chat('B > Thief HAT @@@@@ $ > LVL 20 DAGGE R PANTS AND SHOE'))
        self.assertIn('DAGGER', prepare_chat('S > LV 20 DAGGE R PANTS'))
        self.assertIn('FAME', prepare_chat('S>FAMF 5K!!'))
        self.assertTrue(prepare_chat('b< scroll 60 %').startswith('B> scroll 60%'))
        self.assertTrue(prepare_chat('BGFA 60% 800k').startswith('B> GFA'))
        self.assertTrue(prepare_chat('Selling White Label 480k').startswith('S> '))
        self.assertNotIn('%#', prepare_chat('B> IRON 250 EA +&+&%#*&!%&+!#%b+1#&*(%^#@!&+^%#&!*^@%!'))
        self.assertEqual(party_post('J> RUSH PQ BE GOOD'), '파티 퀘스트 연속 진행 참가 원해요')
        self.assertEqual(party_split('J> RUSH PQ FinFet u funny'), ('파티 퀘스트 연속 진행 참가 원해요', 'finfet funny'))
        self.assertEqual(party_post(prepare_chat('J>pq @@@@@ we are 2 on discord')),
                         '파티 퀘스트 참가 원해요 (현재 2명, 디스코드)')
        self.assertEqual(party_post(prepare_chat('NPO BONUS ②@@@Q@@Q@@@@@@CO')), '파티 퀘스트 보너스 구간 참가 원해요')
        self.assertEqual(party_post('R< Bonus PQ'), '파티 퀘스트 보너스 구간 모집해요')
        self.assertEqual(casual_request('LETS GOOO'), '가자!')
        self.assertEqual(casual_request('how manv?'.replace('manv', 'many')), '몇 개요?')
        self.assertEqual(casual_request('add nunzik'), 'nunzik 친구 추가해 주세요')
        self.assertEqual(casual_request('DeathDealer<<Spot stealer'), 'DeathDealer 자리 도둑이에요')
        self.assertEqual(rmt_advert('WWW. U4N. (0 /TW->Mesos Hotsale.Lowest Price 100K only $4'), '[메소 현금 거래 광고]')
        self.assertIsNone(rmt_advert('S> White Label 450k'))
        self.assertEqual(polish_leftover('하얀 포션 삽니다 · 장어구이 · 순수한 물 S 아니 INDIANS!!'),
                         '하얀 포션 삽니다 · 장어구이 · 맑은 물 인도인 사절!!')
        self.assertEqual(polish_leftover('펫 이동속도 중급 주문서 3만 메소. 귓말 주세요 삽니다'),
                         '펫 이동속도 중급 주문서 3만 메소. 삽니다. 귓말 주세요')

    def test_polish(self):
        self.assertEqual(polish_leftover('장비 for F Hunter tv 30 삽니다'), '여자 헌터 30레벨용 장비 삽니다')
        self.assertEqual(polish_leftover('BLUE 칼륨 150 삽니다'), '파란 포션 150 삽니다')
        self.assertEqual(polish_leftover('[귀신 가면] 3만 메소 ea(3) 팝니다'), '[귀신 가면] 개당 3만 메소(3) 팝니다')
        self.assertEqual(polish_leftover('구매 1 의 의 18만 메소 각 각 각 삽니다').count('각'), 1)
        self.assertEqual(polish_leftover('물약 · 전사의 물약 - - - - 삽니다'), '물약 · 전사의 물약 삽니다')


if __name__ == '__main__':
    unittest.main()
