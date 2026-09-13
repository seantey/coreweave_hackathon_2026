# Demo operation and evidence

September 13, 2026. This is a presentation of recorded experiments, not a claim that every experiment was one uninterrupted autonomous run.

## Open the presentation

With the backend on port 8000 and Vite on port 5173, open **http://127.0.0.1:5173/demo.html**. The workspace remains at **http://127.0.0.1:5173/**. The production build includes both pages.

The five chapters show the occupied/corrected panorama, the missed distant person, its targeted correction, the subsequent preservation review, and an earlier rejected 3D edit. Use the comparison slider, chapter buttons, or arrow keys. “Play recorded sequence” advances saved evidence; it does not simulate live tool calls or spend credits. Trace links require access to the private W&B project.

The footer reads current saved reconstruction status. Until `office-clean` exists, its room link explicitly opens the **occupied** `office-textured` reconstruction. Once the clean-input scene exists, the link switches to that scene. A generated room still needs visual and geometric inspection.

## Three-minute walkthrough

1. **0:00–0:25 — Goal and result:** “We want this same office as if nobody were there. Furniture and belongings should survive the cleanup.” Drag the first comparison. Explain that the panorama extends a supplied photo, so unseen surroundings are inferred.
2. **0:25–1:00 — Why a loop:** Show Challenge. “The broad vision model missed this small person. Segmentation plus an enlarged crop disagreed, and we kept that counter-evidence.” Open the localized Weave trace if desired.
3. **1:00–1:30 — Targeted action:** Show Repair. “The agent selected a crop, called the image tool, and inspected the result. During development we added a mask-based composite to preserve surrounding pixels.” The displayed branch includes that assistant-led refinement; do not claim the agent invented the implementation.
4. **1:30–1:55 — Preserve and recheck:** Show Recheck. The subsequent loop requested another correction after a furniture-preservation concern. Final approval is scoped to model-assessed visible image consistency, not ground-truth geometry.
5. **1:55–2:20 — Reject bad changes:** Show Reject. The 3D loop hid a layer, compared matching cameras and rejected the edit because the occupant remained. Measured changes contradict the evaluator’s literal “identical” wording; the target defect nevertheless remained.
6. **2:20–3:00 — Explore:** Open the room. State whether the footer identifies the occupied or clean-input reconstruction. Inspect a chair candidate, toggle Collision and Appearance, and return to the room. These are extracted partial surfaces, not complete articulated chairs or calibrated robotics assets. Close with the useful direction: evidence-driven restoration that can reject its own edits.

## Sponsor usage and boundaries

- **W&B Inference:** GLM-5.3-Flash reviews actual image inputs, reasons about localized evidence, chooses edits, and evaluates results.
- **Weave:** traces those model calls, tool invocations, inputs and decisions. It records evaluations; it does not independently certify that people were removed.
- **fal:** SAM segmentation, Nano Banana image editing, and Hunyuan world generation.
- **Three.js/Spark:** shared viewer foundation for meshes and splats. This office path currently renders textured Hunyuan meshes. Mint/Marble requests failed upstream; do not present the fallback as a Marble splat.

The product contains a source-image correction loop and a 3D inspection/repair loop. Development selected checkpoints and improved tools between runs. No accepted autonomous 3D repair has been demonstrated at this checkpoint. No physics-engine simulation or complete object recovery is claimed. Prior-project rendering/camera ideas were reused; disclose that separately from the code and experiments built here.

## Reproduce the local presentation

After restoring the recorded data directory:

```sh
uv run python scripts/prepare-demo.py
node scripts/demo-check.mjs
node scripts/record-demo.mjs
```

The preparation script deliberately refers to this office experiment’s actual checkpoint IDs and fails if expected evidence is absent. It is a presentation curator, not the generic agent pipeline. The generic implementation is `backend.pipeline` / `backend.cli restore-room`.

The recorder creates `.artifacts/clean-room-imputation-demo.mp4`, a silent recording of actual browser interactions. It uses the available room at recording time; rerecord after the cleaned reconstruction is verified. It starts no model jobs. Its JSON sidecar reports browser errors. Keep this private office media outside Git unless the user explicitly authorizes publication.

## Verification at this checkpoint

41 Python tests pass, including counter-evidence blocking acceptance, exact outside-crop preservation, mask restriction inside the crop, exhaustive uncertainty review, and rejection before world generation. The five-chapter browser check passes without page errors, verifies loaded evidence images and slider behavior, and checks an 800px layout. Production build passes; the existing Spark workspace bundle remains large. These checks establish implementation behavior, not scene reconstruction accuracy.

## Portable private snapshot

```sh
uv run python scripts/package-demo.py .artifacts/recorded-demo-package
```

This packages the chapter images, available office scenes, geometry, references, and a timestamped status snapshot. It excludes credentials and provider job records. To replay on another machine, use the repository with `CLEANROOM_DATA_DIR` pointing to the package directory; start the backend and viewer as usual. The exported presentation labels its status as a recorded snapshot. It is not a resumable provider-job archive. The package contains private office images and is not included in Git.

## Concise project description draft

Clean Room Imputation explores turning an occupied office into the same virtual room without its occupants. W&B-powered agents inspect imagery, challenge broad judgments with localized evidence, request targeted corrections, and recheck preservation; a separate 3D loop compares matching camera views and rejects ineffective scene edits. The prototype demonstrates recorded image correction, partial furniture separation, and rejected 3D repair, with generated hidden geometry explicitly treated as inferred.
