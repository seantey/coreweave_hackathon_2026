# Demo presentation

Updated September 13, 2026 following the user's request to dramatically simplify the site.

Open **http://127.0.0.1:8000/** (production) or **http://127.0.0.1:5173/** (development). `/demo.html` opens the same presentation. A plain `?scene=office-rebuild` link also opens the presentation; the scene selector belongs to the explicit workspace or immersive routes.

The page shows one draggable comparison with two choices:

- **Remove people:** recorded source panorama before and after image cleanup. Extended and exposed surfaces are inferred.
- **Repair furniture:** recorded table-side views of the original office reconstruction and the accepted table/chair repair, using the same camera. This is the initial selection when that evidence is available.

“How it works” expands a four-step diagram: Inspect → Repair → Check → Keep or retry. It includes a short distinction between recorded assistant-led 3D repairs and W&B-supported review, plus the actual Weave repair trace. It does not claim a live autonomous run. The page retains one short geometry limitation, with full technical evidence in [the repair record](direct-office-repair.md).

“Explore in 3D” opens `/?immersive=1&scene=office-rebuild`. “Workspace” opens `/?workspace=1&scene=office-rebuild` with the existing controls. Capture routes (`?capture=1`) still load the renderer directly. The simple landing page loads its own small bundle and does not initialize the 3D renderer.

## Operation and checks

Run `npm run build` for the backend-served production page. Vite proxies API/media requests to the backend on port 8000. The existing data directory and prepared `data/demo/manifest.json` supply the recorded evidence; no model calls run when viewing the presentation.

`node scripts/demo-check.mjs` checks the production landing page, explicit demo page and prior scene link, both image comparisons, slider, loop disclosure and mobile overflow. `node scripts/direct-office-check.mjs` checks original/accepted scene revisions in the explicit workspace. `node scripts/record-demo.mjs` records the simplified comparisons and loop explanation from the development server without starting inference.

The backend offers the latest furniture comparison only when its scene and both captures exist. Historical portable snapshots retain their recorded source comparison and snapshot scene; they do not imply that they contain the later repairs. The six-chapter manifest and old private video are historical evidence, not the current presentation. Do not describe an existing older video as a recording of this redesign.

The actual office still uses a Hunyuan room with office-derived furniture splats and colliders. It is not a completed Marble reconstruction or a validated physical digital twin. Other projects' scenes must never be used as demo content.
