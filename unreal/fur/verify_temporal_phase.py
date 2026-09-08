"""Regression: integer hash offsets freeze; fractional reference phases must vary."""
import ast
import json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=root/'external/RCRA-Forge/ui/viewport.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_halton')
scope={}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),scope)
values=[int(f'{((i&31)+1):032b}'[::-1],2)*2**-32 for i in range(32)]
assert values==[scope['_halton'](i+1,2) for i in range(32)]
old=[((100.125+(i+.5))%1)*.2 for i in range(8)]
new=[((10+i+(100.125+values[i])%1)*.2)%1 for i in range(32)]
assert len(set(old))==1
assert len(set(round(v,7) for v in new))==32
report={'halton_32_exact_match':True,'old_integer_sequence_unique_values':len(set(old)),
    'new_phase_unique_values':32,'samples':values}
(root/'unreal/fur/matched-reference/temporal-regression.json').write_text(json.dumps(report,indent=2))
print('Temporal phase regression passed against the Forge Halton sequence.')
