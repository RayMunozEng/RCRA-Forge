"""Keep private fixture materials outside the distributable plugin content."""
import importlib.util
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'plugins/FurAuthoring/Content/Python/create_scene_fur.py'
spec=importlib.util.spec_from_file_location('scene_fur_builder',path)
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
def create(*args,**kwargs):
    kwargs['asset_path']='/Game/FurReference/Materials'
    return builder.create(*args,**kwargs)
