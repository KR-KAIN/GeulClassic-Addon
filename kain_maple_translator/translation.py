"""Offline EN/KO chat translation with Argos-format model archives.

v0.3.5: support real Argos packages where CT2 config.json is optional.
This deliberately does NOT use the argostranslate sentence-boundary detector,
Stanza model downloader, or global Argos package registry at runtime.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import OrderedDict
import os
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path, PurePosixPath

from .glossary import rule_translate, expand_for_mt, normalize_mt_result
from .natural_chat import phrase_override, polish_translation
from .casual_korean import naturalize_free_chat
from .scroll_intelligence import scroll_trade, polish_scroll_result
from .natural_trade import (trade_override, priced_item_list,
                            general_chat_override, polish_meso_units,
                            normalize_maple_market_name)
from .timings import LatencyBook
from .trade_memory import (TradeMemory, protect_values, safe_slot_translation,
                           normalize_chat_input, split_clauses)

LOGGER = logging.getLogger(__name__)
_LATENCY = LatencyBook()
_ENGINE_STATE = {}


class TranslationError(RuntimeError):
    recoverable_translation_failure = True


_LOCK = threading.RLock()
_READY: dict[str, Path] = {}
_ENGINES: dict[str, tuple[object, object, str]] = {}
_PAIRS = {'en-ko': ('en', 'ko'), 'ko-en': ('ko', 'en')}
_INFER_LOCKS = {direction: threading.RLock() for direction in _PAIRS}


class _NeedGeneric(Exception):
    defer_translation = True
    def __init__(self, text, direction):
        self.key = (text, direction)



def _user_data_root() -> Path:
    root = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME')
    if not root:
        try:
            root = str(Path.home() / ('AppData/Local' if os.name == 'nt' else '.local/share'))
        except (RuntimeError, OSError):
            root = str(Path(tempfile.gettempdir()) / 'KAINMapleTranslator-user-data')
    return Path(root) / 'KAINMapleTranslator'


def model_folder() -> Path:
    """Compatibility directory from older versions; not used by the new engine."""
    return _user_data_root() / 'argos-packages'


def direct_model_folder() -> Path:
    return _user_data_root() / 'ct2-chat-models-v034'


def archive_folder() -> Path:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'resources' / 'models'


def configure_offline_environment() -> None:
    # Keep old settings migration/tests safe. The actual CT2 engine below
    # does not load Argos or depend on any of these settings.
    os.environ['ARGOS_PACKAGES_DIR'] = str(model_folder())
    os.environ['ARGOS_CHUNK_TYPE'] = 'DEFAULT'
    os.environ.setdefault('ARGOS_DEVICE_TYPE', 'cpu')
    os.environ.setdefault('ARGOS_COMPUTE_TYPE', 'int8')


def _model_ready(folder: Path) -> bool:
    # CT2's loader accepts older models without a config.json. The weights
    # and tokenizer are mandatory; optional metadata is preserved if present.
    paths = (folder / 'metadata.json', folder / 'sentencepiece.model',
             folder / 'model' / 'model.bin')
    try:
        return (all(path.is_file() for path in paths)
                and (folder / 'sentencepiece.model').stat().st_size > 100
                and (folder / 'model' / 'model.bin').stat().st_size > 100_000)
    except OSError:
        return False


def _unpack_model(archive: Path, dest: Path, src: str, dst: str) -> None:
    """Extract only files required for short-chat inference, atomically.

    Model archives may contain a single top-level directory or be flat.
    Never extract arbitrary relative paths from an untrusted zip archive.
    """
    if not archive.is_file() or archive.stat().st_size < 100_000:
        raise TranslationError(f'오프라인 모델 압축 파일이 없습니다: {archive.name}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _model_ready(dest):
        try:
            metadata = json.loads((dest / 'metadata.json').read_text(encoding='utf-8'))
            if metadata.get('from_code') == src and metadata.get('to_code') == dst:
                return
        except (OSError, ValueError):
            pass

    stage = Path(tempfile.mkdtemp(prefix='.kain-ct2-', dir=str(dest.parent)))
    try:
        with zipfile.ZipFile(archive) as z:
            names = {n.replace('\\', '/') for n in z.namelist()}
            meta_matches = [n for n in names if n == 'metadata.json' or n.endswith('/metadata.json')]
            if len(meta_matches) != 1:
                raise TranslationError(f'{archive.name}: metadata.json 파일 구성이 올바르지 않습니다')
            prefix = meta_matches[0][:-len('metadata.json')]
            def read_inner(relative: str) -> bytes:
                item = prefix + relative
                if item not in names:
                    raise TranslationError(f'{archive.name}: 필수 모델 파일 누락 ({relative})')
                info = z.getinfo(item)
                if info.file_size > 600_000_000:
                    raise TranslationError(f'{archive.name}: 모델 파일 크기가 비정상적입니다')
                return z.read(item)
            metadata = json.loads(read_inner('metadata.json').decode('utf-8'))
            if (metadata.get('from_code'), metadata.get('to_code')) != (src, dst):
                raise TranslationError(f'{archive.name}: 언어쌍 메타데이터 불일치')
            # Some older official Argos EN/KO packages omit model/config.json.
            # CTranslate2's native model loader treats that JSON as optional,
            # so extract it only when present rather than blocking the build.
            wanted = ('metadata.json', 'sentencepiece.model', 'model/model.bin')
            # Some CTranslate2 models additionally ship vocabulary files.
            for name in names:
                if name.startswith(prefix + 'model/') and not name.endswith('/'):
                    rel = name[len(prefix):]
                    parts = PurePosixPath(rel).parts
                    if len(parts) == 2 and parts[0] == 'model' and all(p not in ('.', '..') for p in parts):
                        if rel not in wanted:
                            wanted += (rel,)
            for rel in wanted:
                output = stage.joinpath(*PurePosixPath(rel).parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(read_inner(rel))
        if not _model_ready(stage):
            raise TranslationError(f'{archive.name}: CTranslate2 모델 구조 불완전')
        if dest.exists():
            shutil.rmtree(dest)
        stage.replace(dest)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise TranslationError(f'{archive.name}: 모델 준비 실패: {type(exc).__name__}: {exc}') from exc
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def prepare_models(directions=None) -> None:
    """Validate bundled offline archives; optionally stage only required directions."""
    with _LOCK:
        for direction in (_PAIRS if directions is None else directions):
            src, dst = _PAIRS[direction]
            if direction in _READY and _model_ready(_READY[direction]):
                continue
            archive = archive_folder() / f'translate-{src}_{dst}.argosmodel'
            dest = direct_model_folder() / f'{src}_{dst}'
            _unpack_model(archive, dest, src, dst)
            _READY[direction] = dest


def _engine_for(direction: str):
    with _LOCK:
        if direction in _ENGINES:
            return _ENGINES[direction]
        try:
            import ctranslate2
            import sentencepiece as spm
        except (ImportError, OSError) as exc:
            raise TranslationError(f'CTranslate2/SentencePiece 실행 라이브러리 오류: {exc}') from exc
        folder = _READY[direction]
        try:
            tokenizer = spm.SentencePieceProcessor(model_file=str(folder / 'sentencepiece.model'))
            meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
            prefix = str(meta.get('target_prefix') or '')
            supported = ctranslate2.get_supported_compute_types('cpu')
            compute_type = next((kind for kind in ('int8','int8_float32','float32') if kind in supported),None)
            if compute_type is None:
                raise TranslationError('지원되는 CPU 연산 타입이 없습니다: '+str(sorted(supported)))
            # A corrupt/missing model is a real load error, not an excuse to
            # silently retry FP32. Capability selection happens before load.
            engine = ctranslate2.Translator(str(folder / 'model'), device='cpu',
                compute_type=compute_type, inter_threads=1, intra_threads=2)
            actual = str(getattr(engine, 'compute_type', compute_type))
            _ENGINE_STATE[direction] = {'device': 'cpu', 'requested': compute_type,
                'actual': actual, 'inter_threads': 1, 'intra_threads': 2}
            LOGGER.warning('MT engine %s: %s', direction, _ENGINE_STATE[direction])
        except Exception as exc:
            raise TranslationError(f'{direction} 오프라인 엔진 로딩 실패: {type(exc).__name__}: {exc}') from exc
        _ENGINES[direction] = (engine, tokenizer, prefix)
        return _ENGINES[direction]


def translate_generic_many(texts: list[str], direction: str) -> list[str]:
    if direction not in _PAIRS:
        raise ValueError('Invalid direction')
    if not texts:
        return []
    prepare_models((direction,))
    engine, tokenizer, prefix = _engine_for(direction)
    # Locks are per language, so Korean input no longer blocks incoming EN chat.
    with _INFER_LOCKS[direction]:
        try:
            tokens = [tokenizer.encode(text.strip(), out_type=str) for text in texts]
            if any(not token for token in tokens):
                raise TranslationError('입력 문장을 토큰화하지 못했습니다')
            limit = min(180, max(24, max(map(len, tokens))*3+10))
            kwargs = dict(beam_size=2, max_decoding_length=limit,
                          no_repeat_ngram_size=3, replace_unknowns=False,
                          return_end_token=True, max_batch_size=8)
            if prefix:
                kwargs['target_prefix'] = [[prefix] for _ in texts]
            started = time.perf_counter()
            batch = engine.translate_batch(tokens, **kwargs)
            _LATENCY.observe('mt_batch', (time.perf_counter()-started)*1000)
            if len(batch) != len(texts):
                raise TranslationError('CTranslate2 번역 결과 개수 불일치')
            results = []
            for entry in batch:
                decoded = list(entry.hypotheses[0])
                ended = any(t in ('</s>', '<eos>') for t in decoded)
                if not ended and len(decoded) >= limit:
                    raise TranslationError('번역 출력 길이 제한 도달 · 잘린 결과 대신 원문 보존')
                if '<unk>' in decoded:
                    raise TranslationError('번역에 미확인 토큰 발생 · 원문 보존')
                if prefix and decoded and decoded[0] == prefix:
                    decoded.pop(0)
                decoded = [t for t in decoded if t not in ('</s>', '<eos>', '<pad>')]
                result = tokenizer.decode(decoded).strip()
                if not result:
                    raise TranslationError(f'{direction} 모델이 빈 번역 결과를 반환했습니다')
                results.append(result)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(f'{direction} CTranslate2 추론 오류: {type(exc).__name__}: {exc}') from exc
    return results


def warmup_models(directions=None):
    # Live OCR needs EN->KO immediately. KO->EN is prepared lazily when used.
    prepare_models(directions)
    for direction, sample in (('en-ko','Where is the party?'), ('ko-en','파티는 어디에 있나요?')):
        if directions is not None and direction not in directions:
            continue
        started = time.perf_counter()
        translate_generic_many([sample], direction)
        _ENGINE_STATE[direction]['warmup_ms'] = round((time.perf_counter()-started)*1000, 1)
    return engine_diagnostics()


def engine_diagnostics():
    return {'engines': {k: dict(v) for k,v in _ENGINE_STATE.items()}, **_LATENCY.snapshot()}


def translate_generic(text: str, direction: str) -> str:
    if direction not in _PAIRS:
        raise ValueError('Invalid direction')
    if not text.strip():
        return ''
    return translate_generic_many([text], direction)[0]


class Translator:
    """Existing UI API preserved. Offline engine now uses direct CTranslate2."""
    def __init__(self, engine='argos', libre_url='', libre_key='', *, body_only=False):
        if engine not in ('argos', 'offline', 'ctranslate2'):
            raise TranslationError(f'지원하지 않는 엔진: {engine}')
        self._generic_cache = OrderedDict()
        self.trade_memory = TradeMemory()
        self.body_only=body_only

    def translate(self, text: str, direction: str) -> str:
        return self._translate(text, direction, translate_generic,parse_sender=not self.body_only)

    def translate_fast(self, text: str, direction='en-ko') -> str | None:
        """Evaluate deterministic rules only, without loading/running an AI model."""
        def cached(value, pair):
            key = (value, pair)
            if key in self._generic_cache:
                return self._generic_cache[key]
            raise _NeedGeneric(value, pair)
        try:
            return self._translate(text, direction, cached,parse_sender=not self.body_only)
        except _NeedGeneric:
            return None

    def translate_many(self, texts: list[str], direction: str) -> list[str]:
        # Planning also includes unknown item sub-translations; the callback
        # suspends at a real missing inference rather than guessing a result.
        results = [None]*len(texts)
        unresolved = list(range(len(texts)))
        cache = self._generic_cache
        for _ in range(32):
            requests = OrderedDict()
            remaining = []
            def cached(value, pair):
                key = (value, pair)
                if key in cache:
                    cache.move_to_end(key)
                    return cache[key]
                raise _NeedGeneric(value, pair)
            for index in unresolved:
                try:
                    results[index] = self._translate(texts[index], direction, cached,parse_sender=not self.body_only)
                except _NeedGeneric as need:
                    requests.setdefault(need.key, None)
                    remaining.append(index)
            if not remaining:
                return results
            for pair in dict.fromkeys(key[1] for key in requests):
                keys = [key for key in requests if key[1] == pair]
                values = translate_generic_many([key[0] for key in keys], pair)
                for key, value in zip(keys, values):
                    cache[key] = value
            while len(cache) > 2048:
                cache.popitem(last=False)
            unresolved = remaining
        raise TranslationError('아이템/문장 번역 계획이 너무 복잡합니다 · 원문 확인 필요')

    def _translate(self, text: str, direction: str, generic, *, parse_sender=False) -> str:
        # Repair only explicitly verified OCR misspellings inside an intact
        # bracketed item link, before the trade/price rule and link-integrity
        # check see the source. Never fuzzy-correct unknown player item names.
        if direction == 'en-ko':
            from .ocr_item_aliases import repair_confirmed_item_link
            from .item_link_protection import protect_hangul_links
            text = repair_confirmed_item_link(protect_hangul_links(text))
            # ALL CAPS free chat ('THIS IS PRIVATE PROPERTY'): the slang,
            # glossary and sentence model read normal case far better. Trade
            # and party posts keep their case (S>, KPQ, 50K ...).
            if not re.match(r'\s*(?:\[|[SBTRJIi1$§hd]\s*[>)<:]|[SB]X[A-Z]|WT[SBT]\b|[JjIi1]?[KkLl]?P[QO]\b|LF|SELL|BUY)', text):
                caps = re.sub(r'[^A-Za-z]', '', text)
                if (len(caps) >= 10 and len(text.split()) >= 3 and sum(c.isupper() for c in caps) >= 0.85 * len(caps)
                        and not re.search(r'\d+(?:\.\d+)?\s*[KM]\b|@@', text)):
                    text = text.lower()
                    text = text[:1].upper() + text[1:]
            # R15: drop '@@@' spam/OCR crumbs and fix common OCR misspellings
            # seen in the user's live chat history.
            from .chat_cleanup import prepare_chat
            text = prepare_chat(text)
            # R17: Korean megaphone text misread by the English OCR model
            # ('972¬人πF1子剂O@@@'). Han/kana without any Hangul is not a
            # sentence; sending it to the model failed the whole 8-line batch.
            if (re.search(r'[぀-ヿ㐀-鿿]', text) and not re.search('[가-힣]', text)
                    and len(re.findall(r'[A-Za-z]{3,}', re.sub(r'\[[^\]]*\]', '', text))) < 2):
                return re.sub(r'[@②③④①]{2,}', '', text).strip()
        result=self._translate_impl(text,direction,generic,parse_sender=parse_sender)
        if direction=='en-ko':
            from .chat_cleanup import polish_leftover, keep_item_names
            result=keep_item_names(text,polish_leftover(result))
            from .user_glossary import glossary_leftover
            result=glossary_leftover(text,result)
            from .chat_fixups import guard_hallucination
            result=guard_hallucination(text,result)
            # names replaced after polishing ('Wolbis stars' -> '월비 표창 stars')
            result=re.sub(r'표창\s+stars?\b','표창',result,flags=re.I)
            result=re.sub(r'메소(?:\s+메소)+','메소',result)          # '1만 메소 메소'
            # 'Each' became '개당' only after polishing ('(700 메소 개당)')
            result=re.sub(r'([\d,]+)\s*메소\s*개당',r'개당 \1 메소',result)
            # 'B> scrolls no def' -> '주문서 삽니다 (방어력 주문서 제외)'
            result=re.sub(r'방어력 주문서 제외\s+(삽니다|팝니다)',r'\1 (방어력 주문서 제외)',result)
            result=re.sub(r'(?i)\bsome\s+(?=[가-힣])','',result)           # 'SELLING SOME NX CLOTHES'
            result=re.sub(r'(?<=\S)\s+!+\s+(?=팝니다|삽니다)',' ',result)         # '[요정의 날개] ! 팝니다'
            result=re.sub(r'(?i)\ball\s+(?:your|ur)\s+([가-힣]+)',r'\1 전부',result)   # 'All your junk nx'
            result=re.sub(r'(?i)\bmithril\b(?=\s*[가-힣])','미스릴',result)          # 'mithril 폴암'
            result=re.sub(r'(?<=[가-힣])\s+or\s+(?=\S)',' 또는 ',result)               # '타이거 마스크 or ...'
            result=re.sub(r'\s*거래 걸어주세요 교환$',' 교환해요. 거래 걸어주세요',result)
            result=re.sub(r',\s*·',' ·',result)
            result=re.sub(r'(?i)판\s+(?:okay|ok|fine)\b','판도 가능',result)        # 'Ingot okay'
            result=re.sub(r'(?i)[,\s]*·?\s*(?:and\s+)?more\s+할로윈',', 그 외 할로윈 아이템',result)   # 'and more halloween'
            result=re.sub(r'(?i)\s*·\s*more\b!*',' 등',result)
            result=re.sub(r'(?i)(?<=메소)\s+st(?:ar|a|e)tin[ge]\b','부터',result)       # '15K starting'
            result=re.sub(r'(?i)\s*can\s+swap\s+(.+?)\s+(삽니다|팝니다)$',r' \2 (\1 교환 가능)',result)
            result=re.sub(r'(?<=[가-힣\d])\s+>\s+(?=[가-힣])',', ',result)         # '50만 메소 > 가격 제안'
            # 'B> ALL NX YOU DONT WANT 10K EA' -> '안 쓰는 캐시템 전부 삽니다'
            result=re.sub(r"(?i)\ball\s+([가-힣][가-힣 ]*?)\s+(?=(?:that\s+)?(?:you|u)\s+(?:dont|don'?t|do\s+not)\s+(?:want|need|use)\b)",
                          r'\1 전부 ',result)
            result=re.sub(r"(?i)([가-힣]+)\s+(전부\s+)?(?:that\s+)?(?:you|u)\s+(?:dont|don'?t|do\s+not)\s+(?:want|need|use)\b\s*!*\s*",
                          r'안 쓰는 \1 \2',result)
        if direction=='en-ko':
            from .chat_safety import has_url_or_domain
            if has_url_or_domain(result) and not has_url_or_domain(text):
                result=text
        if direction=='en-ko' and '[' in text:
            from .link_integrity import preserve_link_labels
            result=preserve_link_labels(text,result)
            # Sellers often link an item and type the exact same title next
            # to it. Keep the clickable label once, with all prices/stats.
            result=re.sub(r'(\[([^\[\]\n]+)\])\s*(?:·\s*)?\2(?=\s|[,.·]|$)',r'\1',result)
        return result

    def _translate_impl(self, text: str, direction: str, generic, *, parse_sender=False) -> str:
        # Local opt-in item names: never scrape the item source website.
        from .item_catalog import current_catalog
        item_catalog = current_catalog() if direction == 'en-ko' else None
        def with_items(value: str) -> str:
            if direction != 'en-ko':
                return value
            # User-imported verified EN->KO names take priority.
            from .megaphone_item_translation import localized_item_text
            value=localized_item_text(value)
            # Supplement with public GMS client items ONLY where a paired,
            # ID-verified Korean name exists. Never invent a name for a gap.
            from .classic_item_index import current_index, replace_unverified_item_names
            verified=value
            # Linked names are immutable slots: only verified catalog changes
            # may touch them. Preserve previous plain-name AI support elsewhere.
            parts = re.split(r'(\[[^\[\]\n]+\])', verified)
            for i in range(0,len(parts),2):
                parts[i] = replace_unverified_item_names(parts[i], lambda name: generic(name,'en-ko'))
            return ''.join(parts)
        text = text.strip()
        if not text:
            return ''
        if direction not in _PAIRS:
            raise ValueError('Invalid direction')
        from .core import parse_chat_line
        if direction == 'en-ko' and parse_sender:
            # Incoming worker inputs already contain the message body only.
            # "cc ch20 pls" is a command, not a player named "cc" with a
            # channel badge. Recursive sender parsing requires a real colon.
            parsed = parse_chat_line(text) if any(c in text for c in ':：;；') else None
            if parsed:
                nick, body = parsed
                return f'{nick} : {self._translate(body, direction, generic)}'
        # URL/chat link messages must survive unchanged. A malformed URL
        # translated by a small generic model can turn .gg or /msclassic
        # into made-up Korean and trigger the meso glossary in hostnames.
        if direction == 'en-ko':
            # meso-for-money adverts carry a fake site ('WWW. U4N'); label them
            # before the keep-links-untranslated rule sees the address
            from .chat_fixups import rmt_advert as _rmt
            if _rmt(text) is not None:
                return _rmt(text)
            from .chat_safety import should_keep_untranslated
            if should_keep_untranslated(text):
                return text
            if re.search('[가-힣]',text) and not re.search('[A-Za-z]',re.sub(r'\[[^\]]*\]','',text)):
                return text
            # Bracketed Hangul item labels are game-native text. The MT
            # engine must never translate or phoneticize their contents.
            from .item_link_protection import protect_hangul_links
            text=protect_hangul_links(text)
            text = normalize_chat_input(text)
            from .chat_patterns import (attention_tail, party_intent, emoticon_tail, linked_price,
                                        mixed_trade_parts, trade_tail, explicit_trade, announcement_intent)
            from .chat_cleanup import party_post, recruit_as_buy, offer_post, price_pairs
            party_line=party_post(text) or offer_post(text)
            if party_line is not None:
                return party_line
            from .chat_cleanup import party_split
            # 'J PQ bonus CandyCanez· S> Fame 5k': a trade post after the party
            # post keeps its own case and markers
            party_trade=re.search(r'(?:(?<=\s)|(?<=·))(?:[SB]\s*>|WT[SB]\b)\s*[A-Za-z0-9]',text)
            if party_trade and party_trade.start()>3:
                left=text[:party_trade.start()].rstrip(' ·,')
                if party_split(left) is not None or party_post(left) is not None:
                    return (f'{self._translate(left,direction,generic)} · '
                            f'{self._translate(text[party_trade.start():],direction,generic)}')
            # 'b>scrolls J>bonus~': a party post after the trade post
            party_tail=re.search(r'(?:(?<=\s)|(?<=,))[JjIi1]\s*>\s*(?=(?:[KkLlOo]?[Pp][QqOo]|rush|bonus)\b)',text,re.I)
            if party_tail and party_tail.start()>3 and re.match(r'(?i)\s*(?:[SBT]\s*>|WT[SBT])',text):
                right=text[party_tail.start():]
                if party_split(right) is not None or party_post(right) is not None:
                    return (f'{self._translate(text[:party_tail.start()].rstrip(" ,·"),direction,generic)} · '
                            f'{self._translate(right,direction,generic)}')
            split_party=party_split(text)
            if split_party is not None:
                head,rest=split_party
                rest_ko=self._translate(rest,direction,generic) if re.search(r'[A-Za-z]{2,}',rest) else rest
                # a lone name after the post ('pq? Serath') must not get a particle ('serath의')
                if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_]{2,15}',rest) and re.search('[A-Za-z]',rest) and (
                        rest_ko.lower().startswith(rest.lower()) or re.search(r'\d',rest)):
                    rest_ko=rest                                  # '2016whoadude' is a name, not '2016년'
                return f'{head} · {rest_ko}' if rest_ko.strip() else head
            from .chat_fixups import casual_request as _casual, bare_scroll_price, game_question
            scroll_price=bare_scroll_price(text)
            if scroll_price is not None:
                return scroll_price
            from .chat_fixups import rmt_advert
            advert=rmt_advert(text)
            if advert is not None:
                return advert
            question=game_question(text,lambda s:self._translate(s,direction,generic))
            if question is not None:
                return question
            if re.fullmatch(r'(?i)me|me\s+too|same|ing|always',text.strip(' .!?~@')):
                return _casual(text)
            text=recruit_as_buy(text)
            # 'B> Blue 130 Unagi 400 Red 30 PureWater 600 Ear Dex/Str60%': a
            # consumable price list, before the scroll/stat parsers see the '60%'
            from .chat_cleanup import consumable_prices
            consumables=consumable_prices(text,lambda s:self._translate(s,direction,generic))
            if consumables is not None:
                return consumables
            announcement=announcement_intent(text)
            if announcement is not None:
                return announcement
            # Repeated > is an explicit trading marker, not an item character.
            text=re.sub(r'^(\s*(?:\[[^\]\n]+\]\s*)?[SBT])\s*>{2,}',r'\1>',text,flags=re.I)
            face=emoticon_tail(text)
            if face:
                core,decoration=face
                if re.fullmatch(r'\[[^\]\n]+\]',core):
                    from .megaphone_item_translation import localized_item_text
                    return localized_item_text(core)+' '+decoration
                return self._translate(core,direction,generic)+' '+decoration
            priced_link=linked_price(text)
            if priced_link is not None:
                return priced_link
            decorated=attention_tail(text)
            if decorated:
                core,decoration=decorated
                return self._translate(core,direction,generic)+' '+decoration
            party=party_intent(text)
            if party is not None:
                return party
            mixed=mixed_trade_parts(text)
            if mixed:
                joined=''
                for index,part in enumerate(mixed):
                    either=bool(re.search(r'\s+or\s*$',part,re.I))
                    part=re.sub(r'\s+or\s*$','',part,flags=re.I)
                    joined+=self._translate(part,direction,generic)+(' 또는 ' if either else ' · ')
                return joined.rstrip(' ·').removesuffix(' 또는')
            swap=re.fullmatch(r'T\s*>+\s*([A-Za-z][A-Za-z \'-]{2,40}?)[.!\s]*',text)
            if swap:
                name=with_items(swap.group(1))
                if not re.search(r'[A-Za-z]{2,}',name):
                    return name+' 교환 원해요'
            suffix=trade_tail(text)
            if suffix:
                return self._translate(suffix[0],direction,generic).rstrip(' .')+'. '+suffix[1]
            structured=explicit_trade(text)
            if structured is not None:
                return structured
            # Offer requests belong to the seller's sentence, not the item
            # label. Handle before linked-item and stat-specific parsers.
            offer=re.fullmatch(r'(.+?)\s+leave\s+(?:me\s+)?(?:an?\s+)?offers?[.!]*',text,re.I)
            if offer and re.search(r'(?:[SB]\s*>|\b(?:wts|wtb|selling|buying)\b)',re.sub(r'\[[^\]]*\]','',offer.group(1)),re.I):
                return self._translate(offer.group(1),direction,generic).rstrip(' .')+'. 가격 제안 주세요'
            sale=re.fullmatch(r'(\[[^\]\r\n]+\])?\s*(\d+(?:\.\d+)?\s*[kmb])\s+come\s+(?:and\s+)?buy(?:\s+it)?[.!]*',text,re.I)
            if sale:
                from .natural_trade import _money
                label=with_items(sale.group(1))+' ' if sale.group(1) else ''
                return label+_money(sale.group(2))+'에 팝니다. 사러 오세요'
            linked_bid=re.fullmatch(r'(\[[^\]\r\n]+\])\s*([SB])\s*>\s*((?:(?:a\s*/\s*w|c\s*/\s*o|h\s*/\s*o|res)\s*[:=]?\s*\d+(?:\.\d+)?\s*[kmb]\s*)+)',text,re.I)
            if linked_bid:
                bid=trade_override(linked_bid.group(2)+'> '+linked_bid.group(1)+' '+linked_bid.group(3))
                if bid:return with_items(bid)
            from .natural_trade import equipment_no_slots_override
            gear = equipment_no_slots_override(text)
            if gear is not None:
                return gear
            # Location suffixes are trade metadata, not untranslated English.
            # Remove before other trade interpreters/MT then append the exact
            # channel+market room after translating the listing itself.
            from .natural_trade import split_market_location
            location_parts = split_market_location(text)
            if location_parts is not None:
                base, location = location_parts
                if not base:
                    return location
                # Trade marker or an explicitly recognized SP-reset listing.
                # Avoid stripping locations from unrelated player prose.
                if (re.match(r'^\s*(?:\[[^\]\n]+\]\s*)?(?:[SB]\s*[>＞]|WTS\b|WTB\b|SELLING\b|BUYING\b)',base,re.I)
                        or re.fullmatch(r'(?i)SP\s+resets?\s+\d+(?:\.\d+)?\s*[kmb]',base)):
                    translated_base = self._translate(base,direction,generic)
                    return translated_base.rstrip(' .') + ' (' + location + ')'
            from .megaphone_item_translation import _TRADE_MARKERS, translate_announcement_trade
            markers=list(_TRADE_MARKERS.finditer(text))
            if len(markers)>1 and len({m.group(1).upper() for m in markers})==1:
                multiple=translate_announcement_trade(text)
                if multiple is not None:return with_items(multiple)
            from .trade_stats import translate_stat_trade
            stat_trade=translate_stat_trade(text)
            if stat_trade is not None:
                return with_items(stat_trade)
            remembered = self.trade_memory.translate(text)
            if remembered is not None:
                return remembered
            listing=priced_item_list(text)
            if listing is not None:
                link=re.match(r'^\s*(\[[^\]\r\n]+\])\s*(?=(?:S\s*>|B\s*>|WTS\b|WTB\b))',text,re.I)
                if link:
                    from .megaphone_item_translation import localized_item_text
                    listing=localized_item_text(link.group(1))+' · '+listing
                return with_items(listing)
            # 'B> 60% Scrolls Claw 140k Dagger 135k ...': one price per item
            pairs=price_pairs(text)
            if pairs is not None:
                return with_items(pairs)
            # Separate multi-listing clauses before the broad repeated-S>
            # parser can absorb the next linked item into the first price.
            clauses=split_clauses(text)
            if len(clauses)>1:
                return ' · '.join(self._translate(clause,direction,generic) for clause in clauses)
        from .chat_shorthand import shorthand_translation, expand_shorthand, trade_suffix
        if direction == 'en-ko':
            # R20.3: the game's own status lines ('Your pet is running low on
            # the allotted HP potions.') in the game's words, not the model's
            from .system_lines import system_line
            status = system_line(text)
            if status is not None:
                return status
            shorthand = shorthand_translation(text)
            if shorthand is not None:
                return shorthand
            suffix = trade_suffix(text)
            if suffix is not None:
                base, label = suffix
                return self._translate(base, direction, generic).rstrip(' .')+'. '+label
        # Whole-message conversational shortcuts (including OCR spellings)
        # run before generic MT, but never rewrite market prices or item data.
        from .colloquial import conversational_shortcut, polish_chat_result
        if direction == 'en-ko':
            greeting = conversational_shortcut(text)
            if greeting is not None:
                return normalize_maple_market_name(greeting)
            # Researched chat slang: whole short sentences, then markers such
            # as ngl/lol/smh peeled off and the remaining core translated.
            from .chat_slang import slang_sentence, peel_markers, join_markers
            slang = slang_sentence(text)
            if slang is not None:
                return slang
            # User glossary (2026-10-28): lines made only of known terms.
            from .user_glossary import glossary_sentence
            known = glossary_sentence(text)
            if known is not None:
                return known
            peeled = peel_markers(text)
            if peeled is not None:
                front, core, back = peeled
                return join_markers(front, self._translate(core, direction, generic), back)
        # Keep linked items and repeat-S> announcement segments out of the
        # generic sentence model. Exact item names and stat values must remain
        # stable across the megaphone and regular-chat panes.
        if direction == 'en-ko':
            from .megaphone_item_translation import translate_announcement_trade
            announcement_trade = translate_announcement_trade(text)
            if announcement_trade is not None:
                return with_items(announcement_trade)
        # Established glossary phrases keep their verified interpretation;
        # new pattern rules handle market sentences not covered by the catalog.
        # Complete Classic World scroll listings are parsed before the
        # generic market parser or MT can garble the equipment/stat/rate.
        if direction == 'en-ko':
            reliable_scroll = scroll_trade(text)
            if reliable_scroll:
                return with_items(reliable_scroll)
        if direction == 'ko-en':
            # R19: Korean trade / party posts as Maple chat English
            # ('노가다 목장갑 8공 3작 900만에 팝니다' -> 'S> Work Gloves 8 att 3 slots 9m')
            from .ko_trade import korean_post
            post = korean_post(text, lambda value: generic(value, direction))
            if post:
                return post
        exact = rule_translate(text, direction)
        if exact:
            return with_items(polish_scroll_result(polish_meso_units(exact))) if direction == 'en-ko' else exact
        if direction == 'en-ko':
            item_list = priced_item_list(text)
            if item_list:
                return with_items(polish_scroll_result(polish_meso_units(item_list)))
            trade = trade_override(text)
            if trade:
                return with_items(polish_scroll_result(polish_meso_units(trade)))
            game_chat = general_chat_override(text)
            if game_chat:
                return with_items(polish_scroll_result(normalize_maple_market_name(game_chat)))
        familiar = phrase_override(text, direction)
        if familiar:
            return with_items(normalize_maple_market_name(familiar)) if direction == 'en-ko' else familiar
        clauses = split_clauses(text)
        if len(clauses)>1:
            return ' · '.join(self._translate(clause, direction, generic) for clause in clauses)
        if direction == 'en-ko':
            # R18: whole lines the model garbled in the live sample
            from .chat_fixups import casual_request, item_stat_post
            special = casual_request(text) or item_stat_post(text)
            if special is not None:
                return special
            # '[Ring] S< 700k OBO PM': the link, then the uncertain-direction
            # rule on the rest (the model turned 'S<' into '₢ 킹')
            linked = re.fullmatch(r'(\[[^\[\]\n]+\])\s*([SB]\s*<.+)', text)
            if linked:
                from .megaphone_item_translation import localized_item_text
                rest = re.sub(r'^[SB]\s*<+\s*', '', linked.group(2))
                body = self._translate('S> '+rest, direction, generic)
                body = re.sub(r'\s*팝니다\.?', '', body).strip(' .·')
                body = re.sub(r'^(?:판매|구매)\s*:\s*', '', body)
                return localized_item_text(linked.group(1))+' · '+body+' (거래 방향 확인 필요)'
        from .chat_slang import expand_slang, koreanize_names
        expanded = expand_shorthand(expand_slang(text)) if direction == 'en-ko' else text
        if not re.search(r'[A-Za-z가-힣]',expanded) or re.fullmatch(r'[A-Za-z]{1,2}[.!?]?',expanded):
            return expanded
        if direction == 'en-ko' and (re.fullmatch(r'[A-Za-z0-9]{1,2}\s*[-.>]\s*[A-Za-z]{1,3}[!?.]*',expanded)
                                     or re.fullmatch(r'[A-Za-z0-9]{1,2}(?:\s+[A-Za-z0-9]{1,2})+[!?.]*',expanded)):
            return expanded
        if direction == 'en-ko':
            # an ALL CAPS sentence ('THE FIRST WHO SAYS THE RIGHT NUMBER ...') is
            # read far better by the sentence model in normal case
            letters = re.sub(r'[^A-Za-z]', '', expanded)
            if len(letters) >= 12 and len(expanded.split()) >= 4 and sum(c.isupper() for c in letters) >= 0.8 * len(letters):
                expanded = expanded.lower()
                expanded = expanded[:1].upper() + expanded[1:]
        plan = protect_values(expanded) if direction == 'en-ko' else None
        if plan is not None and plan.slots and all(slot.kind=='number' for slot in plan.slots):
            # Plain levels/counts do not need long placeholder tokens. Keep
            # context intact, accept only an exactly matching digit sequence.
            candidate=generic(expand_for_mt(expanded,direction),direction)
            if re.findall(r'\d+(?:[.,]\d+)*',candidate)==re.findall(r'\d+(?:[.,]\d+)*',expanded):
                result=candidate
            else:
                result=safe_slot_translation(plan,lambda value:generic(expand_for_mt(value,direction),direction))
        elif plan is not None and plan.slots:
            result = safe_slot_translation(plan, lambda value: generic(expand_for_mt(value,direction),direction))
        else:
            prepared = expand_for_mt(expanded, direction)
            result = generic(prepared, direction)
        result = normalize_mt_result(result, direction)
        if direction == 'ko-en':
            # R19: 'About Us' / 'LOGIN JOIN' / '{{if price_varies}}' for short
            # Korean the model does not know: never hand that to the game chat
            from .natural_chat import junk_english, chatify_english
            if junk_english(result):
                return text
            # R20.3: the short forms Maple chat uses ('ty', 'pls', 'brb')
            result = chatify_english(result)
        if direction == 'en-ko':
            result = koreanize_names(result)
        result = polish_translation(text, result, direction)
        return with_items(polish_scroll_result(polish_meso_units(polish_chat_result(text, naturalize_free_chat(text, result))))) if direction == "en-ko" else result

    def compose(self, text: str) -> tuple[str, bool]:
        """KO > EN for the composer: (English, sure). sure is False when the
        sentence model wrote it and its English, turned back into Korean, no
        longer says what the Korean said ("What's New" for '여기는 내자리야');
        the composer then shows it without copying it to the game chat."""
        result = self.translate(text, 'ko-en')
        if not re.search('[가-힣]', text or ''):
            return result, True
        if re.search('[가-힣]', result or ''):
            return result, False          # left untranslated
        from .natural_chat import korean_chat_phrase, faithful_english
        from .ko_trade import korean_post
        try:
            trusted = bool(korean_chat_phrase(text) or korean_post(text))
        except Exception:
            trusted = False
        if trusted:
            return result, True
        return result, faithful_english(text, result, lambda value: translate_generic(value, 'en-ko'))

    def offline_test(self, direction='en-ko') -> str:
        return translate_generic('Where are you going?' if direction == 'en-ko' else '어디로 가세요?', direction)
