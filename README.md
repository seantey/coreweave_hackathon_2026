# Clean Room Imputation

Reconstruct an occupied office as if nobody were there, preserving its furniture, layout, and visual consistency. The intended system uses agents to inspect a reconstruction, make targeted edits, and check their effects.

**Status — September 13, 2026:** initial local application implemented: Spark/Three.js viewer, camera capture, reversible scene revisions, provider adapters, and a bounded inspection/repair loop. The existing chair reconstruction is the initial test asset. No end-to-end restoration of the occupied office has been demonstrated.

Read [the build brief](docs/build-brief.md) for user intent, the proposed technical approach, evaluation questions, and known limits. Coding agents should also read [AGENTS.md](AGENTS.md).

This directory is the self-contained application and intended GitHub repository. Keep runtime code, scripts, dependencies, tests, and application documentation here. The parent workspace contains brainstorming, event research, local credentials, and private media; those are not runtime dependencies of an independent checkout. Accept configurable input and credential paths rather than hard-coding parent paths.

See the [agent runbook](docs/agent-runbook.md) for setup, implemented commands, evidence, and replay. Never commit populated credentials, raw captures, or temporary service response files.
