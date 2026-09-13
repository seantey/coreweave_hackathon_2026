"""Import Hunyuan's layered panorama reconstruction with inspectable provenance."""

import json
import math
import zipfile
from pathlib import Path
import httpx
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from PIL import Image
from .models import Asset, Bounds, Camera, Revision, Scene, Transform
from .storage import DATA, scene_path, save_scene, timestamp, write_json, event


def import_world(job_path: Path, scene_id: str, title: str, references: list[str]):
    from .cli import copy_asset

    if scene_path(scene_id).exists():
        raise ValueError("Scene already exists; preserve prior revisions")
    result = json.loads((job_path.parent / "result.json").read_text())
    archive = job_path.parent / "world.zip"
    if not archive.exists():
        with httpx.stream(
            "GET", result["world_file"]["url"], timeout=120, follow_redirects=True
        ) as response:
            response.raise_for_status()
            temporary = archive.with_suffix(".partial")
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
            temporary.replace(archive)
    extracted = job_path.parent / "layers"
    extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            target = (extracted / info.filename).resolve()
            if not target.is_relative_to(extracted.resolve()):
                raise ValueError("Unsafe archive path")
            if info.file_size > 1_000_000_000:
                raise ValueError("Unexpectedly large world layer")
            if not target.exists():
                source.extract(info, extracted)
    with Image.open(extracted / "image.png") as panorama:
        if panorama.width != 2 * panorama.height:
            raise ValueError(
                "Hunyuan world input must be an equirectangular panorama with 2:1 dimensions; ordinary photos produce distorted geometry"
            )
    directory = DATA / "assets" / scene_id
    directory.mkdir(parents=True, exist_ok=True)
    assets = []
    records = []
    for index, path in enumerate(sorted(extracted.glob("mesh_layer*.ply"))):
        mesh = trimesh.load(path, process=False)
        original_count = len(mesh.faces)
        budget = 150_000 if index < 2 else 400_000 if index == 2 else 40_000
        simplified = mesh.simplify_quadric_decimation(
            face_count=min(budget, original_count)
        )
        _, nearest = cKDTree(mesh.vertices).query(simplified.vertices)
        colors = np.asarray(mesh.visual.vertex_colors)[nearest].copy()
        srgb = colors[:, :3] / 255.0
        linear = np.where(
            srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4
        )
        colors[:, :3] = np.round(linear * 255).astype(np.uint8)
        simplified.visual.vertex_colors = colors
        output = directory / f"layer-{index}.glb"
        simplified.export(output)
        labels = []
        if index < 2 and (extracted / f"fg{index + 1}.json").exists():
            detections = json.loads((extracted / f"fg{index + 1}.json").read_text())
            labels = sorted({box["label"] for box in detections.get("bboxes", [])})
        label = (
            ", ".join(labels)
            if labels
            else (
                "Background completion"
                if index == 2
                else "Distant shell"
                if index == 3
                else f"Layer {index}"
            )
        )
        relative = str(output.relative_to(DATA))
        assets.append(
            Asset(
                id=f"layer-{index}",
                label=label,
                kind="mesh",
                path=relative,
                collider_path=relative if index < 3 else None,
                unlit=True,
                protected=index >= 2,
                transform=Transform(rotation=(-math.pi / 2, 0, -math.pi / 2)),
                provenance="Hunyuan panorama reconstruction; layer labels are detector hypotheses. Hidden surfaces, physical scale, and source fidelity are unverified. Mesh simplified with nearest-source color transfer.",
            )
        )
        records.append(
            {
                "layer": index,
                "detected_labels": labels,
                "original_triangles": original_count,
                "render_triangles": len(simplified.faces),
            }
        )
    if not assets:
        raise ValueError("No world mesh layers returned")
    cameras = {
        name: Camera(position=(0, 0, 0), target=target, fov=75)
        for name, target in {
            "Forward": (0, 0, -2),
            "Right": (2, 0, 0),
            "Back": (0, 0, 2),
            "Left": (-2, 0, 0),
        }.items()
    }
    bounds_points = []
    rotation = trimesh.transformations.euler_matrix(
        -math.pi / 2, 0, -math.pi / 2, axes="rxyz"
    )
    for asset in assets:
        geometry = trimesh.load(DATA / asset.path, force="scene")
        geometry.apply_transform(rotation)
        bounds_points.extend(geometry.bounds)
    bounds_points = np.asarray(bounds_points)
    scene = Scene(
        id=scene_id,
        title=title,
        description="Panorama-based Hunyuan fallback. Original references are evidence; generated views and hidden surfaces are hypotheses.",
        assets=assets,
        references=[copy_asset(p, scene_id) for p in references],
        cameras=cameras,
        bounds=Bounds(
            minimum=tuple(bounds_points.min(axis=0)),
            maximum=tuple(bounds_points.max(axis=0)),
        ),
        revisions=[
            Revision(
                id="original",
                label="Initial reconstruction",
                status="baseline",
                created_at=timestamp(),
            )
        ],
        current_revision="original",
    )
    save_scene(scene)
    write_json(
        scene_path(scene_id).parent / "import.json",
        {
            "provider": "Hunyuan World via fal",
            "job": str(job_path),
            "layers": records,
            "panorama": copy_asset(extracted / "image.png", scene_id),
            "orientation": "Official viewer rotateX(-pi/2), rotateZ(-pi/2)",
            "color": "Input sRGB vertex colors converted to linear for glTF",
        },
    )
    event(
        scene_id,
        "world_imported",
        {
            "provider": "Hunyuan World via fal",
            "layers": records,
            "scope": "Unverified reconstruction, no restoration accepted",
        },
    )
    return scene
