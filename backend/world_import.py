"""Import a documented Mint world manifest without flattening its remote RAD stream."""

import json
from pathlib import Path
import httpx
import trimesh
from .models import Asset, Bounds, Camera, Revision, Scene
from .storage import DATA, save_scene, scene_path, timestamp, write_json, event


def import_mint_world(
    manifest_path: Path,
    scene_id: str,
    title: str,
    references: list[str],
    video: str | None = None,
    fixture: bool = False,
):
    from .cli import copy_asset

    if scene_path(scene_id).exists():
        raise ValueError(
            "Scene already exists; imports never overwrite revision history"
        )
    manifest = json.loads(manifest_path.read_text())
    runtime = manifest.get("runtime", {})
    if (
        manifest.get("integrationMode") != "remote_stream"
        or runtime.get("format") != "rad"
    ):
        raise ValueError("Expected a Mint remote_stream RAD world manifest")
    asset = Asset(
        id="source",
        label=title,
        kind="splat",
        remote_url=runtime["runtimeUrl"],
        paged=True,
        provenance="Marble reconstruction via Mint; source agreement and physical dimensions require verification",
    )
    collider_url = runtime["collider"]["runtimeUrl"]
    # Reuse URL validation without ever persisting credentials in the manifest.
    Asset(id="url-check", label="URL validation", kind="mesh", remote_url=collider_url)
    directory = DATA / "assets" / scene_id
    directory.mkdir(parents=True, exist_ok=True)
    collider_path = directory / "collider.glb"
    temporary = directory / "collider.glb.partial"
    with httpx.stream(
        "GET", collider_url, follow_redirects=True, timeout=120
    ) as response:
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)
    temporary.replace(collider_path)
    collider = trimesh.load(collider_path, force="scene")
    limits = collider.bounds
    if limits is None:
        raise ValueError("Collider contains no framing geometry")
    bounds = Bounds(minimum=tuple(limits[0]), maximum=tuple(limits[1]))
    asset.collider_path = str(collider_path.relative_to(DATA))
    # These are initial coordinate directions at the reconstruction origin, not
    # recovered source-camera calibration or semantic room orientations.
    cameras = {
        "Forward": Camera(position=(0, 0, 0), target=(0, 0, -2), fov=75),
        "Right": Camera(position=(0, 0, 0), target=(2, 0, 0), fov=75),
        "Back": Camera(position=(0, 0, 0), target=(0, 0, 2), fov=75),
        "Left": Camera(position=(0, 0, 0), target=(-2, 0, 0), fov=75),
    }
    scene = Scene(
        id=scene_id,
        title=title,
        description="Reconstruction from source imagery. Hidden surfaces are inferred; preservation and occupant removal require inspection.",
        assets=[asset],
        references=[copy_asset(path, scene_id) for path in references],
        video=copy_asset(video, scene_id) if video else None,
        cameras=cameras,
        bounds=bounds,
        revisions=[
            Revision(
                id="original",
                label="Initial reconstruction",
                status="baseline",
                created_at=timestamp(),
            )
        ],
        current_revision="original",
        source_kind="synthetic_fixture" if fixture else "captured_room",
    )
    save_scene(scene)
    write_json(scene_path(scene_id).parent / "generation-manifest.json", manifest)
    event(
        scene_id,
        "world_imported",
        {
            "source": manifest.get("source"),
            "integration": "remote RAD with local collider",
            "camera_status": "Initial coordinate directions; not source-calibrated",
            "fixture": fixture,
        },
    )
    return scene
