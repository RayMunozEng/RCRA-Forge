"""Write small owned environment fixtures and a private recovered BRDF input."""
from pathlib import Path
import struct,sys,json,hashlib
import numpy as np
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]/'external/RCRA-Forge'))
from core.fur_resources import default_hair_brdf_rg_half
out=root/'recovered/environment-inputs';out.mkdir(exist_ok=True)
def dds(path,faces):
    n=faces[0][0].shape[0];count=len(faces[0]);cube=len(faces)==6
    header=[124,0x2100F,n,n,n*8,0,count]+[0]*11
    header += [32,4,int.from_bytes(b'DX10','little'),0,0,0,0,0]
    header += [0x401008 if count>1 else 0x1000,0xfe00 if cube else 0,0,0,0]
    data=b'DDS '+struct.pack('<31I',*header)+struct.pack('<5I',10,3,4 if cube else 0,1,0)
    data+=b''.join(np.asarray(m,dtype='<f2').tobytes() for f in faces for m in f)
    path.write_bytes(data)
colors=np.array([[.45,.36,.27],[.12,.2,.34],[.25,.3,.4],[.13,.12,.11],[.65,.62,.55],[.04,.035,.03]])
faces=[]
for c in colors:
    face=[]
    for mip in range(6):
        value=c*(1-mip/10)+colors.mean(axis=0)*(mip/10)
        a=np.ones((32>>mip,32>>mip,4));a[:,:,:3]=value
        face.append(a)
    faces.append(face)
dds(out/'StudioCube.dds',faces)
brdf=np.ones((64,64,4),dtype=np.float16)
brdf[:,:,:2]=np.frombuffer(default_hair_brdf_rg_half(),dtype='<f2').reshape(64,64,2)
brdf[:,:,2]=0
dds(out/'PrivateBRDF.dds',[[brdf]])
(out/'provenance.json').write_text(json.dumps({'cube':'Owned six-face synthetic studio test, UE axes. Mips are controlled blends, not a physically convolved HDRI.','brdf':'Private recovered default RG LUT from Forge fur_resources; never packaged.','files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.dds')}},indent=2))
print(out)
