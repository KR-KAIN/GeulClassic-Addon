"""Regression coverage for 2026-10-24 community glossary expansion."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from kain_maple_translator.expanded_terms import ENTRIES, all_index, exact_label, scroll_label
from kain_maple_translator.glossary import TERMS, rule_translate, expand_for_mt
from kain_maple_translator.translation import Translator

ROOT=Path(__file__).resolve().parents[1]

class CommunityGlossaryV0310(unittest.TestCase):
    def test_all_new_terms_and_aliases_available(self):
        self.assertGreaterEqual(len(ENTRIES), 240)
        self.assertGreaterEqual(sum(1+len(e.aliases) for e in ENTRIES), 375)
        index=all_index()
        for e in ENTRIES:
            with self.subTest(term=e.term):
                self.assertIn(e.term.casefold(), index)
                self.assertIn(e.term.casefold(), {v.casefold() for v in (t.english for t in TERMS)})
                for alias in e.aliases:
                    self.assertIn(alias.casefold(),index)

    def test_weapon_and_armor_scrolls(self):
        pairs={
            'GFA 60%':'장공 60% 주문서',
            'GMA 10%':'장마 10% 주문서',
            '1H Sword ATT':'한손검 공격력 주문서',
            '2H BW ATT':'두손둔기 공격력 주문서',
            'Claw ATT 60%':'아대 공격력 주문서 60%',
            'Wand M.ATT':'완드 마력 주문서',
            'Cape INT 10%':'망토 지력 주문서 10%',
            'Overall DEX 60%':'전신갑옷 민첩 주문서 60%',
            'Helmet DEX 10%':'투구 민첩 주문서 10%',
            'Shield M.ATT':'방패 마력 주문서',
        }
        for en,ko in pairs.items():
            with self.subTest(en=en): self.assertEqual(rule_translate(en,'en-ko'),ko)

    def test_market_context_and_prices(self):
        pairs={
            'B> GFA 60%':'장공 60% 주문서 삽니다',
            'B> WG AW 5k':'노가다 목장갑(노목) 삽니다 (즉시 구매가 5,000 메소)',
            'S> Zhelm C/O 3M FM2 CH5':'자쿰 투구(자투) 팝니다 (현재 최고 제시가 300만 메소) (5채널 자유시장 2번 방)',
            'S> 60% scroll 2m':'60% 주문서 200만 메소에 팝니다',
            'S> GFA 60% 1.5m':'장공 60% 주문서 150만 메소에 팝니다',
            'a/w 10m':'즉시 구매가 1,000만 메소',
            'h/o 10m':'최고 제시가 1,000만 메소',
            'R> kPQ need 2':'커닝 파퀘 2명 모집해요',
        }
        for en,ko in pairs.items():
            with self.subTest(en=en):self.assertEqual(Translator().translate(en,'en-ko'),ko)

    def test_game_specific_and_chat_short_codes(self):
        expected={'WS':'백의 주문서(백줌)','CSS':'순백의 주문서',
                  'AEE':'고급 장비강화 주문서', 'VSS':'보라색 아이젠',
                  'Dexless Sin':'올럭 표도','Lukless Mage':'올인트 법사',
                  'ToT':'시간의 신전','LHC':'사자왕의 성','FoG':'골렘의 숲',
                  'OPQ':'오르비스 파퀘','HPQ':'헤네시스 파퀘',
                  'DC':'접속 끊김(튕김)','R?':'준비됐나요?',
                  'CC12':'12채널로 이동','NGL':'솔직히','GDI':'아 진짜 짜증나'}
        for en,ko in expected.items():
            with self.subTest(en=en):self.assertEqual(rule_translate(en,'en-ko'),ko)

    def test_ambiguity_and_original_english_prose(self):
        self.assertIn('문맥',rule_translate('CS','en-ko'))
        self.assertIn('문맥',rule_translate('BM','en-ko'))
        self.assertIsNone(rule_translate('clean the room','en-ko'))
        self.assertEqual(expand_for_mt('clean the room','en-ko'),'clean the room')
        self.assertIn('glove attack scroll',expand_for_mt('need GFA 60% pls','en-ko'))
        self.assertNotIn('Bowmaster',expand_for_mt('BM','en-ko'))
        self.assertEqual(Translator().translate('Player123: B> GFA 60%','en-ko'),
                         'Player123 : 장공 60% 주문서 삽니다')

    def test_dictionary_export_and_sources(self):
        obj=json.loads((ROOT/'COMMUNITY-TERMS-v0310.json').read_text(encoding='utf8'))
        self.assertEqual(len(obj['entries']),len(ENTRIES))
        self.assertIn('https://dreaminfo.tistory.com/1454',obj['accessible_source_urls'])
        self.assertNotIn('https://arca.live/b/globalmaplestory/112815376',obj['accessible_source_urls'])

if __name__=='__main__': unittest.main()
