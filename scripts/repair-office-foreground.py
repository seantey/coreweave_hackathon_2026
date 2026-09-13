"""Reproduce the reviewed office foreground cleanup as pending scene revisions.

This is an office-specific experiment, not an automatic defect detector. Requires
its original local data and pre-cleanup revision; refuses duplicate execution.
The user explicitly authorized repairing this identified background-layer defect.
It preserves protected source assets and writes separate paired mesh replacements.
Inspect the resulting candidates from multiple cameras before accepting either.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.storage import (
    DATA,
    read_scene,
    save_scene,
    identifier,
    timestamp,
    write_json,
    event,
)
import json
from backend.models import Edit, Revision, Bounds
from backend.surface_repair import asset_matrix
import trimesh, numpy as np
from scipy.spatial import cKDTree, Delaunay

s = read_scene("office-rebuild")
a = next(a for a in s.assets if a.id == "layer-2")
parent = next(r for r in s.revisions if r.id == s.current_revision)
directory = DATA / "repairs/foreground-blob-v2"
directory.mkdir(parents=True, exist_ok=True)
assert parent.id == "revision-31257761382b", (
    "Requires the reviewed pre-cleanup office revision"
)
assert not any(a.id == "room-without-foreground-blob-v2" for a in s.assets), (
    "Cleanup already exists; inspect its saved revisions instead of rerunning"
)
m = trimesh.load(DATA / a.path, force="mesh", process=False)
matrix = asset_matrix(a.transform)
vertices = trimesh.transform_points(m.vertices, matrix)
uv = np.array(m.visual.uv)
low = np.array([-0.20, -0.60, -0.25])
high = np.array([0.16, 0.04, 0.17])
remaining = (vertices, np.array(m.faces), uv)
parts = []
for axis in range(3):
    for boundary, sign in [(low[axis], -1), (high[axis], 1)]:
        normal = np.eye(3)[axis] * sign
        origin = np.zeros(3)
        origin[axis] = boundary
        v, f, u = remaining
        outside = trimesh.intersections.slice_faces_plane(v, f, normal, origin, uv=u)
        if len(outside[1]):
            parts.append(outside)
        remaining = trimesh.intersections.slice_faces_plane(v, f, -normal, origin, uv=u)
# Infer the local floor plane from neighboring mesh floor samples, never from the floating remnant.
floor = (
    (vertices[:, 1] > -0.42)
    & (vertices[:, 1] < -0.34)
    & (vertices[:, 0] > -0.4)
    & (vertices[:, 0] < -0.16)
    & (abs(vertices[:, 2]) < 0.3)
)
samples = vertices[floor]
coef = np.linalg.lstsq(
    np.column_stack([samples[:, 0], samples[:, 2], np.ones(len(samples))]),
    samples[:, 1],
    rcond=None,
)[0]
# Fill the opening using its actual boundary heights so the floor has no seams or gaps.
boundary = []
boundary_uv = []
for v, f, u in parts:
    referenced = np.unique(f)
    v = v[referenced]
    u = u[referenced]
    on_edge = (
        np.isclose(v[:, 0], low[0])
        | np.isclose(v[:, 0], high[0])
        | np.isclose(v[:, 2], low[2])
        | np.isclose(v[:, 2], high[2])
    )
    within = (
        (v[:, 0] >= low[0] - 1e-8)
        & (v[:, 0] <= high[0] + 1e-8)
        & (v[:, 2] >= low[2] - 1e-8)
        & (v[:, 2] <= high[2] + 1e-8)
        & (v[:, 1] > low[1])
        & (v[:, 1] < -0.25)
    )
    boundary.extend(v[on_edge & within])
    boundary_uv.extend(u[on_edge & within])
boundary = np.array(boundary)
boundary_uv = np.array(boundary_uv)
_, indices = np.unique(np.round(boundary[:, [0, 2]], 8), axis=0, return_index=True)
patch = boundary[indices]
patch_uv = boundary_uv[indices]
# Interior point triangulates the boundary; use adjacent floor UVs for newly inferred surfaces.
center = np.array(
    [[(low[0] + high[0]) / 2, np.median(patch[:, 1]), (low[2] + high[2]) / 2]]
)
_, donor = cKDTree(samples[:, [0, 2]]).query(center[:, [0, 2]] + [-0.35, 0])
patch = np.vstack([patch, center])
patch_uv = np.vstack([patch_uv, uv[floor][donor]])
triangles = Delaunay(patch[:, [0, 2]]).simplices
parts.append((patch, triangles, patch_uv))
verts = []
faces = []
uvs = []
offset = 0
for v, f, u in parts:
    verts.append(v)
    faces.append(f + offset)
    uvs.append(u)
    offset += len(v)
result = trimesh.Trimesh(
    vertices=trimesh.transform_points(np.vstack(verts), np.linalg.inv(matrix)),
    faces=np.vstack(faces),
    visual=trimesh.visual.texture.TextureVisuals(
        uv=np.vstack(uvs), material=m.visual.material
    ),
    process=False,
)
result.remove_unreferenced_vertices()
result.export(directory / "room-without-foreground-blob.glb")
replacement = a.model_copy(deep=True)
replacement.id = "room-without-foreground-blob-v2"
replacement.label = "Room shell — central reconstruction remnant removed"
replacement.path = replacement.collider_path = str(
    (directory / "room-without-foreground-blob.glb").relative_to(DATA)
)
replacement.initially_visible = False
replacement.provenance += " User-requested local removal of malformed foreground geometry and inferred floor fill. Original scene remains available."
reason = "Remove the floating central reconstruction remnant from appearance and collider while retaining repaired table and chairs"
evidence = [
    "User identified floating central chunk after repair",
    ".artifacts/blob-picks.json",
    ".artifacts/blob-before.png",
    "Original office photo and multi-view inspection",
]
r = Revision(
    id=identifier("revision"),
    parent_id=parent.id,
    label=reason,
    created_at=timestamp(),
    edits=[
        *parent.edits,
        Edit(
            id=identifier("edit"),
            operation="hide_asset",
            asset_id=a.id,
            reason=reason,
            evidence=evidence,
        ),
        Edit(
            id=identifier("edit"),
            operation="place_asset",
            asset_id=replacement.id,
            transform=replacement.transform,
            reason=reason,
            evidence=evidence,
        ),
    ],
)
s.assets.append(replacement)
s.revisions.append(r)
save_scene(s)
report = {
    "revision": r.id,
    "parent": parent.id,
    "asset": a.id,
    "replacement": replacement.id,
    "bounds": {"minimum": low.tolist(), "maximum": high.tolist()},
    "old_triangles": len(m.faces),
    "new_triangles": len(result.faces),
    "removed_interior_triangles": len(remaining[1]),
    "floor_plane": coef.tolist(),
    "floor_sample_count": len(samples),
    "floor_height_corners": patch[:, 1].tolist(),
    "status": "candidate",
    "authorization": "User explicitly requested fixing the central floating chunk; default background protection retained on original asset; direct reviewed replacement only.",
}
write_json(directory / "report.json", report)
event(s.id, "foreground_blob_repair_proposed", report)
print(json.dumps(report))

floor_revision_id = r.id

s = read_scene("office-rebuild")
base = next(r for r in s.revisions if r.id == floor_revision_id)
a = next(a for a in s.assets if a.id == "desk-without-tabletop")
m = trimesh.load(DATA / a.path, force="mesh", process=False)
matrix = asset_matrix(a.transform)
remaining = (
    trimesh.transform_points(m.vertices, matrix),
    np.array(m.faces),
    np.array(m.visual.uv),
)
parts = []
low = np.array([-0.34, -0.65, -0.56])
high = np.array([0.23, -0.135, -0.09])
for axis in range(3):
    for boundary, sign in [(low[axis], -1), (high[axis], 1)]:
        normal = np.eye(3)[axis] * sign
        origin = np.zeros(3)
        origin[axis] = boundary
        v, f, u = remaining
        outside = trimesh.intersections.slice_faces_plane(v, f, normal, origin, uv=u)
        if len(outside[1]):
            parts.append(outside)
        remaining = trimesh.intersections.slice_faces_plane(v, f, -normal, origin, uv=u)
verts = []
faces = []
uvs = []
offset = 0
for v, f, u in parts:
    verts.append(v)
    faces.append(f + offset)
    uvs.append(u)
    offset += len(v)
rmesh = trimesh.Trimesh(
    vertices=trimesh.transform_points(np.vstack(verts), np.linalg.inv(matrix)),
    faces=np.vstack(faces),
    visual=trimesh.visual.texture.TextureVisuals(
        uv=np.vstack(uvs), material=m.visual.material
    ),
    process=False,
)
rmesh.remove_unreferenced_vertices()
directory = DATA / "repairs/foreground-cleanup-final"
directory.mkdir(parents=True, exist_ok=True)
rmesh.export(directory / "desk-without-old-table.glb")
asset = a.model_copy(deep=True)
asset.id = "desk-without-old-table"
asset.label = "Office desks — old table remnants removed"
asset.path = asset.collider_path = (
    "repairs/foreground-cleanup-final/desk-without-old-table.glb"
)
asset.initially_visible = False
reason = (
    "Remove old table legs and stray fragments that overlap the replacement furniture"
)
evidence = [
    "Isolated old desk collider shows obsolete table legs and a floating rectangular chunk",
    "User-requested clean table and chair collision geometry",
    ".artifacts/residual-desk-without-tabletop.png",
]
edits = [
    *base.edits,
    Edit(
        id=identifier("edit"),
        operation="hide_asset",
        asset_id=a.id,
        reason=reason,
        evidence=evidence,
    ),
    Edit(
        id=identifier("edit"),
        operation="place_asset",
        asset_id=asset.id,
        transform=asset.transform,
        reason=reason,
        evidence=evidence,
    ),
    Edit(
        id=identifier("edit"),
        operation="hide_region",
        asset_id="layer-0-remainder",
        bounds=Bounds(minimum=(-0.30, -0.65, -0.54), maximum=(0.20, -0.23, -0.10)),
        reason="Remove residual old furniture fragments below tabletop while keeping the laptop lid",
        evidence=[
            "Isolated chair remainder collider shows fragments below table",
            "Laptop is above the removal region",
        ],
    ),
]
r = Revision(
    id=identifier("revision"),
    parent_id=s.current_revision,
    label="Remove floating foreground remnant and obsolete table geometry",
    created_at=timestamp(),
    edits=edits,
)
s.assets.append(asset)
s.revisions.append(r)
save_scene(s)
report = {
    "revision": r.id,
    "parent": s.current_revision,
    "floor_candidate": base.id,
    "old_desk_triangles": len(m.faces),
    "new_desk_triangles": len(rmesh.faces),
    "removed_old_table_triangles": len(remaining[1]),
    "bounds": [low.tolist(), high.tolist()],
    "status": "candidate",
}
write_json(directory / "report.json", report)
event(s.id, "old_table_remnants_cleanup_proposed", report)
print(report)
