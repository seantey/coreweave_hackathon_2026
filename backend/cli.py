"""Command-line access to the same scene operations used by the application."""

import argparse, hashlib, json, shutil
from pathlib import Path
import numpy as np
from .storage import (
    DATA,
    read_scene,
    save_scene,
    timestamp,
    identifier,
    write_json,
    propose,
    decide,
)
from .models import Scene, Asset, Camera, Bounds, Revision, Transform, Edit, ImageRegion


def copy_asset(source, scene_id):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError(f"Missing input: {source}")
    # Different inputs often share camera filenames; avoid silently replacing prior evidence.
    with source.open("rb") as input_file:
        digest = hashlib.file_digest(input_file, "sha256").hexdigest()[:12]
    destination = DATA / "assets" / scene_id / (digest + "-" + source.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source != destination:
        shutil.copy2(source, destination)
    return str(destination.relative_to(DATA))


def ply_bounds(path):
    """Read Gaussian center bounds for framing, not physical units or semantic geometry."""
    fields = []
    count = None
    with Path(path).open("rb") as f:
        for _ in range(200):
            line = f.readline().decode("ascii").strip()
            if line.startswith("format ") and line != "format binary_little_endian 1.0":
                raise ValueError(
                    "Automatic framing supports binary little-endian Gaussian PLY; supply bounds for other formats"
                )
            if line.startswith("element vertex "):
                count = int(line.split()[-1])
            if line.startswith("property "):
                _, kind, name = line.split()
                if kind != "float":
                    raise ValueError("Automatic PLY framing requires float fields")
                fields.append((name, "<f4"))
            if line == "end_header":
                break
        if not count:
            raise ValueError("No vertices found")
        a = np.fromfile(f, dtype=np.dtype(fields), count=count)
        points = np.stack([a[k] for k in ("x", "y", "z")], axis=1)
        points = points[np.isfinite(points).all(axis=1)]
        low = np.quantile(points, 0.005, axis=0)
        high = np.quantile(points, 0.995, axis=0)
        padding = np.maximum((high - low) * 0.15, 0.02)
        return Bounds(minimum=tuple(low - padding), maximum=tuple(high + padding))


def import_scene(args):
    if (DATA / "scenes" / args.id / "scene.json").exists():
        raise ValueError("Scene already exists; choose a new id")
    if args.bounds:
        values = json.loads(args.bounds)
        bounds = Bounds(minimum=values[:3], maximum=values[3:])
    else:
        bounds = ply_bounds(args.splat)
    midpoint = (np.array(bounds.minimum) + np.array(bounds.maximum)) / 2
    radius = (
        float(np.linalg.norm(np.array(bounds.maximum) - np.array(bounds.minimum))) * 0.8
    )
    cameras = {
        "Front": Camera(
            position=tuple(midpoint + [0, radius * 0.15, radius]),
            target=tuple(midpoint),
        ),
        "Three-quarter": Camera(
            position=tuple(midpoint + [radius * 0.8, radius * 0.3, radius * 0.8]),
            target=tuple(midpoint),
        ),
        "Back": Camera(
            position=tuple(midpoint + [0, radius * 0.15, -radius]),
            target=tuple(midpoint),
        ),
        "Overhead": Camera(
            position=tuple(midpoint + [0.01, radius, 0.01]), target=tuple(midpoint)
        ),
    }
    baseline = Revision(
        id="original", label="Original", status="baseline", created_at=timestamp()
    )
    scene = Scene(
        id=args.id,
        title=args.title,
        description=args.description,
        assets=[
            Asset(
                id="source",
                label=args.title,
                kind="splat",
                path=copy_asset(args.splat, args.id),
                collider_path=copy_asset(args.collider, args.id)
                if args.collider
                else None,
                provenance="Imported reconstruction; geometric accuracy unverified",
            )
        ],
        references=[copy_asset(p, args.id) for p in args.reference],
        video=copy_asset(args.video, args.id) if args.video else None,
        cameras=cameras,
        bounds=bounds,
        revisions=[baseline],
        current_revision="original",
        source_kind="object_probe" if args.object_probe else "captured_room",
    )
    save_scene(scene)
    print(
        json.dumps(
            {"scene": scene.id, "bounds": bounds.model_dump(), "data_dir": str(DATA)},
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("review-segmentation")
    p.add_argument("segmentation")
    p = commands.add_parser("generate-marble")
    p.add_argument("source")
    p.add_argument("--prompt", required=True)
    p.add_argument("--title", default="Clean Room Imputation")
    p.add_argument("--model", default="marble-1.1")
    p = commands.add_parser("resume-marble")
    p.add_argument("operation")
    p.add_argument("--timeout", type=float, default=600)
    p = commands.add_parser("segment")
    p.add_argument("image")
    p.add_argument("--prompt", required=True)
    p.add_argument("--maximum-masks", type=int, default=32)
    p = commands.add_parser("resume-fal")
    p.add_argument("job")
    p.add_argument("--timeout", type=float, default=180)
    p = commands.add_parser("import-mint-world")
    p.add_argument("manifest")
    p.add_argument("--id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--reference", action="append", default=[])
    p.add_argument("--video")
    p.add_argument(
        "--fixture",
        action="store_true",
        help="Label imported prior content as a test fixture, not the office",
    )
    p = commands.add_parser("import-scene")
    p.add_argument("--id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument(
        "--description",
        default="Imported scene. Source coverage and physical dimensions are unverified.",
    )
    p.add_argument("--splat", required=True)
    p.add_argument("--collider")
    p.add_argument("--reference", action="append", default=[])
    p.add_argument("--video")
    p.add_argument("--object-probe", action="store_true")
    p.add_argument(
        "--bounds",
        help="JSON [minX,minY,minZ,maxX,maxY,maxZ] for SPZ/RAD or explicit framing",
    )
    p = commands.add_parser("capture")
    p.add_argument("scene")
    p.add_argument("--camera", default="Front")
    p.add_argument("--revision")
    p.add_argument(
        "--region",
        help="JSON [left,top,right,bottom], normalized image rectangle for collider inspection",
    )
    p = commands.add_parser("propose")
    p.add_argument("scene")
    p.add_argument("edit_file")
    p = commands.add_parser("decide")
    p.add_argument("scene")
    p.add_argument("revision")
    p.add_argument("--accept", action="store_true")
    p.add_argument("--reason", required=True)
    p = commands.add_parser("loop")
    p.add_argument("scene")
    p.add_argument("--passes", type=int, default=2)
    p = commands.add_parser("reconstruct")
    p.add_argument("image")
    p.add_argument("--box", required=True, help="JSON [x_min,y_min,x_max,y_max]")
    p.add_argument("--seed", type=int, default=42)
    p = commands.add_parser("export")
    p.add_argument("scene")
    p.add_argument("output")
    p = commands.add_parser("align-sam")
    p.add_argument("scene")
    p.add_argument("metadata_file")
    p.add_argument("--asset", default="source")
    p = commands.add_parser("register-asset")
    p.add_argument("scene")
    p.add_argument("--id", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--kind", choices=["splat", "mesh"], required=True)
    p.add_argument("--collider")
    p.add_argument(
        "--collider-matrix", help="JSON column-major 4x4 registration matrix"
    )
    p.add_argument(
        "--provenance",
        required=True,
        help="Source and uncertainty of this reusable asset",
    )
    args = parser.parse_args()
    if args.command == "review-segmentation":
        from . import agent
        from .mask_review import review_segmentation

        agent.initialize_tracing()
        try:
            print(json.dumps(review_segmentation(args.segmentation), indent=2))
        finally:
            if agent.CLIENT:
                agent.CLIENT.flush()
    elif args.command == "generate-marble":
        from .worldlabs import generate

        print(generate(Path(args.source), args.prompt, args.title, args.model))
    elif args.command == "resume-marble":
        from .worldlabs import resume

        result = resume(Path(args.operation), args.timeout)
        print(
            json.dumps(
                {
                    "world_id": result.get("world_id"),
                    "world_marble_url": result.get("world_marble_url"),
                },
                indent=2,
            )
        )
    elif args.command == "segment":
        from .segmentation import segment

        print(
            json.dumps(
                segment(Path(args.image), args.prompt, args.maximum_masks), indent=2
            )
        )
    elif args.command == "resume-fal":
        from .fal_jobs import resume

        print(json.dumps(resume(Path(args.job), args.timeout), indent=2))
    elif args.command == "import-mint-world":
        from .world_import import import_mint_world

        scene = import_mint_world(
            Path(args.manifest),
            args.id,
            args.title,
            args.reference,
            args.video,
            args.fixture,
        )
        print(
            json.dumps(
                {
                    "scene_id": scene.id,
                    "bounds": scene.bounds.model_dump(),
                    "remote_stream": True,
                },
                indent=2,
            )
        )
    elif args.command == "import-scene":
        import_scene(args)
    elif args.command == "capture":
        from .capture import capture

        scene = read_scene(args.scene)
        values = json.loads(args.region) if args.region else None
        region = ImageRegion(minimum=values[:2], maximum=values[2:]) if values else None
        print(
            json.dumps(
                capture(
                    args.scene,
                    args.revision or scene.current_revision,
                    args.camera,
                    region,
                ),
                indent=2,
            )
        )
    elif args.command == "propose":
        print(
            propose(
                args.scene, Edit.model_validate_json(Path(args.edit_file).read_text())
            ).model_dump_json(indent=2)
        )
    elif args.command == "decide":
        print(
            decide(
                args.scene,
                args.revision,
                args.accept,
                {"source": "operator", "reason": args.reason},
            ).model_dump_json(indent=2)
        )
    elif args.command == "loop":
        from .agent import run_traced_loop

        print(json.dumps(run_traced_loop(args.scene, args.passes), indent=2))
    elif args.command == "reconstruct":
        from .providers import reconstruct

        box = dict(
            zip(("x_min", "y_min", "x_max", "y_max"), json.loads(args.box), strict=True)
        )
        print(json.dumps(reconstruct(Path(args.image), box, args.seed), indent=2))
    elif args.command == "align-sam":
        from .alignment import fit
        from .storage import media_path, event

        scene = read_scene(args.scene)
        asset = next(a for a in scene.assets if a.id == args.asset)
        if not asset.path or not asset.collider_path:
            raise ValueError("Both splat and collider are required")
        if len(scene.revisions) > 1:
            raise ValueError("Calibrate before making scene revisions")
        metadata = json.loads(Path(args.metadata_file).read_text())["metadata"][0]
        result = fit(media_path(asset.path), media_path(asset.collider_path), metadata)
        asset.collider_matrix = tuple(result["best"]["matrix"])
        save_scene(scene)
        event(scene.id, "collider_calibration", result)
        print(json.dumps(result, indent=2))
    elif args.command == "register-asset":
        from .storage import LOCK, event

        with LOCK:
            scene = read_scene(args.scene)
            if any(asset.id == args.id for asset in scene.assets):
                raise ValueError("Asset id already registered")
            asset = Asset(
                id=args.id,
                label=args.label,
                kind=args.kind,
                path=copy_asset(args.path, args.scene),
                collider_path=copy_asset(args.collider, args.scene)
                if args.collider
                else None,
                collider_matrix=tuple(json.loads(args.collider_matrix))
                if args.collider_matrix
                else None,
                initially_visible=False,
                provenance=args.provenance,
            )
            scene.assets.append(asset)
            save_scene(scene)
            event(
                scene.id,
                "asset_registered",
                {
                    "asset": asset.model_dump(mode="json"),
                    "note": "Inactive library asset; placement requires a reviewed scene revision",
                },
            )
            print(asset.model_dump_json(indent=2))
    elif args.command == "export":
        scene = read_scene(args.scene)
        destination = Path(args.output).resolve()
        if destination.exists():
            raise ValueError("Export destination already exists")
        # Export a portable scene package with assets and edits, not provider credentials or raw job responses.
        for path in (
            {p for a in scene.assets for p in (a.path, a.collider_path) if p}
            | set(scene.references)
            | ({scene.video} if scene.video else set())
        ):
            from .storage import media_path

            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(media_path(path), target)
        write_json(
            destination / "scenes" / scene.id / "scene.json",
            scene.model_dump(mode="json"),
        )
        print(
            f"Exported scene package to {destination}; point CLEANROOM_DATA_DIR there to replay"
        )


if __name__ == "__main__":
    main()
