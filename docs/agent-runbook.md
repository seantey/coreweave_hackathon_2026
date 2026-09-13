# Reproducing the agent workflow

This runbook describes implemented interfaces. It does not claim that an occupied office has already been restored. Read `build-brief.md` for the goal and evaluation limits.

## Setup

Use Node 22.12+ and Python 3.11+. Install dependencies with `npm ci` and `uv sync`. The lockfiles capture the tested versions. Chrome must be installed for the capture tool; it uses Playwright's `channel="chrome"`.

Copy `.env.example` to a private `.env` and populate keys, or set `CLEANROOM_ENV_FILE` to an existing local credential file. `CLEANROOM_DATA_DIR` selects the scene/asset/evidence directory (default `./data`). Run commands from this repository directory.

Start two processes:

```sh
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
npm run dev
```

Open `http://127.0.0.1:5173`. This is a local development application, not a publicly secured multi-user service. Keys stay in the backend. The viewer proxy routes `/api` and `/media` to port 8000. `CLEANROOM_VIEWER_URL` overrides the URL used by headless capture.

## Import existing evidence

```sh
uv run python -m backend.cli import-scene \
  --id office --title 'Office reconstruction' \
  --splat /path/to/room.ply --collider /path/to/collider.glb \
  --reference /path/to/reference.jpg --video /path/to/preview.mp4
```

Input files are copied into the configured data directory; originals remain untouched. Use `--object-probe` for an isolated object test. Never label that as an office. Binary float32 Gaussian PLY supports automatic camera framing from robust center bounds. Supply `--bounds '[minX,minY,minZ,maxX,maxY,maxZ]'` for other formats or explicit framing. Bounds are not measured physical dimensions. Camera names initially indicate generic viewing directions, not verified semantic object front/back.

For a SAM object with paired GLB and PLY, coordinate frames may differ. `align-sam` compares metadata quaternion conventions and proper axis rotations against sampled geometry:

```sh
uv run python -m backend.cli align-sam office /path/to/sam-result.json
```

The leading metadata candidates are refined with trimmed rigid ICP. This is empirical alignment, not proof of exact registration or physical scale. Inspect the overlay from several angles and preserve residuals. Appearance and collision visibility can be toggled independently. The tool only handles the tested untransformed single-mesh GLB form, and calibration must precede scene edits.

## Inspect before editing

```sh
uv run python -m backend.cli capture office --camera Front
```

Capture opens a fresh browser, loads the selected scene/revision, sets a saved camera, and stores an image plus camera/projection matrices and asset bounds. Check that the image actually contains the asset. The browser smoke test checks pixel variation to catch an empty canvas that otherwise appears successfully initialized.

To sample collider geometry below an image region:

```sh
uv run python -m backend.cli capture office --camera Front --region '[0.3,0.3,0.7,0.7]'
```

This returns 25 ray samples with image coordinates and nearest collider intersections. The loop can request targeted probes during its bounded inspection sequence. Missing hits mean unknown geometry, not free space; hits may belong to a wall behind an unmodeled person. This is geometric inspection, not automatic segmentation.

An image box does not define a 3D edit. The browser tool `window.cleanroom.pick(x,y)` accepts normalized image coordinates and returns a collider intersection when one exists. That intersection is only as reliable as collider alignment. `window.cleanroom.metadata()` returns scene/camera metadata. Do not infer accurate geometry from a missing intersection.

## Propose, verify, decide

An edit JSON contains a unique `id`, `operation`, `asset_id`, `reason`, and nonempty `evidence` list, plus operation-specific fields:

- `hide_region`: `bounds: {minimum:[x,y,z],maximum:[x,y,z]}`. Scoped to a splat or mesh asset; removes matching visual/collider triangles intersecting that region. This is coarse triangle removal, not a watertight Boolean repair.
- `hide_asset`: hides an independent asset and its collider. Inspect its contents first; a layer label alone is insufficient. Cannot hide the last visible source asset.
- `transform_asset`: `transform: {position:[x,y,z],rotation:[rx,ry,rz],scale:[sx,sy,sz]}`. Euler angles in radians; moves the whole independent asset, not one baked-in object.
- `place_asset`: a transform and an existing inactive library asset ID. Activates that asset only in the candidate revision; rollback hides it again.
- `add_surface`: a transform, positive `size:[x,y,z]`, and `color`. Creates a plain box; only appropriate for evidence-supported simple completions.

```sh
uv run python -m backend.cli propose office /path/to/edit.json
uv run python -m backend.cli capture office --revision REVISION_ID --camera Front
uv run python -m backend.cli decide office REVISION_ID --accept --reason 'Observed correction with preserved surroundings'
```

Omit `--accept` to reject. Original and accepted scenes stay unchanged until an explicit decision. Stale candidates cannot overwrite newer accepted work. Oversized erasures and invalid transforms are rejected. A size limit is only a guardrail, not semantic validation.

Register a reusable asset before proposing placement:

```sh
uv run python -m backend.cli register-asset office --id replacement-chair \
  --label 'Reference chair' --kind splat --path /path/to/chair.ply \
  --collider /path/to/chair.glb --provenance 'Reconstructed from source; hidden surfaces unverified'
```

Registration adds it to the library without changing the original view. If its collider uses a different frame, supply a previously verified `--collider-matrix` as a JSON list of 16 column-major values. Registration does not establish correct scale, placement, identity, or appearance. Propose `place_asset` with grounded placement and inspect the candidate.

The automated version is:

```sh
uv run python -m backend.cli loop office --passes 2
```

This spends W&B inference credits. It captures two views, requests a structured observation and proposal, can request further inspection tools, applies a candidate, and evaluates matched before/after views. When available, another camera is withheld from the proposal and added for regression checks. Mechanical checks reject mismatched cameras or unchanged images before paid evaluation. The evaluator must explicitly report defect resolution, furniture preservation, no new damage, and no unresolved uncertainties to accept. Original source references accompany the comparison. Malformed or inconclusive assessments reject the candidate. A rejected edit remains rejected while the next bounded pass sees its evaluation and may propose a different hypothesis. Identical spatial proposals within a run stop without another paid evaluation. The current v6 observation interface supports up to six tool requests per pass in model-selected order: another saved view, a new camera pose inside scene bounds, an isolated-layer view, or a geometry probe. Identical inspection requests stop rather than consume another call. Whole-asset removal requires actual isolation evidence in that pass, not just a detector label. Isolated views inform diagnosis but are excluded from the full-scene before/after comparison. It does not autonomously invoke asset generation yet.

`reconstruct IMAGE --box '[x_min,y_min,x_max,y_max]'` is a separate paid fal tool. It submits once, saves the request id before polling, and downloads assets. If polling times out, use saved job information to resume rather than paying for a duplicate request. Generated output still needs inspection and import/placement; generation is not scene repair by itself.

## Evidence and replay

- `scenes/SCENE/scene.json`: portable assets, cameras, and revision history.
- `scenes/SCENE/events.jsonl`: observations, prompts, proposed edits, decisions, captures, and failures.
- `captures/VIEW/`: screenshot and camera record.
- `runs/LOOP.json`: bounded-loop outcome.
- Weave: decorated observations, evaluations, and loop calls, with the reviewed images, final model content, and usage. Flush occurs after the root traced call ends to avoid waiting on its own completion. Credentials and internal reasoning are not returned by the provider adapter.

Keep original goal criteria stable across comparison. `PROMPT_VERSION` identifies the evaluation prompt revision. Record changes rather than treating newly inflated scores as improvement.

```sh
uv run python -m backend.cli export office /path/to/new-export-directory
```

Export copies scene assets, references, and edit history into a replayable package. It does **not** bake all edits into a new monolithic PLY/GLB. Set `CLEANROOM_DATA_DIR` to that package to replay it. Review reference-media sharing before publishing a package.

## Verification

```sh
uv run pytest
npm run build
npm run test:browser
uv run python scripts/check-revisions.py --scene chair-probe
```

The browser check currently expects the local `chair-probe` scene and produces ignored screenshots in `.artifacts/`. Unit tests use temporary data. These checks establish application mechanics; visual model reliability and real-room success require separate evidence.

## Evidence checkpoint — September 13, 2026

- Twenty-nine local tests pass, including rejection/retry behavior with **mocked** model responses. This does not establish vision-model reliability.
- An actual rendered mechanics test cut the chair splat and reduced collider triangles from 269,740 to 227,452. Rollback restored 269,740 triangles and the original screenshot exactly. It also verified reversible activation of a library asset. The deliberate test cut was not an agent-discovered defect or a useful restoration. Artifacts are local under `.artifacts/revision-check/`.
- [A real one-pass inspection trace](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a099e4-2700-7a98-b118-f6011c7b8759) completed with W&B image inference and image-bearing Weave inputs. It stopped without an edit because the input was an isolated chair rather than the office. This ran prompt v3; v4 adds library placement and rejected-edit feedback, which have local mechanical tests but no live room evaluation yet.
- Earlier live attempts exposed an in-operation flush hang and an exhausted output allowance. The flush moved outside the traced operation; the output allowance increased to 4,096, and the observation request became more concise. Neither failed attempt changed the accepted scene.
- Room restoration, segmentation accuracy, object replacement quality, and reliable detection of remaining occupants remain unverified. Mint OAuth now works, but two office requests failed in its upstream fal preview provider with an exhausted-balance error. The supplied fal account works independently. A first Hunyuan World output was rendered but rejected as a faithful room: the endpoint accepted an ordinary photo even though reconstruction expects a panorama. A corrected panorama-based job is processing.


## Checkpointed provider jobs and remote worlds

`segment IMAGE --prompt person` submits a fal SAM 3 image-segmentation request, validates returned mask dimensions, and saves model scores, masks, and the request ID. The actual office photo returned 19 candidate masks, including potentially overlapping detections; that is not a verified count of people.

`review-segmentation data/segmentation/JOB/segmentation.json` reviews source crops and mask overlays through W&B image inference and Weave. Each batch is checkpointed. Only explicit person-only decisions enter the candidate mask union; the source remains unchanged. The live review exposed JSON-container variation and output exhaustion. Container normalization preserves strict decision validation; 8,192 tokens also proved insufficient. W&B documents GLM-5.3-Flash reasoning as always on. The allowance is now 32,768 tokens with a 600-second read timeout. Full office-mask review completed, retaining 13 person-only candidates and withholding six; these are model judgments, not independently established segmentation accuracy.

`resume-fal data/PATH/job.json --timeout 600` resumes a queued request without another submission. Timeouts preserve its handle. Never submit a duplicate merely because a polling process ended.

`import-mint-world MANIFEST --id office --title 'Office reconstruction' --reference IMAGE` imports the actual remote RAD contract and downloads its paired collider. Use `--fixture` for prior content used only to test integration. Initial cameras look along coordinate axes at the reconstruction origin; they are not recovered source-camera calibration. Remote RAD remains dependent on its provider URL in exported packages.

The optional `generate-marble SOURCE --prompt TEXT` and `resume-marble OPERATION` commands use a separate `WORLDLABS_API_KEY`. Their protocol has mocked tests only. Mint authentication and credits cannot substitute for this key. Image/video inline inputs are limited to 10 MB by this adapter; preserve originals when preparing derivatives.


## Layered world import and inspection

`import-hunyuan JOB_JSON --id office --title 'Office reconstruction' --reference SOURCE_IMAGE` consumes a completed Hunyuan World job. The importer validates 2:1 panorama dimensions, retains downloaded originals, converts mesh layers to lighter GLBs with panorama textures, and applies the official viewer orientation. Simplification can lose appearance detail. Background and distant-shell layers are protected from removal. Live import completed. Naive vertex-color simplification looked poor; current imports preserve appearance with projected panorama textures and seam-aware UVs.

`capture office --camera Forward --isolate layer-0` inspects a single layer without changing accepted scene state. Model labels are hypotheses; people and furniture can share a layer. Browser checks on the rejected projection experiment confirmed single-layer visibility and pixel-exact restoration after exiting isolation. This is a mechanics result, not an accepted repair.

The UI's Capture view now saves the current orbit-camera pose before headless capture. Saved camera names cannot be overwritten, preserving prior evidence definitions. Headless images use a fixed viewport, so framing aspect ratio can differ from the interactive panel.

A live assistant-led 2D preparation experiment used built-in image editing, W&B comparison, enlarged-crop inspection, a targeted correction, and the same comparison prompt again. The first judgment requested revision; the second reported no definite people, preserved visible furniture and architecture, and recommended provisional use while retaining background uncertainty. This is not the deployed 3D loop and does not establish a completed office. Traces: [first comparison](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09b7f-5d1a-7e42-90d3-73d6b2b52434), [second comparison](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09b85-c436-7757-8d85-803c103fbd03), [mask review](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09b7e-609d-7766-9682-360cd195e60d).

SAM image results sort masks and metadata together by score; metadata `index` identifies the pre-sort detection, not the returned mask-array offset. Preserve both indices. This was verified against actual mask extents and covered by a regression test. Source images are copied into the segmentation evidence directory for portable replay.


For individual SAM object exports, use `align-sam SCENE --canonical`. Their normalized coordinates differ from the combined scene; applying the combined-scene scale/translation to an individual pair produced residual 0.1546, while canonical-frame fitting reduced it to 0.0124 in unverified units on one office chair. This is empirical alignment, not physical calibration. An initial Z-up splat was rotated into the viewer's Y-up frame for inspection; inspect each imported asset rather than assuming one convention universally.

The expanded region-removal test now covers actual mesh appearance and collision geometry: a deliberate fixture cut removed 7,314 of 99,999 collider triangles and changed 0.128% of pixels; rollback restored both exactly. The splat rollback test continues to pass. These fixtures do not represent successful office repairs.


`partition-layer SCENE ASSET SEGMENTATION_JSON PANORAMA` partitions a Hunyuan mesh before any edits. It verifies pixel equality against both the segmentation source and the imported layer source, projects triangle centers using Hunyuan's spherical camera convention, and assigns every triangle exactly once. Overlapping masks use confidence order. All original triangles remain; this creates independently addressable partial objects without claiming complete hidden geometry or improved reconstruction. Original scene and partition records are saved per layer. Coordinate and triangle-conservation tests pass; live office partition retained all 198,192 triangles and the Forward screenshot was pixel-identical. Six chair candidates received independent geometry and colliders.

Each object row now has an Inspect control to isolate that asset and Show room to restore the full revision. This is a view operation, not a saved edit. Appearance visibility covers meshes and splats. The viewer prefers a scene named `office` when available.

## Source completion before reconstruction

`complete-image SOURCE --id RUN_ID --initial-candidate CANDIDATE --max-edits 3` runs a separate, real tool loop: W&B compares source and candidate using fixed `source-preservation-v1` criteria, a planner proposes a targeted correction, fal Nano Banana 2 edits it, and the same evaluator checks the result. Source, judgments, prompts, queue handles and candidates are checkpointed under `data/completion/RUN_ID/`; rerun the same command to resume. A run ID must continue to refer to the same input. This is image preparation, not a 3D collision-quality verdict. The app shows its history separately.

`reconstruct-completion RUN_ID --scene SCENE_ID --reference ORIGINAL_PHOTO` requires an explicitly accepted completion and an exact 2:1 panorama, then checkpoints Hunyuan generation and imports its world. It does not declare the new geometry validated. Run scene inspection and object partitioning on the actual output. The original photo remains evidence; a generated panoramic extension is inferred, not recovered camera coverage.

The actual Hunyuan occupied-panorama result detected only two people. Its supposedly completed background visibly retained several occupants. The new source-completion loop correctly rejected that image for remaining people; correction is processing. This is a recorded provider failure, not an authored test defect. The corrected world archive transfer is ongoing; byte-range downloads now resume individual parts and reject changed archive versions or incorrect server ranges. Three download tests and two completion feedback/checkpoint tests pass, bringing local tests to 34. The Nano Banana 2 request follows the [official fal schema](https://fal.ai/models/fal-ai/nano-banana-2/edit/api); live editing success is not yet established.


### Current live findings

The `office-textured` scene renders the occupied panoramic office and its extracted chair candidates; `office` retains the earlier low-quality vertex-color representation for evidence. Neither is a cleaned office. The UI prefers `office-clean` when available, then `office-textured`, then `office`. Source video is attached as an additional unregistered viewpoint. Object inspection automatically frames the selected asset; extraction can leave missing legs or hidden surfaces. Do not call these complete furniture models.

The source-completion run generated a first candidate with most occupants removed, but a background person remained. A broad VLM verdict claimed absence with uncertainty; its planner also mistakenly stopped. SAM 3 detected one residual person, and a localized, enlarged mask review confirmed head and torso. The resumed planner reversed its conclusion and requested a targeted correction. A later audit retained a bag as a belonging while identifying the same missed person. Whole-panorama edits can fail on tiny targets; the planner now has an optional normalized `crop_region` tool that edits a larger crop and composites it back with unchanged outside pixels. These additions are engineering responses to observed failures, not claims that the current candidate passed.

Person audits run when broad review claims absence, and can block approval. Their crop sheets, detector boxes, classifications, and alternate plans are preserved separately from the original broad verdict. Original criteria remain `source-preservation-v1`; additional evidence does not overwrite old judgments. Exact echoed version metadata is normalized without relaxing verdict types. Source/run mismatches are rejected.

The first live 3D loop inspected two layers, then failed edit validation because the model returned null for an irrelevant color field. No scene changed. The v6 loop normalizes that unused default and retains prior inspection findings so the model can explicitly address contradictions such as calling an asset person-only while acknowledging a fused chair. It is running again. [First office inspection trace](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a09bc4-fa19-73bc-ab36-8cfe3ae7f462).
