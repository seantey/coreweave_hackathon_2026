"""Check the spherical coordinate contract and non-overlapping mask assignment."""

import numpy as np
import trimesh
from backend.partition import panorama_coordinates, assign_faces


def test_panorama_axes_match_hunyuan_camera_convention():
    points = np.array([[1, 0, 0], [0, -1, 0], [-1, 0, 0], [0, 1, 0]])
    uv = panorama_coordinates(points)
    assert np.allclose(uv, [[0, 0.5], [0.25, 0.5], [0.5, 0.5], [0.75, 0.5]])


def test_overlapping_masks_assign_each_triangle_once_and_preserve_remainder():
    mesh = trimesh.Trimesh(
        vertices=[
            [-1, -0.1, -0.1],
            [-1, 0.1, -0.1],
            [-1, 0, 0.1],
            [1, -0.1, -0.1],
            [1, 0.1, -0.1],
            [1, 0, 0.1],
        ],
        faces=[[0, 1, 2], [3, 4, 5]],
        process=False,
    )
    mask = np.zeros((20, 40), dtype=bool)
    mask[:, 15:25] = True
    assigned = assign_faces(mesh, [mask, mask.copy()])
    assert assigned.tolist() == [0, -1]
    parts = [
        mesh.submesh([np.flatnonzero(assigned == i)], append=True, repair=False)
        for i in [-1, 0]
    ]
    assert sum(len(part.faces) for part in parts) == len(mesh.faces)
    actual = np.concatenate([part.triangles_center for part in parts])
    assert np.allclose(np.sort(actual, axis=0), np.sort(mesh.triangles_center, axis=0))
