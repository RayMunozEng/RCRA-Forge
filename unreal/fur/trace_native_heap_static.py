"""Read-only retail heap-error and memory-option string cross-reference audit."""
from pathlib import Path
import sys, re, json, hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'artifacts/rcra-fur-continuation/capture-tools'))
from trace_temporal_cbuffer_static import parse_pe,file_to_rva,scan_rip_references,runtime_functions,containing_function
exe=Path(r'F:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart\RiftApart.exe')
data=exe.read_bytes();digest=hashlib.sha256(data).hexdigest()
assert digest=='51299faca61866cf10ea9035a15b8f22600a56557dd5ffc1aad390d5a54e6d82'
base,sections=parse_pe(data);text=next(s for s in sections if s.name=='.text')
strings=[];targets={}
for match in re.finditer(rb'[\x20-\x7e]{6,512}\x00',data):
    value=match.group()[:-1].decode('ascii')
    if 'CreateHeap(&desc' in value or (value.startswith('-') and re.search('memory|heap|pool|budget|stream',value,re.I)):
        rva=file_to_rva(match.start(),sections)
        if rva is not None:
            targets[base+rva]=value
            strings.append(dict(text=value,va=hex(base+rva)))
targets[0x146255F24]='texture heap override parsed value'
refs=scan_rip_references(data,base,text,set(targets));functions=runtime_functions(data,sections)
for ref in refs:
    ref['text']=targets[ref['target_va']]
    bounds=containing_function(ref['instruction_rva'],functions)
    ref['function_va_bounds']=[hex(base+b) for b in bounds] if bounds else None
out=ROOT/'unreal/fur/recovered/native-ear-audit/heap-static.json'
out.write_text(json.dumps(dict(sha256=digest,strings=strings,references=refs,
    limits='Byte-scanned RIP references are candidates pending exact instruction disassembly. Strings alone do not establish supported command-line options or the failed allocation size.'),indent=2))
print(json.dumps(dict(strings=strings,references=refs),indent=2))
