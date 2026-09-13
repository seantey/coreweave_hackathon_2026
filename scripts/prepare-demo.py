"""Curate the recorded office experiment for presentation; never invent a run.

Run with: uv run python scripts/prepare-demo.py
This script packages this demonstration's existing checkpoints. It does not run
the agent or generate new images. Paths stay inside CLEANROOM_DATA_DIR.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from backend.storage import DATA, media_path, write_json


def read(path):
    return json.loads(media_path(path).read_text())


def prepare():
    run = 'office-panorama-masked'
    summary = read(f'completion/{run}/summary.json')
    if summary['accepted'] is not True:
        raise ValueError('This presentation requires the recorded accepted input')
    final = read(summary['history'][-1]['evaluation'])
    targeted = 'completion/office-panorama-targeted/pass-00'
    plan = read(targeted + '/plan-with-person-audit.json')['plan']
    audit = read(targeted + '/evaluation-with-person-audit.json')['person_audit']
    if audit['people_count'] < 1 or plan['action'] != 'edit':
        raise ValueError('Expected recorded detector counter-evidence and edit plan')
    # Crop original pixels to compare the same region, not the model's resized
    # crop input with its generated output. This includes masked compositing.
    before = 'completion/office-panorama-cleaning/pass-00/edit/candidate.png'
    after = targeted + '/edit-masked/candidate.png'
    box = read(targeted + '/edit-masked/composition.json')['box_pixels']
    directory = DATA / 'demo'
    directory.mkdir(exist_ok=True)
    for name, path in [('detail-before', before), ('detail-after', after)]:
        with Image.open(media_path(path)) as image:
            image.crop(box).save(directory / (name + '.png'))
    raw = f'completion/{run}/original.png'
    trace = 'https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/'
    chapters = [
        {'label': 'Restore', 'title': 'Remove people. Preserve the place.',
         'description': 'A busy office becomes a candidate for an unoccupied virtual room. The goal stays fixed: preserve the furniture, layout and belongings.',
         'before': raw, 'after': summary['candidate'], 'before_label': 'Occupied panorama', 'after_label': 'Corrected input',
         'evidence': 'The final image passed model-based people, furniture, layout and visible-damage checks, plus a person-detector audit and follow-up uncertainty review.',
         'scope': 'Panorama generated from the supplied office photo; extended surroundings and newly exposed surfaces are inferred. Image approval does not validate 3D geometry.'},
        {'label': 'Challenge', 'title': 'The first verdict was wrong.',
         'description': 'A broad scene review missed a distant person. Segmentation and enlarged crop review supplied counter-evidence, so the agent could not simply trust its first answer.',
         'before': 'demo/detail-before.png', 'after': 'demo/detail-before.png', 'before_label': 'Same recorded crop', 'after_label': 'Remaining person',
         'evidence': audit['detections'][0]['explanation'],
         'trace': trace + '01a09bc5-8347-7d4d-957b-099e9c2022af',
         'scope': 'Enlarged pixels from the failed candidate. The person is near the crop center; this is a real recorded model disagreement, not a simulated fault.'},
        {'label': 'Repair', 'title': 'Zoom in. Edit less.',
         'description': 'The agent chose a localized crop edit after receiving the person mask. A tighter, mask-based composite then limited changes to the person region.',
         'before': 'demo/detail-before.png', 'after': 'demo/detail-after.png', 'before_label': 'Missed occupant', 'after_label': 'Targeted correction',
         'evidence': 'The recorded plan selected a crop around the remaining person. The subsequent mask-compositing refinement reused the paid output and changed about 0.041% of the full panorama’s pixels.',
         'trace': trace + '01a09bcc-d9e2-7beb-867a-6402eaf24b02',
         'scope': 'Agent-selected regional edit; mask compositing was an assistant-led refinement during development. This is a selected branch of the experiment, not one uninterrupted autonomous run.'},
        {'label': 'Recheck', 'title': 'People gone is not enough.',
         'description': 'The next review questioned furniture preservation. The loop requested another correction and checked the candidate again before starting reconstruction.',
         'before': f'completion/{run}/initial.png', 'after': summary['candidate'], 'before_label': 'Before preservation pass', 'after_label': 'Approved 2D input',
         'evidence': final['assessment']['evidence'],
         'scope': 'These are fallible model judgments. Original uncertainties and follow-up decisions remain in the saved evaluations; unseen physical surfaces cannot be recovered as ground truth.'},
    ]
    events = [json.loads(line) for line in (DATA / 'scenes' / 'office-textured' / 'events.jsonl').read_text().splitlines()]
    rejected = next(event['payload'] for event in events if event['kind'] == 'evaluation' and event['payload'].get('job_id') == 'loop-72cd9f125a21')
    if rejected['accepted'] is not False:
        raise ValueError('The rejection chapter must describe an actual rejected edit')
    chapters.append({
        'label': 'Reject', 'title': 'An edit is not an improvement.',
        'description': 'In the earlier 3D room, hiding a detected person layer did not remove the occupant from the rendered scene. Matched-camera review rejected the edit; further inspection found people baked into another layer.',
        'before': rejected['before'][0]['image'], 'after': rejected['after'][0]['image'],
        'before_label': 'Before 3D edit', 'after_label': 'Rejected candidate',
        'evidence': 'The target person remains. Measured image changes: Forward 0.138%, Right 0%, Back 0%. The evaluator’s “identical” description was imprecise; the edit still failed its people-removal goal.',
        'trace': trace + '01a09bc9-ae33-7174-b470-54bb0526afbd',
        'scope': 'Earlier occupied-room experiment, shown separately from the source-image correction branch. No accepted autonomous 3D repair is claimed.'})
    write_json(directory / 'manifest.json', {'chapters': chapters, 'completion_run': run, 'restored_scene': 'office-clean', 'occupied_scene': 'office-textured'})
    print('Prepared recorded demo: http://127.0.0.1:5173/demo.html')


if __name__ == '__main__':
    prepare()
