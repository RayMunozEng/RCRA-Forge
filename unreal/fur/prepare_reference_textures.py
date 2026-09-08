"""Decode authored BC mip levels to UE-importable RGBA DDS, without resampling."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import imagecodecs

sheep='--sheep' in sys.argv
root=Path(__file__).resolve().parent/('sheep-reference' if sheep else 'matched-reference')
data=json.loads((root/'inputs.json').read_text())
report={}
for mid,slots in data['textures'].items():
    for role,info in slots.items():
        if role not in ('base_color','albedo','fur_control') and not (mid==('0' if sheep else '2') and role=='specular_color'): continue
        source=(root/info['file']).read_bytes()
        fmt=info['dxgi']
        bcn={71:1,72:1,74:2,75:2,77:3,78:3,98:7,99:7}.get(fmt)
        assert bcn or fmt in (28,29),fmt
        w,h=info['size']
        offset=148
        decoded=[]
        for level in range(info['mips']):
            mw,mh=max(1,w>>level),max(1,h>>level)
            if bcn:
                size=max(1,(mw+3)//4)*max(1,(mh+3)//4)*(8 if bcn==1 else 16)
                raw=imagecodecs.bcn_decode(source[offset:offset+size],format=bcn,shape=(mh,mw,4)).tobytes()
            else:
                size=mw*mh*4
                raw=source[offset:offset+size]
            assert len(raw)==mw*mh*4
            decoded.append(raw)
            offset+=size
        assert offset==len(source),(info['file'],offset,len(source))
        header=[124,0x2100F,h,w,w*4,0,len(decoded)]+[0]*11
        header += [32,4,int.from_bytes(b'DX10','little'),0,0,0,0,0]+[0x401008,0,0,0,0]
        srgb=fmt in (29,72,75,78,99)
        output=b'DDS '+struct.pack('<31I',*header)+struct.pack('<5I',29 if srgb else 28,3,0,1,0)+b''.join(decoded)
        name=Path(info['file']).stem+'-rgba.dds'
        (root/name).write_bytes(output)
        report[info['file']]={'file':name,'mips':len(decoded),'decoder':'imagecodecs '+imagecodecs.__version__,
            'sha256':hashlib.sha256(output).hexdigest(),'mip_sha256':[hashlib.sha256(m).hexdigest() for m in decoded]}
(root/'decoded-textures.json').write_text(json.dumps(report,indent=2))
print('Decoded',len(report),'textures; authored mip dimensions retained.')
