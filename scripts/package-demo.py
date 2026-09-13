"""Export a private replay snapshot, excluding credentials and provider job records."""
import argparse
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.demo import demo_record
from backend.storage import DATA, media_path, read_scene, scene_path, timestamp, write_json


def package(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Choose a new destination; snapshots are never overwritten')
    record = demo_record()
    manifest = json.loads((DATA / 'demo' / 'manifest.json').read_text())
    paths = {chapter[key] for chapter in record['chapters'] for key in ('before', 'after')}
    scenes = []
    for scene_id in {manifest['restored_scene'], manifest['occupied_scene']}:
        if not scene_path(scene_id).exists():
            continue
        scene = read_scene(scene_id)
        scenes.append(scene)
        paths.update(path for asset in scene.assets for path in (asset.path, asset.collider_path) if path)
        paths.update(scene.references)
        if scene.video:
            paths.add(scene.video)
    for relative in paths:
        source = media_path(relative)
        if not source.is_file():
            raise ValueError(f'Missing evidence: {relative}')
    for relative in sorted(paths):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media_path(relative), target)
    for scene in scenes:
        write_json(destination / 'scenes' / scene.id / 'scene.json', scene.model_dump(mode='json'))
    manifest['snapshot_world'] = {**record['world'], 'status': 'Recorded snapshot · ' + record['world']['status'],
                                  'detail': 'Snapshot captured ' + timestamp() + '. ' + record['world']['detail']}
    write_json(destination / 'demo' / 'manifest.json', manifest)
    write_json(destination / 'snapshot.json', {'created_at': timestamp(), 'scenes': [s.id for s in scenes], 'media_files': len(paths), 'purpose': 'Private replay only; no credentials or live provider job records included'})
    print(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    package(parser.parse_args().destination)
