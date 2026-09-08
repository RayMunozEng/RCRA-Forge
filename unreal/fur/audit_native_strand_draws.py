"""Bounded saved-frame audit of native strand draws; no retail process or visible replay output."""
from pathlib import Path
import json,hashlib,struct,time,traceback
import renderdoc as rd
root=Path(r'F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader')
out=root/'unreal/fur/recovered/ear-strand-audit';report={'events':[]};cap=ctrl=None

def save(name,raw):
 data=bytes(raw);(out/name).write_bytes(data);return dict(file=name,size=len(data),sha256=hashlib.sha256(data).hexdigest())
def checkpoint(): (out/'draw-report.json').write_text(json.dumps(report,indent=2))
try:
 cap=rd.OpenCaptureFile();status=cap.OpenFile(str(root/'artifacts/rcra-fur-continuation/capture-tools/riftapart-checkpoint_capture_5.rdc'),'',None)
 assert status==rd.ResultCode.Succeeded,str(status)
 status,ctrl=cap.OpenCapture(rd.ReplayOptions(),None);assert status==rd.ResultCode.Succeeded,str(status)
 names={r.resourceId:r.name for r in ctrl.GetResources()};textures={r.resourceId:r for r in ctrl.GetTextures()}
 for event in (24727,24825,24831,24838,24844):
  ctrl.SetFrameEvent(event,True);pipe=ctrl.GetPipelineState();row=dict(event=event,stages=[]);report['events'].append(row)
  if event!=24727:
   for stage in (rd.ShaderStage.Vertex,rd.ShaderStage.Geometry,rd.ShaderStage.Pixel):
    refl=pipe.GetShaderReflection(stage)
    if not refl:continue
    s=dict(stage=str(stage),entry=refl.entryPoint,sha256=hashlib.sha256(bytes(refl.rawBytes)).hexdigest(),buffers=[]);row['stages'].append(s)
    for index,block in enumerate(refl.constantBlocks):
     if block.name!='ModelStrandCBuffer':continue
     d=pipe.GetConstantBlock(stage,index,0).descriptor
     raw=bytes(ctrl.GetBufferData(d.resource,d.byteOffset,block.byteSize))
     s['buffers'].append(dict(name=block.name,resource=str(d.resource),offset=d.byteOffset,scene_object_gpu=struct.unpack_from('<I',raw,28)[0],strand_count=struct.unpack_from('<I',raw,60)[0],**save(str(event)+'-'+str(stage).split('.')[-1]+'-cb.bin',raw)))
  targets=pipe.GetOutputTargets()
  if len(targets)>1:
   d=targets[1];t=textures[d.resource]
   assert t.width*t.height<=4096*4096
   row['albedo']=dict(resource=str(d.resource),name=names.get(d.resource),width=t.width,height=t.height,format=t.format.Name(),**save(str(event)+'-albedo.bin',ctrl.GetTextureData(d.resource,rd.Subresource())))
  checkpoint();time.sleep(.15)
 report['completed']=True
except Exception:report.update(completed=False,error=traceback.format_exc())
finally:
 if ctrl:ctrl.Shutdown()
 if cap:cap.Shutdown()
 checkpoint()
raise SystemExit()
