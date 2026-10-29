"""Turn the user's glossary workbook into kain_maple_translator/user_glossary_data.py.

Usage: python scripts/import_user_glossary.py [workbook.xlsx]
Reads the first sheet (columns: 분류, 약어·줄임말, 영어 원형, 한국어 뜻, 구분, 주의).
No openpyxl needed: the workbook XML is read directly.
"""
from __future__ import annotations
import pprint, re, sys, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def sheets(path):
    z = zipfile.ZipFile(path)
    strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            strings.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    book = ET.fromstring(z.read('xl/workbook.xml'))
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    out = {}
    for sheet in book.find('m:sheets', NS):
        target = rels[sheet.get('{%s}id' % NS['r'])].lstrip('/')
        target = target if target.startswith('xl/') else 'xl/' + target
        rows = []
        for row in ET.fromstring(z.read(target)).iter('{%s}row' % NS['m']):
            cells = {}
            for c in row.findall('m:c', NS):
                col = re.match(r'[A-Z]+', c.get('r')).group()
                v = c.find('m:v', NS)
                if c.get('t') == 's' and v is not None:
                    cells[col] = strings[int(v.text)]
                elif c.get('t') == 'inlineStr':
                    cells[col] = ''.join(x.text or '' for x in c.iter('{%s}t' % NS['m']))
                elif v is not None:
                    cells[col] = v.text
            rows.append(cells)
        out[sheet.get('name')] = rows
    return out


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'resources' / 'glossary' / 'user-glossary.xlsx'
    book = sheets(src)
    first = next(iter(book.values()))
    entries = []
    started = False
    for r in first:
        if r.get('A') == '분류':
            started = True
            continue
        if not started or not r.get('B') or not r.get('D'):
            continue
        forms = [f.strip() for f in re.split(r'\s+/\s+', r['B']) if f.strip()]
        entries.append((r.get('A', '').strip(), tuple(forms), (r.get('C') or '').strip(),
                        r['D'].strip(), (r.get('E') or '').strip(), (r.get('F') or '').strip()))
    dest = ROOT / 'kain_maple_translator' / 'user_glossary_data.py'
    dest.write_text('"""Generated from the user glossary workbook by scripts/import_user_glossary.py.\n\n'
                    'Rows: (분류, 표기들, 영어 원형, 한국어 뜻, 구분, 주의). Do not edit by hand."""\n'
                    'SOURCE = ' + repr(src.name) + '\nENTRIES = ' + pprint.pformat(entries, width=110) + '\n',
                    encoding='utf-8')
    print(f'{len(entries)} entries -> {dest}')


if __name__ == '__main__':
    main()
