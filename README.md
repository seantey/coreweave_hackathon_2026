# Clean Room Imputation

Reconstruct an occupied office as if nobody were there, preserving its furniture, layout, and visual consistency. The intended system uses agents to inspect a reconstruction, make targeted edits, and check their effects.

**Status — September 13, 2026:** the local app renders a textured office reconstruction, separates six chair candidates with individual colliders, captures inspection views, and runs W&B-traced source-completion and 3D inspection loops. Chair partitioning preserved every triangle and the rendered screenshot exactly. The source loop has generated corrections and caught a remaining person through a segmentation/crop cross-check after the broad vision model missed it. A fully restored office and an accepted autonomous 3D repair are still unverified. Marble generation is unavailable through the current Mint route; the live office uses a disclosed Hunyuan fallback.

Read [the build brief](docs/build-brief.md) for user intent, the proposed technical approach, evaluation questions, and known limits. Coding agents should also read [AGENTS.md](AGENTS.md).

**Demo:** open `/demo.html` on the local viewer for recorded before/after comparisons, actual detector counter-evidence, and a rejected 3D edit. See [the demo walkthrough](docs/demo.md). The latest corrected panorama passed the visible-input evaluation and was submitted for world generation; this does not yet establish a verified restored 3D room.

This directory is the self-contained application and intended GitHub repository. Keep runtime code, scripts, dependencies, tests, and application documentation here. The parent workspace contains brainstorming, event research, local credentials, and private media; those are not runtime dependencies of an independent checkout. Accept configurable input and credential paths rather than hard-coding parent paths.

See the [agent runbook](docs/agent-runbook.md) for setup, implemented commands, evidence, and replay. Never commit populated credentials, raw captures, or temporary service response files.
