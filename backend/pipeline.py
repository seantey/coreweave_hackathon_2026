"""Run source correction, room reconstruction, object separation and scene inspection."""
from pathlib import Path
import json
import weave
from . import agent
from .completion import completion_loop, reconstruct_completion
from .storage import DATA, read_scene, scene_path, media_path, event, write_json


@weave.op()
def restore_room(source: str, run_id: str, scene_id: str, reference: str,
                 initial_candidate: str | None = None, max_edits: int = 3,
                 inspection_passes: int = 2):
    completion = completion_loop(source, run_id, max_edits, initial_candidate)
    if completion['accepted'] is not True:
        return {'status': 'needs_evidence', 'completion': completion}
    reconstruction = reconstruct_completion(run_id, scene_id, reference)
    scene = read_scene(scene_id)
    manifest = json.loads((scene_path(scene_id).parent / 'import.json').read_text())
    chair_layer = next((layer for layer in manifest['layers'] if 'chair' in layer['detected_labels']), None)
    if chair_layer and len(scene.revisions) == 1:
        asset_id = f"layer-{chair_layer['layer']}"
        if any(asset.id == asset_id for asset in scene.assets):
            from .segmentation import segment
            from .partition import partition_layer
            panorama = media_path(manifest['layer_sources'][asset_id])
            directory = DATA / 'completion' / run_id / 'room-chair-segmentation'
            record = segment(panorama, 'chair', directory=directory)
            if any((mask.get('score') or 0) >= .75 for mask in record['masks']):
                partition_layer(scene_id, asset_id, directory / 'segmentation.json', panorama)
            else:
                event(scene_id, 'partition_withheld', {'reason': 'No chair masks met the candidate threshold'})
    inspection = agent.repair_loop(scene_id, inspection_passes)
    result = {'status': 'built_and_inspected', 'completion': completion,
              'reconstruction': reconstruction, 'inspection': inspection,
              'scope': 'Prototype inferred room; inspect evidence, geometry and remaining limitations'}
    write_json(DATA / 'completion' / run_id / 'pipeline.json', result)
    return result


def run_pipeline(*args, **kwargs):
    agent.initialize_tracing()
    try:
        return restore_room(*args, **kwargs)
    finally:
        if agent.CLIENT: agent.CLIENT.flush()
