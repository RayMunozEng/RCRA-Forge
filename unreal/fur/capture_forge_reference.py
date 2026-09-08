"""Private comparison runner: no exposure curve/bloom; fixed display gamma 2.2."""
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[2]
forge=root/'external/RCRA-Forge'
sys.path.insert(0,str(forge))
os.environ['QT_SCALE_FACTOR']='1'
os.environ['QT_ENABLE_HIGHDPI_SCALING']='0'
import ui.viewport as viewport
# Process-local changes keep the original Forge preview untouched.
old='FragColor = vec4(mapped, 1.0);'
assert old in viewport.COMPOSITE_FRAG
viewport.COMPOSITE_FRAG=viewport.COMPOSITE_FRAG.replace(old,'FragColor = vec4(pow(max(hdr, vec3(0.0)), vec3(1.0/2.2)), 1.0);')
viewport._postprocess_settings=lambda has_lava:(1.0,0.0)
from tools.smoke_fur_viewport import main
sheep='--sheep' in sys.argv
out=root/'unreal/fur'/('sheep-reference' if sheep else 'matched-reference')
mode=sys.argv[1]
assert mode in ('unlit','lit')
sys.argv=[__file__,'--game-root','F:/SteamLibrary/steamapps/common/Ratchet & Clank - Rift Apart',
    '--hashes',str(forge/'hashes.txt'),'--model','0x959F9CE032472D83' if sheep else '0xAA4A5371E9C251F7',
    '--output',str(out/('forge-'+mode+'.png')),'--report',str(out/('forge-'+mode+'.json')),
    '--width','600','--height','600','--yaw','30','--pitch','25',
    '--samples','1','--converge-samples','1','--disable-fur-environment',
    '--disable-fur-contact','--disable-fur-denoise','--preview-light-direction','.6','1','.8']
if mode=='unlit': sys.argv+=['--albedo-unlit-fur']
main()
