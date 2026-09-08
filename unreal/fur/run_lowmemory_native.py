"""Temporary game settings around a guarded private launch; restore on return."""
import json
from pathlib import Path
import subprocess
import sys
import winreg
import argparse
import re

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='lowmemory')
args=parser.parse_args()
if not re.fullmatch(r'[a-z0-9-]+',args.tag): parser.error('Invalid output tag')

root=Path(__file__).resolve().parents[2]
out=root/'unreal/fur/recovered/native-ear-audit'
folder=root/'artifacts/rcra-fur-continuation/capture-tools'
def output(suffix): return out/f'{args.tag}-{suffix}'
if any(output(s).exists() for s in ('settings-backup.json','native-job.json','native.stop')):
    raise RuntimeError('Output tag already used; choose a new tag to preserve evidence')
keyname=r'Software\Insomniac Games\Ratchet & Clank - Rift Apart\Graphics'
changes=dict(Fullscreen=0,ExclusiveFullscreen=0,WindowWidth=1280,WindowHeight=720,
             UserWindowWidth=1280,UserWindowHeight=720,WindowMaximized=0,
             TextureQuality=0,ShadowQuality=0,LevelOfDetail=1,VehicleDetail=0,
             ParticleLighting=0,ScreenSpaceReflections=0,VSync=1,ForceHalfRefreshRate=1)
before={}
with winreg.OpenKey(winreg.HKEY_CURRENT_USER,keyname,0,winreg.KEY_READ) as key:
    for name in changes:
        value,kind=winreg.QueryValueEx(key,name)
        assert kind==winreg.REG_DWORD
        before[name]=value
report=dict(before=before,temporary=changes,restored=False)
output('settings-backup.json').write_text(json.dumps(report,indent=2))
mute=None
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,keyname,0,winreg.KEY_SET_VALUE) as key:
        for name,value in changes.items(): winreg.SetValueEx(key,name,0,winreg.REG_DWORD,value)
    mute=subprocess.Popen([str(folder/'mute_riftapart_audio.exe'),'--seconds','210'],creationflags=subprocess.CREATE_NO_WINDOW)
    command=[sys.executable,str(root/'external/RCRA-Forge/tools/private_desktop.py'),
        '--report',str(output('native-job.json')),'--seconds','180',
        '--stop-file',str(output('native.stop')),'--ui-restrictions','none',
        '--min-physical-gib','8','--min-pagefile-gib','8','--min-disk-gib','2',
        '--max-job-memory-gib','6','--priority','below-normal','--',sys.executable,
        str(folder/'launch_riftapart_settings.py'),'-noStreamline','-nolauncher',
        '-playthrough_no_save','-level','i29','-checkpoint','CHK_MARKETING_PACKART_RATCHET']
    report['runner_exit_code']=subprocess.call(command)
finally:
    if mute and mute.poll() is None:
        mute.terminate();mute.wait(timeout=10)
    preserved=[]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,keyname,0,winreg.KEY_READ|winreg.KEY_SET_VALUE) as key:
        for name,value in before.items():
            current,kind=winreg.QueryValueEx(key,name)
            if current==changes[name] and kind==winreg.REG_DWORD:
                winreg.SetValueEx(key,name,0,kind,value)
            elif current!=value:
                preserved.append(name) # Preserve any intervening user/game adjustment.
        report['restored']=all(winreg.QueryValueEx(key,n)[0]==v for n,v in before.items())
    report['intervening_changes_preserved']=preserved
    output('settings-result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
