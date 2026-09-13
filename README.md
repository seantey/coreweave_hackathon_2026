# Clean Room Imputation

Reconstruct an occupied office as if nobody were there, preserving its furniture, layout, and visual consistency. The intended system uses agents to inspect a reconstruction, make targeted edits, and check their effects.

**Status — September 13, 2026:** an end-to-end prototype run completed source correction, world generation, chair separation and W&B-traced 3D inspection. The corrected office renders without the prominent occupants, with seven mask-assigned chair parts: four substantial candidates and three small fragments. Partitioning retained all 149,999 triangles and the rendered screenshot exactly. The 3D agent used probes, isolation and another camera to resolve a suspected person remnant as furniture, then stopped without editing. Warped surfaces, incomplete chairs and other reconstruction defects remain; no accepted autonomous 3D repair or physical-geometry accuracy is claimed. The office uses a disclosed Hunyuan fallback because Marble generation failed through Mint.

**Current target gap:** the requested immersive Marble Gaussian-splat office has not been generated. The Hunyuan result does not satisfy that visual target. Mint OAuth works, but office generation failed in its upstream preview provider with HTTP 403 / exhausted balance. An unrelated prior-project scene was mistakenly imported for testing and presented as the viewer link; it has been removed along with its dependent artifacts and test. Do not reuse other projects’ scenes. Generic virtual-probe controls remain, but their synthetic geometry tests do not validate this office’s collision quality.

Read [the build brief](docs/build-brief.md) for user intent, the proposed technical approach, evaluation questions, and known limits. Coding agents should also read [AGENTS.md](AGENTS.md).

**Demo:** open `/demo.html` on the local viewer for six recorded chapters, before/after comparisons, detector counter-evidence, a rejected 3D edit, and the completed clean-input reconstruction. See [the demo walkthrough](docs/demo.md). A short screen recording and private replay package are available locally under `.artifacts/`; private media is excluded from Git.

This directory is the self-contained application and intended GitHub repository. Keep runtime code, scripts, dependencies, tests, and application documentation here. The parent workspace contains brainstorming, event research, local credentials, and private media; those are not runtime dependencies of an independent checkout. Accept configurable input and credential paths rather than hard-coding parent paths.

See the [agent runbook](docs/agent-runbook.md) for setup, implemented commands, evidence, and replay. Never commit populated credentials, raw captures, or temporary service response files.
