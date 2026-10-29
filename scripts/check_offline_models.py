"""Mandatory actual inference check: two model archives, two language directions."""
from kain_maple_translator.console_io import configure_utf8_console
configure_utf8_console()

import os
import sys
import time
import traceback
from kain_maple_translator.translation import prepare_models, translate_generic, archive_folder, direct_model_folder


def main():
    started = time.monotonic()
    try:
        print('OFFLINE CHECK: CTranslate2 + SentencePiece direct inference', flush=True)
        print('Model archive directory:', archive_folder(), flush=True)
        print('Extracted local model directory:', direct_model_folder(), flush=True)
        print('Runtime network calls: none', flush=True)
        print('STAGE: verify and unpack model files',flush=True)
        prepare_models()
        print('STAGE PASS: local models verified',flush=True)
        for direction, sample in [('en-ko', 'Where is the party?'), ('ko-en', '파티는 어디에 있나요?')]:
            print('STAGE: infer ' + direction,flush=True)
            result = translate_generic(sample, direction)
            print('MODEL TRANSLATION {}: {!r} -> {!r}'.format(direction,sample,result),flush=True)
            if not result.strip() or result.strip() == sample:
                raise RuntimeError(direction+' returned empty or unchanged text')
        print('MODEL TRANSLATION PASS: actual bidirectional inference; elapsed {:.1f}s'.format(time.monotonic()-started),flush=True)
    except BaseException as exc:
        print('MODEL TRANSLATION FAILED: {}: {}'.format(type(exc).__name__, exc),file=sys.stderr,flush=True)
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
