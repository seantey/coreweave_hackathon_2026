# Clean Room Imputation

Reconstruct an occupied office as if nobody were there, preserving its furniture, layout, and visual consistency. The intended system uses agents to inspect a reconstruction, make targeted edits, and check their effects.

**Status — September 13, 2026:** pre-implementation. Service access probes have run in the development workspace, but this directory does not yet contain a runnable application. No end-to-end reconstruction or autonomous repair has been demonstrated.

Read [the build brief](docs/build-brief.md) for user intent, the proposed technical approach, evaluation questions, and known limits. Coding agents should also read [AGENTS.md](AGENTS.md).

This directory is the self-contained application and intended GitHub repository. Keep runtime code, scripts, dependencies, tests, and application documentation here. The parent workspace contains brainstorming, event research, local credentials, and private media; those are not runtime dependencies of an independent checkout. Accept configurable input and credential paths rather than hard-coding parent paths.

Setup and run instructions will be added when implemented and tested. Do not infer available commands or features from the design brief. Never commit populated credentials, raw captures, or temporary service response files.
