# 3D demo presentation

Updated September 13, 2026. The user's latest direction is to focus the demo on 3D simulation/exploration, not people-removal still images. Keep the interface simple and use one primary URL: **http://127.0.0.1:8000/**.

The page opens the actual office reconstruction in an embedded Three.js/Spark viewer. Drag to look, use WASD to move and Q/E to change elevation. On-screen movement buttons also work. Before repair / After repair switches the actual scene revision while retaining the camera position. Reset view returns to the initial office camera; Orbit view offers an alternative navigation mode. Full screen expands the viewer.

The optional Quick comparison tab shows matched-camera renders of the original versus repaired table and chairs. It does not show people-removal images. The compact expandable diagram explains Inspect → Repair → Check → Keep or retry, with a short account of the actual assistant-led work and a Weave trace. There is no simulated live agent activity.

## Scope and review findings

The previous simplification overemphasized static image cleanup and hid movement behind a separate page and “Pilot virtual probe.” Immersive mode also hid revision controls. A browser review reached the office but crashed after entering collision-probe mode and pressing W. The exact crash cause was not isolated; collision navigation remains experimental.

The presentation now uses free flight, without building or consulting the collision octree. This is deliberately labeled exploration, not validated physics. Reconstructed furniture has paired collision meshes, but the demonstration does not establish physical accuracy or robust collision navigation. The workspace retains its experimental probe tool.

The room remains the office-derived Hunyuan reconstruction with table/chair splats and colliders. It is not a completed Marble world. The damaged background has not been repaired by the UI changes. See [the direct office repair record](direct-office-repair.md) for accepted/rejected work and source provenance. Never use other projects' scenes as demo content.

## Implementation and checks

`npm run build` updates the backend-served page. Vite on port 5173 is the development equivalent. The root and `/demo.html` use the same demo component. The embedded renderer uses `?immersive=1&presentation=1&scene=office-rebuild`; the explicit workspace uses `?workspace=1&scene=office-rebuild`. Capture routes remain unchanged. These are internal modes, not additional primary demo URLs.

`node scripts/demo-check.mjs` checks actual embedded office rendering, keyboard and on-screen movement, revision changes at a fixed position, comparison, loop disclosure and mobile layout. `node scripts/direct-office-check.mjs` checks original/accepted revisions in the workspace. `node scripts/record-demo.mjs` records actual 3D exploration and comparisons from the development server without running inference.

Saved evidence requires the local data directory and prepared demo manifest. Older snapshots may lack the repaired office; the quick comparison is hidden if repair evidence is unavailable. Historical six-chapter manifests and older videos remain historical records and must not be described as recordings of this presentation.
