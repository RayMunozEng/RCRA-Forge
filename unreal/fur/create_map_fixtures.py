"""Small synthetic linear control maps for the fur authoring diagnostic."""
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parent/'recovered/maps'
root.mkdir(parents=True,exist_ok=True)

def png(name, sample):
    size = 64
    rows = b''.join(b'\0'+bytes(v for x in range(size) for v in sample(x,y)) for y in range(size))
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',size,size,8,6,0,0,0))
    data += chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
    (root/(name+'.png')).write_bytes(data)

png('LengthBands',lambda x,y: ((32 if (y//8)%2 else 255),)*3+(255,))
png('DensityBands',lambda x,y: ((0 if (y//8)%2 else 255),)*3+(255,))
png('GroomDirections',lambda x,y: (230 if y<32 else 25,128,0,255))
png('Black',lambda x,y:(0,0,0,255))
png('White',lambda x,y:(255,255,255,255))
png('SyntheticAlbedo',lambda x,y:(170+(x//8%2)*28,82+(y//8%2)*24,38,255))
png('SyntheticControl',lambda x,y:(128,128,255,176))
png('SyntheticSpecular',lambda x,y:(128,180,0,255))
print(root)
