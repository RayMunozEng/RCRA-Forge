"""Compare UE GPU samples with DDS texels, including all cube faces and mips."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parent/'recovered'
report=json.loads((root/'environment-sampling/report.json').read_text())
im=np.asarray(Image.open(report['image']).convert('RGB'),dtype=float)
h,w=im.shape[:2]
def sample(col,row):
 x=int((col+.5)*w/6);y=int((row+.5)*h/7)
 return np.median(im[y-5:y+6,x-5:x+6],axis=(0,1))
def display(rgb):return np.clip(np.asarray(rgb),0,1)**(1/2.2)*255
cube=(root/'environment-inputs/StudioCube.dds').read_bytes();offset=148
errors=[]
for face in range(6):
 for mip in range(6):
  side=32>>mip;count=side*side*4
  pixels=np.frombuffer(cube,dtype='<f2',count=count,offset=offset).reshape(side,side,4)
  errors.append(float(abs(sample(face,mip)-display(pixels[0,0,:3].astype(float))).max()))
  offset+=count*2
assert offset==len(cube)
lut=np.frombuffer((root/'environment-inputs/PrivateBRDF.dds').read_bytes(),dtype='<f2',offset=148).reshape(64,64,4).astype(float)
lut_errors=[]
for face in range(6):
 x=(face+.5)/6*64-.5;i=int(np.floor(x));f=x-i
 expected=((lut[31,i]+lut[32,i])*(1-f)+(lut[31,i+1]+lut[32,i+1])*f)*.5
 lut_errors.append(float(abs(sample(face,6)-display(expected[:3])).max()))
result={'maximum_cube_error_rgb8':max(errors),'maximum_brdf_error_rgb8':max(lut_errors),'cube_face_mip_samples':36,'brdf_samples':6}
print(json.dumps(result,indent=2))
assert max(errors)<3,errors
assert max(lut_errors)<3,lut_errors
(root/'environment-sampling-validation.json').write_text(json.dumps(result,indent=2))
