"""Present saved evidence without starting inference or exposing provider records."""
import json
from .storage import DATA, media_path, scene_path


def demo_record():
    record = json.loads((DATA / 'demo' / 'manifest.json').read_text())
    scene_id = record.pop('restored_scene')
    fallback = record.pop('occupied_scene')
    run_id = record.pop('completion_run')
    snapshot = record.pop('snapshot_world', None)
    if not run_id.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Invalid completion run')
    directory = DATA / 'world-generation' / (run_id + '-world')
    if snapshot:
        world = snapshot
    elif scene_path(scene_id).exists():
        pipeline = DATA / 'completion' / run_id / 'pipeline.json'
        inspected = pipeline.exists() and json.loads(pipeline.read_text()).get('status') == 'built_and_inspected'
        world = {'scene_id': scene_id,
                 'status': 'Clean-input room · inspection recorded' if inspected else 'Clean-input room · inspection in progress',
                 'detail': 'Generated from the corrected panorama. Hidden surfaces are inferred; geometry and collision quality remain prototype limitations. Hunyuan fallback, not Marble.'}
    else:
        status_path = directory / 'status.json'
        status = json.loads(status_path.read_text()).get('status') if status_path.exists() else None
        state = {'IN_QUEUE': 'Queued for 3D generation', 'IN_PROGRESS': 'Generating the cleaned room', 'COMPLETED': 'Downloading and preparing the cleaned room'}.get(status, 'Cleaned reconstruction pending')
        world = {'scene_id': fallback if scene_path(fallback).exists() else None,
                 'status': state,
                 'detail': 'The available 3D workspace is the earlier occupied reconstruction, with separated chair parts. It is not the cleaned result. Provider status is the latest saved observation.'}
    # Paths are checked before exposing the manifest as a browser presentation.
    for chapter in record['chapters']:
        for name in ('before', 'after'):
            if not media_path(chapter[name]).is_file():
                raise FileNotFoundError(chapter[name])
    repair = {
        'label': 'Repair furniture',
        'before': 'captures/view-d6f5eda08d52/image.png',
        'after': 'captures/view-de30fb660636/image.png',
        'scope': '3D table and chair repair · same camera, before and after.',
        'trace': 'https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09c29-918d-7315-b341-8345512beb11',
    }
    if (not snapshot and scene_path('office-rebuild').exists()
            and all(media_path(repair[key]).is_file() for key in ('before', 'after'))):
        latest_path = DATA / 'demo' / 'repair-comparison.json'
        if latest_path.exists():
            latest = json.loads(latest_path.read_text())
            scene = json.loads(scene_path('office-rebuild').read_text())
            if (latest.get('revision_id') == scene['current_revision']
                    and all(media_path(latest[key]).is_file() for key in ('before', 'after'))):
                repair = {key: latest[key] for key in ('before', 'after', 'scope')}
        record['repair'] = repair
        world = {'scene_id': 'office-rebuild', 'status': 'Local furniture repairs recorded',
                 'detail': 'Assistant-led table and chair repairs. Generated room geometry remains distorted.'}
    return {**record, 'world': world}
