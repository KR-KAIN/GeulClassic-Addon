"""Verify every bundled current-Classic potion PNG before EXE packaging."""
from pathlib import Path
import hashlib
import json


def verify(root=None):
    folder=Path(root or Path(__file__).resolve().parents[1])/'resources/hunt/potions'
    data=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
    expected=set()
    for item in data['icons']:
        filename=item['file']
        if filename!=str(item['item_id'])+'.png':raise RuntimeError('Invalid potion filename')
        blob=(folder/filename).read_bytes()
        if not blob.startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('Invalid PNG: '+filename)
        if len(blob)!=item['size_bytes'] or hashlib.sha256(blob).hexdigest()!=item['sha256']:
            raise RuntimeError('Potion PNG checksum mismatch: '+filename)
        expected.add(filename)
    if len(expected)!=data['coverage']['total_items']:raise RuntimeError('Potion catalogue incomplete')
    permitted=expected|set(data.get('reference_images',{}))
    if {p.name for p in folder.glob('*.png')}!=permitted:raise RuntimeError('Unexpected/missing image in potion bundle')
    digits=folder.parent/'digits'
    glyphs=json.loads((digits/'manifest.json').read_text(encoding='utf8'))['digits']
    if {g['digit'] for g in glyphs}!={str(i) for i in range(10)}:raise RuntimeError('Missing stack-number glyph')
    for glyph in glyphs:
        blob=(digits/glyph['file']).read_bytes()
        if len(blob)!=glyph['bytes'] or hashlib.sha256(blob).hexdigest()!=glyph['sha256']:
            raise RuntimeError('Stack-number glyph checksum mismatch: '+glyph['file'])
    print('PASS:',len(expected),'Global Classic recovery/buff PNGs; total',sum(i['size_bytes'] for i in data['icons']),'bytes')


if __name__=='__main__':verify()
