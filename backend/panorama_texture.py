"""Project a layer panorama onto its raw Hunyuan mesh without losing image detail."""

import numpy as np
import trimesh
from PIL import Image
from .partition import panorama_coordinates


def texture_panorama(mesh: trimesh.Trimesh, image_path):
    uv = panorama_coordinates(mesh.vertices)
    faces = mesh.faces.copy()
    vertices = mesh.vertices.copy()
    # Duplicate only seam triangles so interpolation crosses the repeating edge,
    # rather than stretching the entire image across a narrow seam triangle.
    crossing = np.flatnonzero(np.ptp(uv[faces, 0], axis=1) > 0.5)
    if len(crossing):
        seam_faces = faces[crossing]
        seam_uv = uv[seam_faces].copy()
        seam_uv[..., 0] += seam_uv[..., 0] < 0.5
        faces[crossing] = np.arange(
            len(vertices), len(vertices) + 3 * len(crossing)
        ).reshape(-1, 3)
        vertices = np.concatenate([vertices, mesh.vertices[seam_faces].reshape(-1, 3)])
        uv = np.concatenate([uv, seam_uv.reshape(-1, 2)])
    # Trimesh's exporter flips bottom-origin UVs into glTF's top-origin convention.
    uv[:, 1] = 1 - uv[:, 1]
    with Image.open(image_path) as opened:
        texture = opened.convert("RGB")
        texture.thumbnail((2048, 1024), Image.Resampling.LANCZOS)
    result = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    result.visual = trimesh.visual.texture.TextureVisuals(
        uv=uv,
        material=trimesh.visual.material.PBRMaterial(
            baseColorTexture=texture,
            baseColorFactor=[255, 255, 255, 255],
            metallicFactor=0,
            roughnessFactor=1,
            doubleSided=True,
        ),
    )
    return result
