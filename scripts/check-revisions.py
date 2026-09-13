"""Check actual splat/collider edit and rollback against an imported asset.

Creates an explicitly labeled temporary scene. This deliberately destructive test
edit is never proposed as a useful restoration and never changes the source scene.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from backend import storage
from backend.models import Edit, Bounds, Revision, Transform

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scene", default="chair-probe")
args = parser.parse_args()
source = storage.read_scene(args.scene)
fixture_id = storage.identifier("mechanics-test")
fixture = source.model_copy(deep=True)
fixture.id = fixture_id
fixture.title = "Temporary edit/rollback mechanics test"
fixture.source_kind = "synthetic_fixture"
fixture.references = []
fixture.video = None
fixture.revisions = [
    Revision(
        id="original",
        label="Test baseline",
        status="baseline",
        created_at=storage.timestamp(),
    )
]
fixture.current_revision = "original"
library = fixture.assets[0].model_copy(deep=True)
library.id = "library-test"
library.initially_visible = False
fixture.assets.append(library)
storage.save_scene(fixture)
output = Path(".artifacts/revision-check")
output.mkdir(parents=True, exist_ok=True)
midpoint = (np.array(source.bounds.minimum) + source.bounds.maximum) / 2
halfsize = (np.array(source.bounds.maximum) - source.bounds.minimum) * np.array(
    [0.3, 0.1, 0.3]
)
candidate = storage.propose(
    fixture_id,
    Edit(
        id="deliberate-test-cut",
        operation="hide_region",
        asset_id=source.assets[0].id,
        reason="Destructive mechanics test, not a restoration",
        evidence=["test fixture"],
        bounds=Bounds(
            minimum=tuple(midpoint - halfsize), maximum=tuple(midpoint + halfsize)
        ),
    ),
)
placement = storage.propose(
    fixture_id,
    Edit(
        id="test-library-placement",
        operation="place_asset",
        asset_id=library.id,
        reason="Test reversible library placement",
        evidence=["test fixture"],
        transform=Transform(position=(0.2, 0, 0)),
    ),
)
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome", headless=True, args=["--use-angle=metal"]
        )
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(
                f"http://127.0.0.1:5173/?scene={fixture_id}&capture=1",
                wait_until="networkidle",
            )
            page.wait_for_function("window.cleanroom?.ready", timeout=90000)
            records = {}
            for label, revision in [
                ("before", "original"),
                ("candidate", candidate.id),
                ("restored", "original"),
            ]:
                page.evaluate(
                    "revision=>window.cleanroom.applyRevision(revision)", revision
                )
                page.evaluate(
                    'async()=>await window.cleanroom.capture("Three-quarter")'
                )
                page.wait_for_timeout(1000)
                page.locator("#viewport canvas").screenshot(
                    path=str(output / f"{label}.png")
                )
                records[label] = page.evaluate("window.cleanroom.diagnostics()")
            probe = page.evaluate(
                "window.cleanroom.probeRegion({minimum:[.25,.25],maximum:[.75,.75]})"
            )
            assert any(sample["hit"] for sample in probe["samples"]), (
                "Expected collider hits beneath the asset"
            )
            arrays = {
                name: np.asarray(
                    Image.open(output / f"{name}.png").convert("RGB"), dtype=np.int16
                )
                for name in records
            }
            changed = float(
                (np.abs(arrays["before"] - arrays["candidate"]).max(axis=2) > 3).mean()
            )
            rollback = float(
                (np.abs(arrays["before"] - arrays["restored"]).max(axis=2) > 3).mean()
            )
            assert changed > 0.0001, "Splat cut must visibly affect the rendered asset"
            assert rollback < 0.0001, "Rollback must restore the original appearance"
            counts = {
                name: next(
                    value["colliderTriangles"]
                    for value in values
                    if value["id"] == source.assets[0].id
                )
                for name, values in records.items()
            }
            assert counts["candidate"] < counts["before"], (
                "Collider cut must remove intersecting triangles"
            )
            assert counts["restored"] == counts["before"], (
                "Rollback must restore collider triangles"
            )
            assert len(page.evaluate("window.cleanroom.metadata().objects")) == 1
            page.evaluate(
                "revision=>window.cleanroom.applyRevision(revision)", placement.id
            )
            assert len(page.evaluate("window.cleanroom.metadata().objects")) == 2, (
                "Placement activates library asset"
            )
            page.evaluate('window.cleanroom.applyRevision("original")')
            assert len(page.evaluate("window.cleanroom.metadata().objects")) == 1, (
                "Rollback hides library asset"
            )
            report = {
                "passed": True,
                "source_scene": source.id,
                "changed_fraction": changed,
                "rollback_difference": rollback,
                "collider_triangles": counts,
                "probe_hits": sum(bool(s["hit"]) for s in probe["samples"]),
                "library_placement_and_rollback": True,
                "scope": "Deliberate mechanics test, not an autonomous repair or quality evaluation",
            }
            storage.write_json(output / "result.json", report)
            print(json.dumps(report, indent=2))
        finally:
            browser.close()
finally:
    shutil.rmtree(storage.scene_path(fixture_id).parent)
