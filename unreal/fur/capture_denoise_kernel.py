from pathlib import Path
import json,unreal
try:
 r=json.loads(unreal.FurViewportProbe.validate_fur_denoise_gpu())
 assert r['invalid_inputs_rejected']
 p=r['pixels'];assert len(p)==12,len(p)
 assert all(abs(a-b)<.0001 for a,b in zip(p[0],[.30859375,.19921875,.099609375,1])),p[0]
 assert all(abs(a-b)<.0003 for a,b in zip(p[2],[.31,.2,.1,1])),p[2]
 assert p[4][0]<.99 and p[4][2]>.01,p[4] # actual cross-edge filtering
 assert p[6][0]>.99 and p[6][2]<.0001,p[6] # foreground depth rejected
 assert p[8][0]>.99 and p[8][2]<.0001,p[8] # non-fur sample excluded
 assert p[9][2]>.99 and p[9][0]<.0001,p[9] # non-fur center preserved
 assert p[10][0]>.99 and p[10][2]<.0001,p[10] # inactive tile suppresses gather
 r['checks']=['native color truncation','non-fur passthrough','directional edge filtering','foreground depth rejection','fur mask exclusion','inactive tiles','invalid input guard']
 r['scope']='Synthetic128x64 GPU buffers only. Live integration is tested separately. No visual/native parity claim.'
 (Path(__file__).parent/'recovered/fur-denoise-kernel.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
 unreal.log('FUR_DENOISE_KERNEL_OK')
finally:
 unreal.SystemLibrary.execute_console_command(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(),'QUIT_EDITOR')
