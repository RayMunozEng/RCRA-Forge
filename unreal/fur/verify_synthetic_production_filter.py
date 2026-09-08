"""Verify the repository-owned production-filter smoke capture."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent
capture = root / 'recovered/fur-denoise-production-synthetic'
report = json.loads((capture / 'report.json').read_text(encoding='utf-8'))
job = json.loads((root / 'recovered/fur-denoise-production-synthetic-job.json').read_text(encoding='utf-8'))
log = (root / 'recovered/fur-denoise-production-synthetic.log').read_text(errors='replace')

frames = report['frames']
assert report['status'] == 'complete'
assert [row['label'] for row in frames] == ['off-a', 'off-b', 'on-a', 'on-b']
assert [row['production_filter_enabled'] for row in frames] == [False, False, True, True]
assert all(row['draw_realtime'] and row['resolved_aa_method'] == 2 for row in frames)
assert all(row['shell_instances'] == 32 for row in frames)
execution_marker = 'Production pre-TAA fur denoise executed:'
assert execution_marker in log
assert 'LogPython: Error:' not in log and 'Ensure condition failed' not in log
assert job['status'] == 'exited' and job['root_exit_code'] == 0

images = {
    name: np.asarray(Image.open(capture / (name + '.png')).convert('RGB'), dtype=np.int16)
    for name in ('off-a', 'off-b', 'on-a', 'on-b')
}
assert len({image.shape for image in images.values()}) == 1
subject = np.maximum.reduce([image.max(axis=2) for image in images.values()]) > 8
assert int(subject.sum()) > 50_000


def mae(a, b):
    return float(np.abs(images[a] - images[b])[subject].mean())


changed = np.any(images['off-b'] != images['on-a'], axis=2) & subject
metrics = {
    'subject_pixels': int(subject.sum()),
    'off_pair_mae_rgb8': mae('off-a', 'off-b'),
    'on_pair_mae_rgb8': mae('on-a', 'on-b'),
    'off_to_on_transition_mae_rgb8': mae('off-b', 'on-a'),
    'off_to_on_subject_pixels_changed': int(changed.sum()),
}
assert metrics['off_to_on_subject_pixels_changed'] > 1_000

validation = {
    'status': 'passed',
    'production_render_thread_execution_logged': True,
    'tagged_surface_material': report['material'],
    'frames': [row['label'] for row in frames],
    'metrics': metrics,
    'peak_job_gib': job['job_memory']['peak_job_gib'],
    'limits': [
        'This proves production integration on generated shell fur, not retail-character parity.',
        'The off/on captures are different temporal frames, so transition MAE is not a same-frame filter delta.',
        'The synthetic on-pair MAE is not lower than the off-pair MAE; no quality-improvement claim is made.'
    ]
}
(capture / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n', encoding='utf-8')

canvas = Image.new('RGB', (images['off-b'].shape[1] * 2, images['off-b'].shape[0] + 44), (16, 20, 25))
draw = ImageDraw.Draw(canvas)
for column, (name, label) in enumerate((('off-b', 'Production filter OFF'), ('on-b', 'Production filter ON'))):
    image = Image.fromarray(images[name].astype(np.uint8))
    canvas.paste(image, (column * image.width, 32))
    draw.text((column * image.width + 12, 9), label, fill='white')
canvas.save(capture / 'comparison.png')
print(json.dumps(validation, indent=2))
