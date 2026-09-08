# Fur ear checkpoint - 2026-09-08

Ear contour is NOT fixed. Full dry fur parity is NOT complete.
Workspace: F:/Cloud-Drive_rmunoz1994@gmail.com/Github/gem-shader

Completed signed-facing diagnostic at unreal/fur/recovered/ear-facing-audit.
Four liveTAA2 frames, exit0, peak4.14915GiB. Ear contour remains. Across-mode
ROI difference0.98131 is less than temporal pair differences1.14599/1.14040.
Corrected abs(dot(normalize(N),V)) to signed geometric normal with TwoSidedSign
in both create_scene_fur.py and create_recovered_material.py. This is a native
sampling-rule correction, NOT the ear fix. New materials only; existing
assets are preserved, no automatic migration. No package released.

New lead: checkpoint5 native frame includes ModelStrand skinning, wind,
work queue and indirect arguments immediately after shell draws. Current
Forge mesh parser/shell builder has no such strand geometry implementation.
Ownership/ear contribution NOT established. The earlier shell draw audit
filtered by31/32instances and selected index counts, omitting these indirect
strand candidates. At events24825,24831,24838,24844 action counts are713020,
57596,0,147200 (nonindexed generic count field; not triangle counts).

CPU-only audit_native_strand_shaders.py extracted eight native containers:
four exact saved compute SHA256 identities plus copy-current-to-previous and
three PS_ModelStrandStandard variants. Cbuffer4800bytes has count,tessellation,
clumping,thickness,curl,opacity. Evidence and disassemblies are saved at
unreal/fur/recovered/ear-strand-audit/report.json and *.llvm.txt.

Prepared audit_native_strand_draws.py for five saved-frame events (before plus
four candidate draws), exports shaders,scene-object cbuffer bindings and albedo.
Guard blocked replay BEFORE LAUNCH at0.947GiB available onF:, below2GiB minimum.
No game/replay process launched. All graphics jobs stopped. Limits unchanged.

F: then ran completely out of space during event-sequence.json write. That
file may be empty/partial. Intended EAR_CONTOURS.md/DRY_FUR_COMPLETION.md/root
CHECKPOINT.md append did NOT execute. No deletion/cleanup done. Preserve this
checkpoint onC: until storage is restored. Other active projects may be writing
F:; do not terminate unrelated jobs or delete user files/caches blindly.

NEXT: restore sufficient F: capacity, run bounded saved-frame strand audit
under existing inactive desktop/memory/disk guards, identify exact scene-object
and pixels changed by strand draws. Only then connect this missing pipeline
to the ear or rule it out. Do not present new strand discovery as a proven fix.

## Receiving-computer update - 2026-09-08

The standalone clone is at
`C:/Users/rmuno/Documents/Codex/2026-08-31/i/RCRA-Forge`. This computer does
not have the source machine's F: volume, saved retail capture, imported Ratchet
or sheep assets, or ear-strand audit inputs. No retail or ear claim was inferred
from their absence. Production pre-TAA filter integration continued using a
generated tagged shell-fur fixture; see FUR_FILTER_INTEGRATION.md and
PRODUCTION_FILTER_CHECKPOINT_20260908.md. The original NEXT action above remains
unchanged and must run on the computer containing the saved capture.
