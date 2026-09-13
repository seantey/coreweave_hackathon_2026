# Working on Clean Room Imputation

- Read `README.md` and `docs/build-brief.md` in full before implementation or scope changes. User instructions override these assistant-written documents.
- Preserve the distinction between user intent, proposed methods, vendor capabilities, and tested behavior. A plausible image or a successful API response does not establish a correct reconstruction.
- Keep this repository independently runnable with configurable inputs and credentials. Parent-workspace planning notes and local media paths must not become mandatory runtime dependencies.
- Preserve original captures and retain reversible scene edits. Store camera transforms and evidence references with observations; a 2D detection is not a validated 3D selection.
- Keep evaluation criteria stable when comparing scene revisions. Distinguish adaptive inspection questions from changes to the evaluator. Record rejected edits and regressions as well as successes.
- Keep API keys server-side and out of logs, browser bundles, source control, and traces. Do not print credentials when diagnosing access.
- The local `codex-git-user` profile maps to the user-requested `rksean` account; no profile named `rksean` exists. Wrap Git/GitHub commands with `git-id-switcher run codex-git-user -- git ...` or `git-id-switcher run codex-git-user -- gh ...`. Do not add co-author or AI attribution footers.
- Write self-contained code comments and implementation docs. Update operational instructions only after testing the actual commands. Disclose reused prior-project components in the eventual submission.
- This file does not authorize subagent spawning or external publication. If delegation is separately authorized, give each agent a bounded task, shared contracts, and the relevant evidence; review and integrate its results.

- Project isolation: use only this project’s supplied office media and derivatives for reconstruction and demonstrations. Do not import scenes, assets, camera calibrations, or demo content from other projects, including as integration fixtures. Shared libraries and conceptual references do not authorize content reuse.
