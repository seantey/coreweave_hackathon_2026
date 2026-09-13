# Direct office repair — September 13, 2026

The user asked the assistant to restart its reasoning and perform the inspect/edit/retest loop itself. This record describes that direct work. It is not a claim that the deployed GLM loop independently discovered or executed these repairs.

## Current result

Open `http://127.0.0.1:8000/?scene=office-rebuild`. The latest accepted revision is `revision-31257761382b`: a continuous folding table plus two reconstructed folding chairs replace the bent tabletop and fragmented chairs. The laptop lid is retained. Table and chair splats have paired colliders. Use **View original** and **View accepted**, then the **Table side** camera to compare the actual scene revisions.

This is a fresh repair branch using the existing **office-derived Hunyuan geometry as a hypothesis**, not a new full-room generation. The supplied office photo was reexamined directly. No other project's assets, scenes or calibration were used. The original `office-clean` scene remains intact. The new default is `office-rebuild` when present. The six-chapter `/demo.html` records the earlier experiments and has not been rewritten to imply it includes this run.

The office remains visibly rough: background surfaces stretch when the camera moves, other chairs are incomplete, thin remnants remain near the repaired area, and the foreground display table/belongings are badly reconstructed. Hidden surfaces and dimensions are inferred. No Marble office, globally correct digital twin or complete autonomous repair product is claimed.

## Actual loop and rejected attempts

1. Compared the supplied `work/media/reference.jpg` with the actual office capture. Identified the curved black folding tabletop and fragmented foreground chairs. Created `office-rebuild` from the office scene, retaining the existing geometry and source references without asserting accuracy.
2. Captured **Table** at position `[0, 0.1, 0.35]`, target `[0, -0.65, -1.1]`, FOV 75. A SAM prompt `black folding table tabletop` returned no masks. A second prompt `table` returned five. Directly inspected mask 1, which selected the curved top. These are separate preserved requests under `data/segmentation/office-rebuild-table` and `office-rebuild-tables`.
3. Proposed planar correction of 22,435 selected vertices in `layer-1`, preserving other vertices and reference rays. Rejected `revision-387238e8f55c`: the result created a visible tear beside the laptop. A refined mesh/texture variant, `revision-e36deec20279`, still failed and was rejected. A zero height range is not sufficient evidence of a good repair.
4. Reconstructed the actual table from the supplied office photo through fal SAM 3D Objects, with box `[330,550,818,796]`, prompt `table`, seed 42 and textured GLB enabled. It returned a Gaussian PLY and mesh. Files and resumable job are under `data/repairs/office-table-reconstruction`. Imported as `office-table-object`, inspected it, and fitted its GLB to the splat; sampled alignment residual was approximately 0.00685 in unverified units.
5. Removed 47,771 mask-selected triangles from the old table/desk layer, retaining 102,228 surrounding triangles and the material. Placed the regenerated table. The first replacement was too large. W&B's image reviewer recommended acceptance while acknowledging scale and contact uncertainty; the assistant did not treat that verdict as sufficient.
6. Collider picks and an isolated view showed the laptop and the draped tabletop smear were in `layer-0-remainder`, not the layer labeled `desk, monitor`. A local removal box `[-0.18,-0.22,-0.35]` to `[-0.04,-0.13,-0.25]` removed the smear while retaining the lid. Asset labels must not substitute for isolation and geometric evidence.
7. Reduced the table footprint. A nonuniform root-scale attempt visibly misplaced the splat and was rejected. The installed Spark transform implementation averages the three decomposed scales (`dist/spark.module.js`, `updateFromMatrix`), so the paired mesh and splat can diverge under nonuniform root scaling. New `place_asset`/`transform_asset` proposals for splats now require uniform scale.
8. Baked the needed vertical stretch into the table's Gaussian centers **and covariance matrices**, and composed the identical affine matrix with its collider registration. Used uniform root scale. The inferred local floor was approximately Y `-0.37861`, tabletop anchor `-0.1821`, and baked vertical factor approximately `2.21622`. These are fitting parameters for this reconstruction, not measured office dimensions. Accepted `revision-928e0de84372` after original, offset and independent side-view review.
9. Inspected the existing `chair-probe`, which was generated earlier from this same supplied office photo. Its complete-looking folding-chair geometry was preferable to the torn foreground parts. Restored canonical upright orientation using the collider registration rotation; the high backrest lay toward canonical negative Z, so a pi yaw faced the chairs toward the table. Reused it for both visually similar folding chairs, replacing `layer-0-object-00` and `layer-0-object-01`. Inferred height 0.24 and floor Y -0.385; centers approximately X/Z `[-0.155,-0.22]` and `[0.03,-0.20]`. Accepted `revision-31257761382b` after Table, Table side and Forward inspection.

The table model's hidden leg structure and the reused chair's hidden surfaces are generated guesses. Local acceptance means the inspected replacement improves the visible broken geometry while retaining the furniture's role and approximate placement. It does not establish exact source recovery.

## Evidence and tools

Local records:

- `data/repairs/table-replacement/`: trimmed mesh, placement variants, W&B review and captures.
- `data/repairs/table-grounded/`: baked splat, affine parameters, accepted decision, main and side captures.
- `data/repairs/office-chairs/`: placement report, captures and accepted decision.
- `data/scenes/office-rebuild/scene.json`: all rejected and accepted revisions, original assets and new inactive/placed assets.
- `data/scenes/office-rebuild/events.jsonl`: direct decisions and observations.
- `.artifacts/`: operator scripts used during this exact experiment, including `reconstruct_office_table.py`, `place_office_table.py`, `ground_office_table.py`, `replace_office_chairs.py`, and intermediate diagnostics. These are local experiment scripts tied to recorded IDs, not a general unattended pipeline. Do not rerun them blindly against an already modified scene.

Reusable committed operations:

- `backend.surface_repair.propose_planar_surface` / CLI `planar-surface`: mask-selected planar candidate, not automatic acceptance. Its first live office applications were rejected; retain that limitation.
- `backend.splat_deformation.stretch_splat`: bakes positive axis scaling into centers and full covariances, preserving color and opacity. Apply the returned column-major affine matrix to the collider registration too. Keep originals and use a new asset/revision.
- Existing segmentation, SAM alignment, revision, capture and decision tools. Review masks at their exact source viewport, inspect assets before replacement, retain camera poses, and inspect another viewpoint before accepting.

To repeat the approach on another scene, discover its own mask, coordinate frame, floor, orientation, scale and replacement transform. None of the office-specific numeric parameters above are universal defaults.

Actual Weave traces:

- [First planar candidate](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09c1c-a168-79dd-91b6-1dce07e1cf2c)
- [Table reconstruction from original photo](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09c1e-5aab-7507-9500-7a8e4a80f981)
- [W&B review of oversized candidate](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09c21-dafb-7fb0-bb51-0666c5186654)
- [Paired table grounding](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09c24-f442-7811-a80b-5d7b40499409)
- [Direct table decision with before/after images](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09c26-f2c9-76fe-9c87-86a41a80164f)
- [Direct chair decision with before/after images](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09c29-918d-7315-b341-8345512beb11)

## Verification boundary

45 Python tests pass, including source preservation during planar candidate creation, transformed Gaussian covariance correctness, unchanged appearance attributes, and rejection of nonuniform splat root placement. Actual browser captures raise on page errors and verify requested scene/revision. These tests establish operation mechanics; visual acceptance above was the assistant's direct review. The deployed GLM loop still does not invoke the new regeneration/grounding sequence itself.

The production browser check `node scripts/direct-office-check.mjs` passes for the saved local office: new table/chairs appear in the accepted revision, the original toggle restores the original assets, and returning to accepted restores the new objects without page errors. Production build passes. `.artifacts/office-direct-repair-package` contains a private scene replay export; it includes geometry and revision state, not the complete provider/capture audit archive.

## Foreground cleanup follow-up

The current accepted revision is now `revision-8347296775c6`. The user explicitly requested removal of the floating central chunk, particularly in the collision view. Collider picks identified the main chunk in the background `layer-2`, not the regenerated furniture. The source photo shows foreground display-table contents that had been projected into a malformed central obstruction.

A first local excision (`revision-621cb646f553`) left spikes and gaps around an inferred floor rectangle and was rejected. A second candidate (`revision-3110165d9171`) enlarged the region and triangulated its actual floor boundary; it was superseded by the combined cleanup because wireframe inspection exposed old table remnants in `desk-without-tabletop` and lower fragments in `layer-0-remainder`.

The final cleanup replaces the affected background and desk layers with separately saved paired appearance/collision meshes. It retains all table/chair replacement assets and transforms, removes the old table's residual geometry, and preserves the laptop above the removal region. The background mesh changes from 628,283 to 258,517 triangles; the already-trimmed desk mesh changes from 102,228 to 19,953. These counts describe geometry removal, not a quality score. The floor texture is still stretched and the wider room remains distorted.

Actual reports, decisions and three-camera appearance/collider captures are under `data/repairs/foreground-cleanup-final/`, with rejected/intermediate evidence under `foreground-blob/` and `foreground-blob-v2/`. The primary demo loads the accepted revision. Its quick comparison reads `data/demo/repair-comparison.json` only when that record matches the current accepted scene revision.

`scripts/repair-office-foreground.py` preserves the exact reviewed geometric procedure as an office-specific candidate generator. It requires the pre-cleanup data and refuses duplicate execution. It is not a general defect detector and does not accept its own output. Background protection is retained on the original asset; this direct, reversible replacement was specifically authorized by the user's request. Do not generalize that authorization to unrelated protected geometry.
