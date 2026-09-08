"""CPU-only audit of saved native/replay bytes; never opens the game or RDC."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parents[2]
evidence=root/'artifacts/rcra-fur-continuation/capture-tools'
out=root/'unreal/fur/recovered/native-ear-audit';out.mkdir(exist_ok=True)
actual=evidence/'fur-raster-replay-wet-shared-0'
native=evidence/'fur-raster-24715'
coverage=np.load(actual/'coverage.npz')
mask=coverage['native'];assert np.array_equal(mask,coverage['actual'])
assert mask.shape==(1080,1920) and mask.sum()==6308
y,x=np.nonzero(mask)
result={'coverage_pixels':int(mask.sum()),'coverage_missing':0,'coverage_extra':0,
        'native_draw_bounds_xyxy':[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],'targets':[]}
manifest=json.loads((native/'report.json').read_text())
specs=[('<u2',4),('u1',4),('<f4',1),('<u4',1),('<u2',2)]
for i,(dtype,channels) in enumerate(specs):
    entry=manifest['after'][i];path=native/entry['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
    expected=np.fromfile(path,dtype=dtype).reshape(1080,1920,channels)
    observed=np.fromfile(actual/f'actual-target{i}.bin',dtype=dtype).reshape(1080,1920,channels)
    exact=int(np.all(expected[mask]==observed[mask],axis=1).sum())
    assert exact==6308
    result['targets'].append({'index':i,'exact_pixels':exact,'native_sha256':entry['sha256']})
entry=manifest['after'][5];path=native/entry['file']
assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
expected=np.fromfile(path,dtype='<f4').reshape(1080,1920,2)[:,:,0]
observed=np.fromfile(actual/'actual-depth.bin',dtype='<f4').reshape(1080,1920)
assert np.array_equal(expected[mask],observed[mask]);result['exact_depth_pixels']=6308

# Decode native TAA output as numerical image data, with explicitly stated
# display transform. This is not a final post-tonemapping game screenshot.
taa=evidence/'taa-apply-resources'
report=json.loads((taa/'report.json').read_text())
entry=next(r for r in report['resources'] if r['register']=='u0')
path=taa/entry['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
packed=np.fromfile(path,dtype='<u4').reshape(entry['height'],entry['width'])
channels=[]
for shift,bits in ((0,6),(11,6),(22,5)):
    word=(packed>>shift)&((1<<(bits+5))-1);exponent=word>>bits;mantissa=word&((1<<bits)-1)
    assert not np.any(exponent==31), 'Nonfinite packed HDR input'
    values=np.where(exponent==0,np.ldexp(mantissa.astype(np.float32),-14-bits),
                    np.ldexp(1+mantissa.astype(np.float32)/(1<<bits),exponent.astype(np.int32)-15))
    channels.append(np.rint(np.clip(values,0,1)**(1/2.2)*255).astype(np.uint8))
Image.fromarray(np.stack(channels,axis=-1)).save(out/'native-taa-display.png')
result['taa_display']={'source_sha256':entry['sha256'],'width':entry['width'],'height':entry['height'],
    'visual_inspection':'Pause/Continue Game menu frame; no usable visible ear. TAA shader agreement on this frame does not validate fur-edge reconstruction.',
    'transform':'R11G11B10_FLOAT decoded, clipped to [0,1], gamma1/2.2; no game tone mapping; not same event as fur draw24715'}
result['superseded_replay']='preview-material-final-0 matches first four targets but not motion; its own report lists only four target comparisons. Use wet-shared-0 for five-target evidence.'
result['limits']='Saved draw match proves this captured view only. Ears are small/back-facing; no registered close-up reference exists in these inspected exports. No proof that the close-up contour is native or a reconstruction defect.'
result['additional_images_inspected']={
    'rift-approved-focus-later.png':'Startup title; no ear',
    'rift-vanilla-focus.png':'Startup title; no ear',
    'replay-character-frames/scene.png':'Severe horizontal corruption; unsuitable reference',
    'replay-character-repeat/scene.png':'Gameplay rear view; small partly obscured ears',
    'hair-event-17544/u0-view.png':'Isolated hair lighting, not final composite; small rear ears'}
(out/'report.json').write_text(json.dumps(result,indent=2))
(out/'index.html').write_text('''<!doctype html><meta charset="utf-8">
<title>Native ear evidence audit</title>
<style>body{background:#171a20;color:#eee;font:17px system-ui;margin:32px;max-width:1200px}img{max-width:100%;background:#000}figure{margin:24px 0}p{line-height:1.55}a{color:#9cf}</style>
<h1>Native ear evidence audit</h1>
<p>The close-up contour remains unresolved. Saved native coverage, all five raster targets (including motion), and depth match the later replay at all 6,308 covered pixels. That draw occupies only 160 × 98 pixels across the rear head: it does not establish close-up parity.</p>
<figure><img src="../../../../artifacts/rcra-fur-continuation/capture-tools/hair-event-17544/u0-view.png"><figcaption>Saved isolated native hair-lighting pass. Small rear ears; not the final composite.</figcaption></figure>
<figure><img src="native-taa-display.png"><figcaption>Decoded native TAA output: a menu frame, with no usable ear reference. Numerical decode, clipping and gamma 1/2.2; not the game's final tone mapping. Agreement on this frame cannot validate the fur contour.</figcaption></figure>
<p>The other inspected exports contain startup titles, corrupted gameplay, or small obscured ears. None supplies a registered close-up comparison. The preferred preview and shipping package are unchanged.</p>
<p><a href="report.json">Verified byte audit and source hashes</a> · <a href="../ear-contours/comparison.html">Earlier preferred comparison</a></p>
''',encoding='utf-8')
print(json.dumps(result,indent=2))
