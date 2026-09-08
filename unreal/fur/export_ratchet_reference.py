"""Export the installed Ratchet head for a private matched renderer comparison.

No game execution. Outputs stay outside the distributable plugin.
"""
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FORGE = ROOT/'external/RCRA-Forge'
sys.path.insert(0,str(FORGE))
from core.archive import TocParser
from core.asset_loader import load_asset, load_model_textures
from core.hashes import HashLookup
from core.mesh import mesh_to_numpy
from exporters.fbx_exporter import FbxExporter, FbxNode

SHEEP = '--sheep' in sys.argv
ASSET = 0x959F9CE032472D83 if SHEEP else 0xAA4A5371E9C251F7
OUT = ROOT/'unreal/fur'/('sheep-reference' if SHEEP else 'matched-reference')
OUT.mkdir(parents=True,exist_ok=True)
toc = TocParser('F:/SteamLibrary/steamapps/common/Ratchet & Clank - Rift Apart/toc')
toc.parse()
lookup = HashLookup()
lookup.load(str(FORGE/'hashes.txt'))
entry = toc.find_entry(ASSET)
assert entry
model = load_asset(entry,toc,lookup).model
assert model
textures = load_model_textures(model,entry,toc,lookup)
report = {'asset_id':f'{ASSET:016X}','path':model.source_path,
          'conversion':'Forge meters (x,y,z) -> UE centimeters (100x,100z,100y)',
          'fbx_import':'disable scene/unit conversion; FBX numeric positions precompensate importer Y flip',
          'parts':[],'textures':{},'scope':'Private reference assets; excluded from plugin packages'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

# Preserve authored tangents as FBX layer elements. This local encoder hook
# changes only this export process, never the fork's general exporter.
encode = FbxNode.encode
active_vertices = []
def encode_with_tangents(node,buffer):
    if node.name=='Geometry' and not any(c.name=='LayerElementTangent' for c in node.children):
        n = np.array([(v.nx,v.ny,v.nz) for v in active_vertices])
        t = np.array([(v.tx,v.ty,v.tz) for v in active_vertices])
        b = np.cross(n,t)*np.array([v.tw for v in active_vertices])[:,None]
        layer = next(c for c in node.children if c.name=='Layer')
        for kind,values in [('Tangent',t),('Binormal',b)]:
            element = node.child('LayerElement'+kind,0)
            element.child('Version',101)
            element.child('Name','')
            element.child('MappingInformationType','ByVertice')
            element.child('ReferenceInformationType','Direct')
            element.child(kind+'s',values.flatten().astype(np.float64))
            declaration = layer.child('LayerElement')
            declaration.child('Type','LayerElement'+kind)
            declaration.child('TypedIndex',0)
    return encode(node,buffer)
FbxNode.encode = encode_with_tangents

converted = [dataclasses.replace(v,x=v.x*100,y=-v.z*100,z=v.y*100,
              nx=v.nx,ny=-v.nz,nz=v.ny,tx=v.tx,ty=-v.tz,tz=v.ty) for v in model.vertexes]
for index,part in enumerate(m for m in model.meshes if m.look_index==0 and m.lod_level==0):
    positions,normals,uv,indices = mesh_to_numpy(model,part)
    name = ('SheepPart' if SHEEP else 'RatchetHeadPart')+str(index)
    active_vertices = converted[part.vertex_start:part.vertex_start+part.vertex_count]
    export_model = dataclasses.replace(model,vertexes=converted,meshes=[part],
                    joints=[],joint_positions=[],joint_quaternions=[],joint_scales=[],rcra_weights=[])
    FbxExporter(export_model,name,0).export(str(OUT/(name+'.fbx')))
    ue_positions = positions[:,[0,2,1]]*100
    report['parts'].append({'name':name,'material':part.material_index,'material_name':model.material_names[part.material_index],
        'vertices':len(positions),'triangles':len(indices)//3,
        'bounds_min_cm':ue_positions.min(axis=0).tolist(),'bounds_max_cm':ue_positions.max(axis=0).tolist(),
        'positions_forge_sha256':sha(positions.tobytes()),'uv_sha256':sha(uv.tobytes()),
        'indices_sha256':sha(indices.tobytes()),'fbx_sha256':sha((OUT/(name+'.fbx')).read_bytes())})

for material,slots in textures.items():
    report['textures'][str(material)] = {}
    for role,payload in slots.items():
        if role not in ['albedo','base_color','fur_control','normal','specular_color']:
            continue
        pixels,w,h,label,meta = payload
        mips = meta.get('compressed_mips')
        source_fmt = meta['dxgi_format']
        representation = 'authored compressed mip chain'
        if not mips:
            assert len(pixels)==w*h*4, (role,w,h,len(pixels))
            mips = [(w,h,pixels)]
            # The Forge loader has already decoded this input to RGBA8.
            # Keep that same payload, and explicitly record the lost mip chain.
            fmt = 29 if source_fmt in (29,72,75,78,91,93,99) else 28
            representation = 'Forge decoded RGBA8 mip zero'
        else:
            fmt = source_fmt
        header = [124,0xA1007,h,w,len(mips[0][2]),0,len(mips)]+[0]*11
        header += [32,4,int.from_bytes(b'DX10','little'),0,0,0,0,0]+[0x401008,0,0,0,0]
        data = b'DDS '+struct.pack('<31I',*header)+struct.pack('<5I',fmt,3,0,1,0)
        data += b''.join(m[2] for m in mips)
        name = 'M'+str(material)+'_'+role
        (OUT/(name+'.dds')).write_bytes(data)
        report['textures'][str(material)][role] = {'file':name+'.dds','name':label,
            'size':[w,h],'dxgi':fmt,'source_dxgi':source_fmt,'representation':representation,
            'mips':len(mips),'sha256':sha(data),
            'fur_settings':meta.get('fur_settings'),'fur_layer_count':meta.get('fur_layer_count')}

reference = json.loads((ROOT/'artifacts/rcra-fur-continuation'/('sheep-relight.json' if SHEEP else 'ratchet-relight-default.json')).read_text())
camera = reference['camera']
yaw,pitch = [math.radians(camera[k]) for k in ['yaw','pitch']]
eye = np.array(camera['target'])+camera['distance']*np.array([math.cos(yaw)*math.cos(pitch),math.sin(pitch),math.sin(yaw)*math.cos(pitch)])
report['camera'] = {'forge':camera,'ue_eye_cm':(eye[[0,2,1]]*100).tolist(),
                    'ue_target_cm':(np.array(camera['target'])[[0,2,1]]*100).tolist(),
                    'vertical_fov_degrees':60,'image_size':[600,600]}
(OUT/'inputs.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
