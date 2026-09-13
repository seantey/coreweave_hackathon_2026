import numpy as np
import trimesh
from PIL import Image
from backend.panorama_texture import texture_panorama


def test_texture_seam_preserves_geometry_and_short_uv_interpolation(tmp_path):
    mesh = trimesh.Trimesh(
        vertices=[[1, 0.1, 0], [1, -0.1, 0], [1, -0.1, 1]],
        faces=[[0, 1, 2]],
        process=False,
    )
    image = tmp_path / "pano.png"
    Image.new("RGB", (40, 20), "red").save(image)
    textured = texture_panorama(mesh, image)
    assert np.allclose(textured.triangles, mesh.triangles)
    assert np.ptp(textured.visual.uv[textured.faces, 0]) < 0.5
    target = tmp_path / "mesh.glb"
    textured.export(target)
    restored = trimesh.load(target, force="scene").to_geometry()
    assert np.allclose(restored.triangles, mesh.triangles)
    assert restored.visual.kind == "texture"
