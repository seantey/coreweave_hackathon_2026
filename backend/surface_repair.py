"""Create reversible planar-surface candidates from reviewed image masks.

A mask identifies candidate vertices in one asset. The operator must inspect its
semantic scope and depth before invoking this tool. This does not discover that
an arbitrary surface ought to be planar.
"""
import json
from pathlib import Path
import numpy as np
import trimesh
import weave
from PIL import Image
from .models import Edit, Revision
from .storage import DATA, read_scene, save_scene, identifier, timestamp, write_json, event, media_path


def asset_matrix(transform):
    x, y, z = transform.rotation
    matrix = (trimesh.transformations.rotation_matrix(x, [1, 0, 0])
              @ trimesh.transformations.rotation_matrix(y, [0, 1, 0])
              @ trimesh.transformations.rotation_matrix(z, [0, 0, 1]))
    matrix[:3, :3] = matrix[:3, :3] @ np.diag(transform.scale)
    matrix[:3, 3] = transform.position
    return matrix


@weave.op()
def propose_planar_surface(scene_id: str, asset_id: str, mask_path: str,
                           camera_record: str, reference_camera: str, height: float,
                           reason: str, evidence: list[str]):
    if not np.isfinite(height):
        raise ValueError("Plane height must be finite")
    scene = read_scene(scene_id)
    asset = next(a for a in scene.assets if a.id == asset_id)
    if asset.kind != 'mesh' or asset.protected or asset.collider_path != asset.path:
        raise ValueError('Requires an unprotected mesh with matching appearance and collider')
    parent = next(r for r in scene.revisions if r.id == scene.current_revision)
    if parent.edits:
        raise ValueError('This version requires an unmodified baseline asset')
    camera = json.loads(media_path(camera_record).read_text())
    if camera['scene_id'] != scene_id or camera['revision_id'] != parent.id:
        raise ValueError('Mask camera must match the current scene revision')
    mesh_scene = trimesh.load(media_path(asset.path), force='scene', process=False)
    if len(mesh_scene.geometry) != 1 or len(mesh_scene.graph.nodes_geometry) != 1:
        raise ValueError('Requires one mesh with an identity node transform')
    node = mesh_scene.graph.nodes_geometry[0]
    node_matrix, geometry_name = mesh_scene.graph[node]
    if not np.allclose(node_matrix, np.eye(4)):
        raise ValueError('Nonidentity node transform is not supported')
    mesh = mesh_scene.geometry[geometry_name].copy()
    original = np.asarray(mesh.vertices).copy()
    matrix = asset_matrix(asset.transform)
    vertices = trimesh.transform_points(original, matrix)
    view = np.linalg.inv(np.array(camera['camera_matrix']).reshape(4, 4, order='F'))
    projection = np.array(camera['projection_matrix']).reshape(4, 4, order='F')
    clip = np.column_stack([vertices, np.ones(len(vertices))]) @ (projection @ view).T
    ndc = clip[:, :3] / np.where(abs(clip[:, 3:]) > 1e-12, clip[:, 3:], np.nan)
    mask = np.asarray(Image.open(media_path(mask_path)).convert('L')) > 127
    h, w = mask.shape
    if [w, h] != camera['viewport']:
        raise ValueError('Mask and camera viewport differ')
    uv = np.rint(np.column_stack([(ndc[:, 0] + 1) * w / 2, (1 - ndc[:, 1]) * h / 2]))
    valid = np.isfinite(uv).all(axis=1) & (clip[:, 3] > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    selected = np.zeros(len(vertices), dtype=bool)
    pixels = uv[valid].astype(int)
    selected[valid] = mask[pixels[:, 1], pixels[:, 0]]
    if selected.sum() < 3:
        raise ValueError('Mask selects insufficient geometry')
    origin = np.array(scene.cameras[reference_camera].position)
    directions = vertices[selected] - origin
    if np.any(abs(directions[:, 1]) < 1e-6):
        raise ValueError('Reference rays are parallel to the target plane')
    factors = (height - origin[1]) / directions[:, 1]
    if np.any(factors <= 0) or np.any(factors > 2):
        raise ValueError('Plane would reverse or excessively extend reference rays')
    repaired = vertices.copy()
    repaired[selected] = origin + directions * factors[:, None]
    local = trimesh.transform_points(repaired, np.linalg.inv(matrix))
    # Retain every unselected vertex exactly, including its original float values.
    local[~selected] = original[~selected]
    mesh.vertices = local
    repair_id = identifier('planar')
    directory = DATA / 'repairs' / repair_id
    directory.mkdir(parents=True)
    path = directory / 'candidate.glb'
    mesh.export(path)
    replacement = asset.model_copy(deep=True)
    replacement.id = repair_id
    replacement.label = asset.label + ' — planar surface candidate'
    replacement.path = replacement.collider_path = str(path.relative_to(DATA))
    replacement.initially_visible = False
    replacement.provenance += ' Targeted mask-selected planar correction; dimensions remain inferred.'
    scene.assets.append(replacement)
    revision = Revision(id=identifier('revision'), parent_id=parent.id, label=reason,
        created_at=timestamp(), edits=[
            Edit(id=identifier('edit'), operation='hide_asset', asset_id=asset.id, reason=reason, evidence=evidence),
            Edit(id=identifier('edit'), operation='place_asset', asset_id=replacement.id, transform=asset.transform, reason=reason, evidence=evidence)])
    scene.revisions.append(revision)
    report = dict(scene_id=scene_id, revision_id=revision.id, asset_id=asset_id,
        replacement_id=replacement.id, mask=mask_path, camera_record=camera_record,
        reference_camera=reference_camera, height=height, selected_vertices=int(selected.sum()),
        total_vertices=len(vertices), triangles=len(mesh.faces),
        before_height_range=float(np.ptp(vertices[selected, 1])),
        after_height_range=float(np.ptp(repaired[selected, 1])),
        maximum_displacement=float(np.linalg.norm(repaired-vertices, axis=1).max()),
        unselected_vertices_unchanged=bool(np.array_equal(local[~selected], original[~selected])),
        status='candidate', reason=reason, evidence=evidence)
    write_json(directory / 'report.json', report)
    save_scene(scene)
    event(scene_id, 'planar_surface_proposed', report)
    return report
