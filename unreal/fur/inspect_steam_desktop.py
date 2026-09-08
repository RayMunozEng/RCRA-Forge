"""Read desktop/window ownership for Steam; never switch desktops or send input."""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'external/RCRA-Forge/tools'))
from private_desktop import api, desktop_state, windows
u,k=api()
callback=C.WINFUNCTYPE(W.BOOL,W.LPWSTR,W.LPARAM)
u.EnumDesktopsW.argtypes=[W.HANDLE,callback,W.LPARAM]
u.OpenDesktopW.argtypes=[W.LPCWSTR,W.DWORD,W.BOOL,W.DWORD]
u.OpenDesktopW.restype=W.HANDLE
targets=set(map(int,sys.argv[1:]))
found=[]
def visit(name,unused):
    desk=u.OpenDesktopW(name,0,False,0x41)
    if desk:
        try:
            matches=[w for w in windows(u,desk) if w['pid'] in targets]
            if matches: found.append({'desktop':name,'windows':matches})
        finally: u.CloseDesktop(desk)
    return True
cb=callback(visit)
assert u.EnumDesktopsW(u.GetProcessWindowStation(),cb,0)
print(json.dumps({'state':desktop_state(u,k),'matches':found},indent=2))
