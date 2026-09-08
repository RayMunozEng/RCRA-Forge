"""Preserve exported FBX node values while avoiding the fork's binary container."""
import json
from pathlib import Path
import struct
import zlib
import sys
import numpy as np

root=Path(__file__).resolve().parent/('sheep-reference' if '--sheep' in sys.argv else 'matched-reference')
inputs=json.loads((root/'inputs.json').read_text())
for part in inputs['parts']:
    data=(root/(part['name']+'.fbx')).read_bytes()
    assert struct.unpack_from('<I',data,23)[0]==7400
    def parse(offset):
        end,count,size,n=struct.unpack_from('<IIIB',data,offset)
        if end==0: return None,offset+13
        name=data[offset+13:offset+13+n].decode()
        offset+=13+n
        properties=[]
        for _ in range(count):
            kind=chr(data[offset]); offset+=1
            if kind in 'YCFDIL':
                fmt={'Y':'h','C':'?','F':'f','D':'d','I':'i','L':'q'}[kind]
                value=struct.unpack_from('<'+fmt,data,offset)[0]
                offset+=struct.calcsize(fmt)
            elif kind in 'SR':
                length=struct.unpack_from('<I',data,offset)[0]; offset+=4
                value=data[offset:offset+length]; offset+=length
                if kind=='R':
                    assert name=='FileId',name
                    value='0000000000000000'
                else:
                    value=value.decode()
            else:
                length,encoded,size=struct.unpack_from('<III',data,offset);offset+=12
                payload=data[offset:offset+size];offset+=size
                if encoded: payload=zlib.decompress(payload)
                dtype={'f':'<f4','d':'<f8','i':'<i4','l':'<i8','b':'u1'}[kind]
                value=np.frombuffer(payload,dtype=dtype)
                assert len(value)==length
            properties.append(value)
        children=[]
        while offset<end:
            child,offset=parse(offset)
            if child: children.append(child)
        assert offset==end
        return (name,properties,children),end
    nodes=[];offset=27
    while True:
        node,offset=parse(offset)
        if node is None: break
        nodes.append(node)
    def atom(value):
        if isinstance(value,str): return json.dumps(value)
        if isinstance(value,bool): return str(int(value))
        return repr(value.item() if isinstance(value,np.generic) else value)
    def write(node,level=0):
        name,props,children=node
        indent='\t'*level
        if len(props)==1 and isinstance(props[0],np.ndarray):
            arr=props[0]
            return indent+name+': *'+str(len(arr))+' {\n'+indent+'\ta: '+','.join(atom(x) for x in arr)+'\n'+indent+'}\n'
        line=indent+name+': '+', '.join(atom(p) for p in props)
        if children: line+=' {\n'+''.join(write(c,level+1) for c in children)+indent+'}'
        return line+'\n'
    result='; FBX 7.4.0 project file\n'+''.join(write(n) for n in nodes)
    (root/(part['name']+'-ascii.fbx')).write_text(result,encoding='utf-8')
print('Converted',len(inputs['parts']),'FBX node trees without changing array values.')
