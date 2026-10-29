"""Optional repair of already-bundled Global Classic potion PNGs only."""
from pathlib import Path
import hashlib,json,os,tempfile,urllib.request

manifest=Path(__file__).resolve().parents[1]/'resources/hunt/potions/manifest.json'
entries=json.loads(manifest.read_text('utf8'))['icons']
root=Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir())/'KAINMapleTranslator/potion-icons'
root.mkdir(parents=True,exist_ok=True)
for item in entries:
    try:
        req=urllib.request.Request(item['source_url'],headers={'User-Agent':'GeulClassic-Potion-Repair/0.4.53'})
        with urllib.request.urlopen(req,timeout=15) as response:blob=response.read(150001)
        if hashlib.sha256(blob).hexdigest()!=item['sha256']:raise ValueError('PNG checksum mismatch')
        (root/item['file']).write_bytes(blob)
        print('OK',item['item_id'],item['name_en'])
    except Exception as exc:print('SKIP',item['item_id'],str(exc)[:90])
print('Restart the tracker after repairing icons. Normal use requires no download.')
