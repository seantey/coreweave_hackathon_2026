"""Partition an unedited Hunyuan mesh layer using masks in its source panorama.

Every original triangle is retained exactly once. This changes object addressing,
not geometry quality, and produces partial reconstructions rather than complete CAD assets.
"""

import json
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image
from .storage import (
    DATA,
    LOCK,
    read_scene,
    save_scene,
    scene_path,
    media_path,
    event,
    write_json,
)


def panorama_coordinates(points):
    """Invert Hunyuan's spherical_uv_to_directions in the raw, unrotated export frame."""
    points = np.asarray(points, dtype=float)
    radius = np.linalg.norm(points, axis=-1)
    if np.any(radius < 1e-10):
        raise ValueError("Cannot project a point at panorama origin")
    theta = np.arctan2(points[..., 1], points[..., 0])
    return np.stack(
        (
            (1 - theta / (2 * np.pi)) % 1,
            np.arccos(np.clip(points[..., 2] / radius, -1, 1)) / np.pi,
        ),
        axis=-1,
    )


def assign_faces(mesh, masks):
    uv = panorama_coordinates(mesh.triangles_center)
    assignments = np.full(len(mesh.faces), -1, dtype=np.int32)
    for index, mask in enumerate(masks):
        height, width = mask.shape
        x = np.clip((uv[:, 0] * width).astype(int), 0, width - 1)
        y = np.clip((uv[:, 1] * height).astype(int), 0, height - 1)
        selected = mask[y, x] & (assignments == -1)
        assignments[selected] = index
    return assignments


def partition_layer(
    scene_id: str,
    asset_id: str,
    segmentation_path: Path,
    source_panorama: Path,
    maximum_objects: int = 12,
):
    if not 1 <= maximum_objects <= 32:
        raise ValueError("Use one to thirty-two objects")
    record = json.loads(segmentation_path.read_text())
    source = Image.open(media_path(record["source_image"])).convert("RGB")
    reference = Image.open(source_panorama).convert("RGB")
    if source.size != reference.size or source.width != 2 * source.height:
        raise ValueError(
            "Segmentation must use the exact 2:1 panorama for this mesh layer"
        )
    if not np.array_equal(np.asarray(source), np.asarray(reference)):
        raise ValueError("Segmentation pixels differ from the supplied layer panorama")
    with LOCK:
        scene = read_scene(scene_id)
        if len(scene.revisions) != 1:
            raise ValueError("Partition at import time before scene edits")
        manifest_path = scene_path(scene_id).parent / "import.json"
        if (
            not manifest_path.exists()
            or json.loads(manifest_path.read_text()).get("provider")
            != "Hunyuan World via fal"
        ):
            raise ValueError("This projection is specific to Hunyuan raw mesh exports")
        manifest = json.loads(manifest_path.read_text())
        layer_source = manifest.get("layer_sources", {}).get(asset_id)
        if not layer_source:
            raise ValueError(
                "Import provenance does not identify this layer's source panorama"
            )
        with Image.open(media_path(layer_source)) as original_panorama:
            if not np.array_equal(
                np.asarray(original_panorama.convert("RGB")), np.asarray(reference)
            ):
                raise ValueError(
                    "Supplied panorama does not match this mesh layer's recorded source"
                )
        target = next((a for a in scene.assets if a.id == asset_id), None)
        if target is None:
            raise ValueError("Unknown source asset")
        if (
            target.kind != "mesh"
            or not target.path
            or target.collider_path != target.path
            or target.collider_matrix
        ):
            raise ValueError(
                "Partition requires a mesh with the same unmodified geometry as its collider"
            )
        geometry = trimesh.load(media_path(target.path), force="scene").to_geometry()
        candidates = [m for m in record["masks"] if (m.get("score") or 0) >= 0.75][
            :maximum_objects
        ]
        if not candidates:
            raise ValueError("No masks meet the candidate threshold")
        masks = [
            np.asarray(Image.open(media_path(item["path"])).convert("L")) > 127
            for item in candidates
        ]
        assignments = assign_faces(geometry, masks)
        directory = DATA / "assets" / scene_id / "partition" / asset_id
        directory.mkdir(parents=True, exist_ok=True)
        replacements = []
        counts = []
        for index in [-1, *range(len(candidates))]:
            faces = np.flatnonzero(assignments == index)
            if not len(faces):
                continue
            part = geometry.submesh([faces], append=True, repair=False)
            identifier = (
                f"{asset_id}-remainder"
                if index < 0
                else f"{asset_id}-object-{index:02}"
            )
            output = directory / f"{identifier}.glb"
            part.export(output)
            relative = str(output.relative_to(DATA))
            asset = target.model_copy(deep=True)
            asset.id = identifier
            asset.path = relative
            asset.collider_path = relative
            asset.label = (
                target.label + " remainder"
                if index < 0
                else f"{record['prompt'].capitalize()} {'fragment' if len(faces) < 1000 else 'candidate'} {index + 1}"
            )
            asset.provenance += f" Partitioned by panorama mask: {len(faces)} triangles; hidden surfaces and semantic purity remain unverified."
            replacements.append(asset)
            counts.append(
                {
                    "asset_id": identifier,
                    "triangles": len(faces),
                    "mask": None if index < 0 else candidates[index],
                }
            )
        if sum(item["triangles"] for item in counts) != len(geometry.faces):
            raise AssertionError("Partition lost triangles")
        original = scene.model_dump(mode="json")
        write_json(directory / "before-partition.json", original)
        scene.assets = [
            asset for asset in scene.assets if asset.id != asset_id
        ] + replacements
        save_scene(scene)
        result = {
            "source_asset": target.model_dump(mode="json"),
            "source_triangles": len(geometry.faces),
            "parts": counts,
            "scope": "Addressable mesh parts; all original triangles retained, not a reconstruction-quality improvement",
        }
        write_json(directory / "partition.json", result)
        event(scene_id, "asset_partitioned", result)
        return result
