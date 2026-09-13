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

This returns 25 ray samples with image coordinates and nearest collider intersections. The loop may request one such targeted probe. Missing hits mean unknown geometry, not free space; hits may belong to a wall behind an unmodeled person. This is geometric inspection, not automatic segmentation.

An image box does not define a 3D edit. The browser tool `window.cleanroom.pick(x,y)` accepts normalized image coordinates and returns a collider intersection when one exists. That intersection is only as reliable as collider alignment. `window.cleanroom.metadata()` returns scene/camera metadata. Do not infer accurate geometry from a missing intersection.

## Propose, verify, decide

An edit JSON contains a unique `id`, `operation`, `asset_id`, `reason`, and nonempty `evidence` list, plus operation-specific fields:

- `hide_region`: `bounds: {minimum:[x,y,z],maximum:[x,y,z]}`. Scoped to a splat asset; removes collider triangles intersecting that region. This is coarse triangle removal, not a watertight Boolean repair.
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

This spends W&B inference credits. It captures two views, requests a structured observation and proposal, can request one additional existing view, applies a candidate, and evaluates matched before/after views. When available, another camera is withheld from the proposal and added for regression checks. Mechanical checks reject mismatched cameras or unchanged images before paid evaluation. The evaluator must explicitly report defect resolution, furniture preservation, no new damage, and no unresolved uncertainties to accept. Original source references accompany the comparison. Malformed or inconclusive assessments reject the candidate. A rejected edit remains rejected while the next bounded pass sees its evaluation and may propose a different hypothesis. Identical spatial proposals within a run stop without another paid evaluation. The current loop does not autonomously invoke asset generation or create arbitrary new camera poses yet.

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

- Eighteen local tests pass, including rejection/retry behavior with **mocked** model responses. This does not establish vision-model reliability.
- An actual rendered mechanics test cut the chair splat and reduced collider triangles from 269,740 to 227,452. Rollback restored 269,740 triangles and the original screenshot exactly. It also verified reversible activation of a library asset. The deliberate test cut was not an agent-discovered defect or a useful restoration. Artifacts are local under `.artifacts/revision-check/`.
- [A real one-pass inspection trace](https://wandb.ai/s-rekaitai/clean-room-imputation/r/call/01a099e4-2700-7a98-b118-f6011c7b8759) completed with W&B image inference and image-bearing Weave inputs. It stopped without an edit because the input was an isolated chair rather than the office. This ran prompt v3; v4 adds library placement and rejected-edit feedback, which have local mechanical tests but no live room evaluation yet.
- Earlier live attempts exposed an in-operation flush hang and an exhausted output allowance. The flush moved outside the traced operation; the output allowance increased to 4,096, and the observation request became more concise. Neither failed attempt changed the accepted scene.
- Room restoration, segmentation accuracy, object replacement quality, and reliable detection of remaining occupants remain unverified. Mint/Marble requires reauthentication before the intended office-generation path can run.
