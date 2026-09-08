"""Read bounded RDC thumbnail headers only; no replay or graphics process."""
from pathlib import Path
import hashlib
import io
import json
import struct
import sys
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'artifacts/rcra-fur-continuation/capture-tools'
OUT = ROOT / 'unreal/fur/recovered/native-ear-audit/thumbnails'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SOURCE))
from inspect_rdc_sections import inspect
records = []
panels = []
for path in sorted(SOURCE.glob('riftapart*.rdc')):
    with path.open('rb') as stream:
        magic, version, header_size, program = struct.unpack('<QII16s', stream.read(32))
        assert magic == int.from_bytes(b'RDOC\0\0\0\0', 'little'), path
        width, height, length = struct.unpack('<HHI', stream.read(8))
        assert 0 <= length <= 10 * 1024 * 1024 and 40 + length <= header_size, path
        data = stream.read(length)
        assert len(data) == length
    record = dict(capture=path.name, width=width, height=height, bytes_read=40+length)
    try:
        sections = inspect(path)
        record['section_inspection_bytes_read'] = sections['inspection_bytes_read']
        record['extended_thumbnails'] = [s for s in sections['sections'] if s['type'] == 7]
    except ValueError as error:
        record['section_inspection_error'] = str(error)
    panel = Image.new('RGB', (480, 300), '#20242b')
    ImageDraw.Draw(panel).text((8, 8), path.name, fill='white')
    if data:
        im = Image.open(io.BytesIO(data))
        assert im.width <= 8192 and im.height <= 8192
        im.load()
        record.update(sha256=hashlib.sha256(data).hexdigest(), format=im.format,
                      decoded_size=list(im.size))
        suffix = '.jpg' if im.format == 'JPEG' else '.png'
        (OUT / (path.stem + suffix)).write_bytes(data)
        im.thumbnail((464, 260))
        panel.paste(im.convert('RGB'), (8, 32))
    else:
        ImageDraw.Draw(panel).text((8, 40), 'No embedded thumbnail', fill='white')
    panels.append(panel)
    records.append(record)
sheet = Image.new('RGB', (480*3, 300*((len(panels)+2)//3)), '#20242b')
for i, panel in enumerate(panels):
    sheet.paste(panel, ((i%3)*480, (i//3)*300))
sheet.save(OUT / 'inventory.png')
(OUT / 'report.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps({'captures':len(records),'thumbnail_bytes_read':sum(r['bytes_read'] for r in records),
                  'successful_section_inspection_bytes_read':sum(r.get('section_inspection_bytes_read',0) for r in records),
                  'section_errors':sum('section_inspection_error' in r for r in records),
                  'inventory':str(OUT/'inventory.png')}, indent=2))
