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
    return {**record, 'world': world}
