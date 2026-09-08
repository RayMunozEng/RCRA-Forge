"""Read-only bounded scan of installed config assets for managed memory settings."""
from pathlib import Path
import sys,io,contextlib,json,struct
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'external/RCRA-Forge'))
from core.archive import TocParser, _decompress_block, ARCHIVE_MAGIC_COMPRESSED
out=ROOT/'unreal/fur/recovered/native-ear-audit'
toc=TocParser(r'F:/SteamLibrary/steamapps/common/Ratchet & Clank - Rift Apart/toc')
with contextlib.redirect_stdout(io.StringIO()): toc.parse()
archives={a.index for a in toc.archives if a.filename.replace('\\','/').endswith('/config')}
terms={b'ManagedBuffer':'ManagedBuffer',b'SystemMemory':'SystemMemory',b'ManagedRaytracingBuffer':'ManagedRaytracingBuffer',struct.pack('<I',0xae669203):'ManagedBuffer-hash',struct.pack('<I',0xf0b87e85):'SystemMemory-hash'}
report=dict(archives=[a.filename for a in toc.archives if a.index in archives],scanned=0,bytes=0,matches=[])
# Decode each archive block once instead of re-decoding it for every asset.
for arc in toc.archives:
 if arc.index not in archives: continue
 indices=np.where(toc.entries._sizes['archive']==arc.index)[0]
 entries=[toc.entries[int(i)] for i in indices]
 extent=max(e.offset+e.size for e in entries)
 if extent>64*1024**2: raise RuntimeError('Archive expansion bound reached')
 with open(Path(toc.game_root)/arc.filename,'rb') as f:
  magic=struct.unpack('<I',f.read(4))[0]
  if magic!=ARCHIVE_MAGIC_COMPRESSED:
   f.seek(0); data=f.read(extent)
  else:
   f.seek(12);end=struct.unpack('<I',f.read(4))[0]
   if end>4*1024**2: raise RuntimeError('Block directory bound reached')
   f.seek(32); blocks=[]
   while f.tell()<end: blocks.append(struct.unpack('<IIIIIIBBHI',f.read(32)))
   data=bytearray(extent)
   for real_off,_,comp_off,_,real_size,comp_size,kind,*_ in blocks:
    if real_off>=extent: continue
    if real_size>64*1024**2 or comp_size>64*1024**2: raise RuntimeError('Block bound reached')
    f.seek(comp_off)
    with contextlib.redirect_stdout(io.StringIO()): block=_decompress_block(f.read(comp_size),real_size,kind)
    take=min(len(block),extent-real_off);data[real_off:real_off+take]=block[:take]
 for e in entries:
  raw=(e.header or b'')+data[e.offset:e.offset+e.size]
  report['scanned']+=1;report['bytes']+=len(raw)
  found=[label for t,label in terms.items() if t in raw]
  if found:
   name=f'memory-config-{e.asset_id:016x}.bin';(out/name).write_bytes(raw)
   report['matches'].append(dict(asset_id=f'{e.asset_id:016x}',terms=found,file=name))
(out/'memory-config-scan.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
