"""Check visible scene-light/shadow response and report a limited static noise metric."""
import json
from pathlib import Path
import numpy as np
from PIL import Image

root=Path(__file__).resolve().parent
def read(path):
    return np.asarray(Image.open(path).convert('RGB'),dtype=np.float32)
def hf(image):
    gray=image.mean(axis=2)
    residual=4*gray[1:-1,1:-1]-gray[:-2,1:-1]-gray[2:,1:-1]-gray[1:-1,:-2]-gray[1:-1,2:]
    return float(np.sqrt(np.mean(residual**2)))
result={}
for fixture in ('matched-reference','sheep-reference'):
    path=root/fixture
    clean=read(path/'ue-scene-clean.png')
    relit=read(path/'ue-scene-relit.png')
    shadow=read(path/'ue-scene-shadow.png')
    assert clean.shape==relit.shape==shadow.shape==(600,600,3)
    foreground=clean.max(axis=2)>30
    change=float(abs(clean-relit)[foreground].mean())
    darkened=int(((clean.mean(axis=2)-shadow.mean(axis=2)>10)&foreground).sum())
    assert change>3,(fixture,change)
    assert darkened>100,(fixture,darkened)
    result[fixture]={'relighting_mean_rgb8_change':change,'shadow_darkened_pixels':darkened}
ear=(slice(265,310),slice(350,430))
old=read(root/'matched-reference/ue-recovered-key.png')[ear]
new=read(root/'matched-reference/ue-scene-clean.png')[ear]
result['static_ear_high_frequency']={'before_rms':hf(old),'after_rms':hf(new),
    'scope':'Fixed interior ear region; antialiasing also filters texture detail. Not a moving-camera flicker measurement.'}
(root/'recovered/scene-image-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
