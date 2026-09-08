"""Sample a failed heap descriptor only from an owned inactive game job."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "external/RCRA-Forge/tools"))
from private_desktop import api, check, desktop_state, windows
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--state", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
state = json.loads(args.state.read_text())
if state["status"] != "running" or time.time()-state["updated_unix"] > 10:
    raise RuntimeError("Private job is not live")
user, kernel = api()
user.OpenDesktopW.argtypes = [W.LPCWSTR, W.DWORD, W.BOOL, W.DWORD]
user.OpenDesktopW.restype = W.HANDLE
desktop = check(user.OpenDesktopW(state["desktop"], 0, False, 0x41))
try:
    if desktop_state(user, kernel)["input_desktop"] == state["desktop"]:
        raise RuntimeError("Desktop became active")
    candidates = [w for w in windows(user, desktop) if w["class"] == "GameNxApp"
                  and w["pid"] in state["job_pids"] and w["visible"]]
    if len(candidates) != 1:
        raise RuntimeError("Expected one private game window")
    pid = candidates[0]["pid"]
finally:
    user.CloseDesktop(desktop)
import hashlib
import subprocess
exe=Path(r"F:/SteamLibrary/steamapps/common/Ratchet & Clank - Rift Apart/RiftApart.exe")
if hashlib.file_digest(exe.open('rb'),'sha256').hexdigest() != '51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82':
    raise RuntimeError('Unverified game build')
probe=Path(__file__).parent/'recovered/native-ear-audit/probe_native_heap.exe'
subprocess.run([str(probe), str(pid), str(args.output)],check=True,timeout=20)
print(args.output.read_text())
