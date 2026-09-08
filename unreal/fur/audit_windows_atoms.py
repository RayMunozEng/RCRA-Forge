"""Count shared Windows atom entries read-only; no clipboard content or mutations."""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
import re
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'external/RCRA-Forge/tools'))
from private_desktop import api,resource_state
u,k=api()
u.GetClipboardFormatNameW.argtypes=[W.UINT,W.LPWSTR,C.c_int]
k.GlobalGetAtomNameW.argtypes=[W.WORD,W.LPWSTR,C.c_int]
buf=C.create_unicode_buffer(512)
counts={'user_atoms':0,'global_atoms':0,'scanned_slots':0x4000}
prefixes=Counter()
patterns=Counter()
markers=Counter()
for atom in range(0xc000,0x10000):
    counts['user_atoms']+=bool(u.GetClipboardFormatNameW(atom,buf,len(buf)))
    if k.GlobalGetAtomNameW(atom,buf,len(buf)):
        counts['global_atoms']+=1
        match=re.match(r'[A-Za-z_]{1,40}',buf.value)
        prefixes[match.group() if match else '(nonalphabetic)']+=1
        # Aggregate names without exporting their per-instance IDs or paths.
        name=buf.value
        for token in ('codex','steam','renderdoc','unreal','qt','chrome','ole','uia','python','powershell','wgl','nvidia','maya','renderman'):
            if token in name.lower(): markers[token]+=1
        if ':\\' in name or '://' in name or '@' in name:
            pattern=re.sub(r'[A-Za-z]:\\.*','<path>',name)
            pattern=re.sub(r'\S+://\S+','<url>',pattern)
            pattern=re.sub(r'[^\s@]+@[^\s@]+','<at-name>',pattern)
            pattern=re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}','<guid>',pattern)
            pattern=re.sub(r'\d+','<n>',pattern)
        else:
            pattern=re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}','<guid>',name)
            pattern=re.sub(r'0x[0-9a-fA-F]+','<hex>',pattern)
            pattern=re.sub(r'\d+','<n>',pattern)
        patterns[pattern[:120]]+=1
counts['global_name_prefix_counts']=prefixes.most_common(10)
counts['global_name_patterns']=patterns.most_common(12)
counts['known_name_markers']=dict(markers)
counts['resources']=resource_state(k,Path(__file__).resolve().parent)
out=Path(__file__).resolve().parent/'recovered/native-ear-audit/windows-atoms.json'
out.write_text(json.dumps(counts,indent=2))
print(json.dumps(counts,indent=2))
