"""Private Forge comparison with the same authored cube and horizontal FOV as UE."""
from pathlib import Path
import os,sys,math,time,json,hashlib
import numpy as np
root=Path(__file__).resolve().parents[2];forge=root/'external/RCRA-Forge'
sys.path.insert(0,str(forge))
os.environ['QT_SCALE_FACTOR']='1';os.environ['QT_ENABLE_HIGHDPI_SCALING']='0'
import ui.viewport as vp
import core.asset_loader as loader
reference_camera='--reference-camera' in sys.argv
shell_depth='--shell-depth' in sys.argv
scene_sequence='--scene-sequence' in sys.argv
scene_background='--scene-background' in sys.argv
assert not scene_background or scene_sequence
far_background='--far-background' in sys.argv
if far_background:
 # Isolate zero-depth preview background handling, not a production fix.
 marker='float opaqueDepth = texelFetch(uSceneDepth, pixel, 0).a;'
 assert vp.TEMPORAL_LINEAR_DEPTH_FRAG.count(marker)==1
 vp.TEMPORAL_LINEAR_DEPTH_FRAG=vp.TEMPORAL_LINEAR_DEPTH_FRAG.replace(marker,
  marker+'\n    if (opaqueDepth <= 0.0) opaqueDepth = 100.0;')
geometry=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--geometry=')),'authored')
assert geometry in ('authored','fixed-spacing','uniform-length')
if geometry!='authored':
 # Isolation experiments, never production defaults or claimed native fixes.
 marker,replacement = (
  ('float unboundedDepth = rawDepth / available;', 'float unboundedDepth = rawDepth;')
  if geometry=='fixed-spacing' else
  ('float controlLength = pointWrappedControlLength(aUV);', 'float controlLength = 0.5;'))
 assert vp.FUR_SHELL_VERT_SRC.count(marker)==1
 vp.FUR_SHELL_VERT_SRC=vp.FUR_SHELL_VERT_SRC.replace(marker,replacement)
if shell_depth:
 # Diagnostic only: keep displacement, coverage/discard and depth untouched.
 # Red = base; cyan = slices (0,4); green = [4,8); blue = [8,16);
 # magenta = [16,32]. Lighting still modulates these diagnostic colors.
 marker='vec4(albedo.rgb, occlusion), customViewDepth'
 replacement='vec4(vBaseShell != 0 ? vec3(1,0,0) : (vLayerSlice < 4.0 ? vec3(0,1,1) : (vLayerSlice < 8.0 ? vec3(0,1,0) : (vLayerSlice < 16.0 ? vec3(0,0,1) : vec3(1,0,1)))), occlusion), customViewDepth'
 for source in ('FUR_MATERIAL_FRAG_SRC','FUR_SHELL_FRAG_SRC'):
  shader=getattr(vp,source);assert shader.count(marker)==1
  setattr(vp,source,shader.replace(marker,replacement))
lighting_mode=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--lighting=')),'combined')
assert lighting_mode in ('combined','direct','environment')
if lighting_mode!='combined':
 # Private output isolation: retain coverage, material decode and both response equations.
 target='indirectColor' if lighting_mode=='direct' else 'directColor'
 for shader_name in ('FUR_LIGHTING_FRAG','FUR_SHELL_FRAG_SRC'):
  shader=getattr(vp,shader_name)
  marker=target+' = hairResolveLighting('
  assert marker in shader
  import re
  setattr(vp,shader_name,re.sub(r'\b'+re.escape(marker),target+' = 0.0 * hairResolveLighting(',shader))
probe=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--probe=')),'none')
assert probe in ('none','normal','albedo','response','diffuse')
if probe!='none':
 expressions={'normal':'normal * 0.5 + 0.5','albedo':'albedo.rgb',
  'response':'vec3(float(packedMaterial.w & 255u)/255.0,float(packedMaterial.w >> 8u)/255.0,material.occlusion)',
  'diffuse':'sampleD3DCube(normal,5.0)*0.6'}
 marker='        packedMaterial, packedStrand, albedo, customViewDepth);'
 for name in ('FUR_LIGHTING_FRAG','FUR_SHELL_FRAG_SRC'):
  shader=getattr(vp,name);assert shader.count(marker)==1
  setattr(vp,name,shader.replace(marker,marker+'\n directColor=vec3(0); indirectColor='+expressions[probe]+'; return;'))
from core.cube_texture import CubeMipChain
from core.fur_resources import default_hair_brdf_rg_half
cube_path=root/'unreal/fur/recovered/environment-inputs/StudioCube.dds'
data=cube_path.read_bytes();offset=148;faces=[]
for face in range(6):
 levels=[]
 for mip in range(6):
  n=32>>mip;a=np.frombuffer(data,dtype='<f2',count=n*n*4,offset=offset).reshape(n,n,4)
  levels.append((n,n,a[:,:,:3].copy().tobytes()));offset+=n*n*8
 faces.append(levels)
# Constant faces: UE (x,y,z) -> Forge (x,z,y); no within-face gradients here.
loader.load_fur_environment=lambda textures,toc:(CubeMipChain([faces[i] for i in [0,1,4,5,2,3]],'rgb16f'),default_hair_brdf_rg_half(),(64,64))
old='FragColor = vec4(mapped, 1.0);';assert old in vp.COMPOSITE_FRAG
vp.COMPOSITE_FRAG=vp.COMPOSITE_FRAG.replace(old,'FragColor = vec4(pow(max(hdr, vec3(0.0)), vec3(1.0/2.2)), 1.0);')
vp._postprocess_settings=lambda has_lava:(1.,0.)
vp.GRID_FRAG='#version 330 core\nlayout(location=0) out vec4 FragColor;\nlayout(location=1) out vec4 BrightColor;\nvoid main(){FragColor=vec4(0,0,0,1);BrightColor=vec4(0,0,0,1);}'
for name in ['_perspective','_perspective_reverse_z_zero_to_one']:
 original=getattr(vp,name)
 def projection(fov,aspect,near,far,original=original):
  return original(math.degrees(2*math.atan(math.tan(math.radians(60)/2)/aspect)),aspect,near,far)
 setattr(vp,name,projection)
original_paint=vp.Viewport3D.paintGL
last=[0.]
def paint(self):
 time.sleep(max(0,.1-(time.monotonic()-last[0])))
 try:result=original_paint(self)
 except Exception:
  import traceback
  traceback.print_exc(file=sys.stderr);sys.stderr.flush();raise
 last[0]=time.monotonic();return result
vp.Viewport3D.paintGL=paint
from tools.smoke_fur_viewport import main
post=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--fur-post=')),'none')
assert post in ('none','contact','denoise','both')
sheep='--sheep' in sys.argv;fixture='sheep' if sheep else 'ratchet'
out=root/'unreal/fur/recovered'/('forge-environment-'+fixture+('' if post=='none' else '-'+post)+('-shell-depth' if shell_depth else '')+('' if geometry=='authored' else '-'+geometry)+('-far-background' if far_background else ''))
if probe!='none':out=out.with_name(out.name+'-probe-'+probe)
output_tag=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--output-tag=')),None)
if output_tag:
 import re
 assert re.fullmatch(r'[a-z0-9-]+',output_tag), 'Output tag must be a simple directory name'
 out=out.with_name(output_tag)
out.mkdir(exist_ok=True)
if scene_sequence:
 assert not far_background and geometry=='authored' and not shell_depth
 out=out.with_name(out.name+('-scene' if scene_background else '-empty')+'-sequence');out.mkdir(exist_ok=True)
 # Install before the wrapper, so every sequence render retains the FPS cap.
 vp.Viewport3D.paintGL=original_paint
 from ear_scene_fixture import install
 install(vp,out,scene_background)
 original_paint=vp.Viewport3D.paintGL
 vp.Viewport3D.paintGL=paint
sys.argv=[__file__,'--game-root','F:/SteamLibrary/steamapps/common/Ratchet & Clank - Rift Apart',
 '--hashes',str(forge/'hashes.txt'),'--model','0x959F9CE032472D83' if sheep else '0xAA4A5371E9C251F7',
 '--output',str(out/'environment.png'),'--report',str(out/'report.json'),
 '--width','2191','--height','942','--yaw','150' if reference_camera else '30','--pitch','5' if reference_camera else '25','--samples','1','--converge-samples','32',
 '--disable-fur-contact','--disable-fur-denoise','--preview-light-direction','.6','1','.8']
if post in ('contact','both'):
 sys.argv.remove('--disable-fur-contact');sys.argv.append('--enable-fur-contact')
if post in ('denoise','both'):sys.argv.remove('--disable-fur-denoise')
try:
 main()
except SystemExit as error:
 if error.code not in (None,0):raise
p=out/'report.json';report=json.loads(p.read_text())
if reference_camera:report['published_reference_camera']={'source':'https://blog.playstation.com/tachyon/2021/06/AaronRatchetLighting-scaled.jpg','yaw':150,'pitch':5,'limits':'Orientation candidate only. No registered native pose, camera intrinsics or lighting match; no shader/material adjustment.'}
if scene_sequence:
 report['ear_scene_sequence']={'manifest':str(out/'sequence.json'),'background':'fixed world-space black plane with opaque depth and velocity' if scene_background else 'empty black background','limits':'environment.png is the pre-sequence camera; stock camera/temporal fields describe the final state. sequence.json is authoritative for individual frames. 12 moving plus 12 held frames; no fur deformation.'}
report['temporal_background_diagnostic']={'mode':'far' if far_background else 'zero','depth':100.0 if far_background else 0.0,'limits':'Only temporal opaque/composed depth producer substitutes empty background. No real background geometry, velocity or motion-scatter depth is added; stationary isolation only.'}
report['geometry_diagnostic']={'mode':geometry,'limits':'Diagnostic vertex override only; pixel coverage, lighting and temporal processing retained. Uniform-length also changes curved UV offset and ignores authored zero length; fixed-spacing removes view-dependent rejection. Neither is a native parity fix.'}
report['environment_comparison']={'cube_sha256':hashlib.sha256(data).hexdigest(),'environment_source':'controlled owned studio cube override; embedded private BRDF','background':'black, grid disabled in private process','horizontal_fov':60,'face_order':[0,1,4,5,2,3],'post_mode':post,'lighting_mode':lighting_mode,'probe':probe,'limits':'No native scene probes; different temporal implementations. Constant faces do not test within-face orientation.'}
p.write_text(json.dumps(report,indent=2))
if shell_depth:
 report['shell_depth_diagnostic']={'base':'red','slices_0_to_4':'cyan','slices_4_to_8':'green','slices_8_to_16':'blue','slices_16_to_32':'magenta','limits':'False-color albedo; lighting and temporal averaging remain active. Geometry and original coverage unchanged.'}
 p.write_text(json.dumps(report,indent=2))
