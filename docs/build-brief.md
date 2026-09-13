# Build brief

Updated September 13, 2026. Assistant-written implementation guidance from the user's discussion. User intent below is established; proposed mechanics are engineering starting points, not tested capabilities or immutable architecture. Implementation has been delegated to the assistant, including resolving technical unknowns.

## Intended outcome

**Clean Room Imputation** recreates an occupied office as if nobody were there. Preserve the same office's furniture, layout, and visual identity. This is not a request to empty the office, redecorate it, or replace its furniture with prettier alternatives. Treatment of belongings and clutter beyond people is not comprehensively specified; do not assume permission to remove everything portable.

The user wants agents to inspect the reconstructed space and use tools to repair inconsistencies iteratively. They also want, ideally, separated furniture assets and individual collision meshes. Collision repair supports the reconstruction outcome; it is not the sole product. Full articulation and realistic drone flight are not established requirements. Earlier drone ideas refer to virtual inspection/probing entities.

Automatic discovery is preferred over requiring the user to select every object. Bounding boxes may be useful tool inputs or inspection controls, but no manual-first interface is required.

Visual consistency matters: a complete mesh that looks conspicuously different from the surrounding splat can be an unacceptable replacement. Prefer preserving, extracting, and reusing suitable appearance before regenerating objects. Extraction, reuse, repair, and generation are choices to evaluate against the input, not a guaranteed sequence.

## Proposed technical approach

The user explicitly proposed reusing the previous hackathon's Spark/Three.js approach and using screenshots with a vision-language model. Begin by validating these components together:

| Component | Intended role | Evidence boundary |
| --- | --- | --- |
| Mint / World Labs Marble | Initial scene generation and downloadable appearance/collision assets | OAuth restored. Two office requests failed in Mint’s upstream fal preview provider with exhausted-balance errors. No completed office world yet. |
| Spark + Three.js | Render splats and meshes, position inspection cameras, apply visual edits, place assets | Viewer renders chair splats, a remote RAD bedroom fixture, and layered Hunyuan meshes. First office fallback was rejected for projection distortion; corrected panorama reconstruction is processing. |
| fal SAM 3D Objects | Reconstruct selected objects, potentially supplying both splats and meshes | One actual request returned a Gaussian PLY and GLB, now rendered. Exports have different coordinate frames; empirical registration is implemented. Room alignment remains untested. |
| Programmatic geometry/editing | Surface completion, object transforms, local geometry and collider changes | Reversible edit primitives are implemented. Scene-quality improvement remains unvalidated. A people-free 2D image candidate has also been generated for evaluation; it is not a restored 3D scene. |
| W&B Inference | GLM-5.3-Flash image observations and potentially agent decisions | Multiple completed image evaluations and mask reviews, including a targeted 2D correction experiment. False-positive flags were found by inspecting crops; reliability remains unvalidated. Native video support is not established. |
| Weave | Trace tool/model calls and record evaluations and revisions | Connectivity trace succeeded; bounded loop instrumentation is implemented. A real inspection trace with image inputs completed and stopped on the isolated chair. An accepted real-room repair remains to be demonstrated. |

Tripo is deferred at the user's request; do not make it a dependency. TypeSafe is optional and should only be introduced if it demonstrably helps. ARIA, marimo, and separate cloud GPU provisioning are not selected dependencies.

Borrow relevant renderer, camera, coordinate, and collider patterns from the previous project after inspecting the actual code. Do not import its house-specific assumptions, authored interactions, or claims of tested behavior into this application.

## Agent loop to develop

1. Inspect source imagery and rendered views; identify a specific suspected defect and supporting evidence.
2. Choose another view or tool when the diagnosis is ambiguous.
3. Select an edit: extract/reuse an object, complete a region, generate an asset, adjust placement, or repair geometry.
4. Save the proposed edit as a reversible scene revision.
5. Render comparable views and run relevant checks; accept, revise, or undo the edit.
6. Stop when criteria are met, evidence is insufficient, attempts no longer help, or the authorized resource limit is reached.

This is a proposed mechanism. Do not script a known failure and describe its correction as autonomously discovered. Assistant-led experiments can establish useful operations, but a deployed loop must invoke those operations and inspect feedback itself to support claims of agent autonomy.

Inspection prompts may adapt to a region and uncertainty. Keep the goal and comparison criteria stable. If evaluator prompts change, version them and compare on fixed examples; a higher score from a different evaluator is not proof of scene improvement.

## Evaluation and unresolved risks

There is no validated universal scene-quality score. Candidate checks include remaining people/remnants, preservation of visible furniture, agreement with source views, replacement alignment, gaps and intersections, and regressions in neighboring regions. Implement and validate checks before treating their outputs as reliable.

- A visual model is fallible. Test known defects, intact areas, and ambiguous cases. Preserve uncertainty and references to views or regions; do not merely request an overall goodness number.
- No detected people does not establish success: missing furniture or uninspected areas can invalidate the result.
- Screenshot coordinates require camera transforms and depth/geometry to support a 3D edit. Depth estimates and reconstructions can be wrong.
- Additional rendered views reveal the reconstruction, not new evidence about the physical room. Hidden surfaces may only admit plausible completion.
- An extracted chair can lack its hidden back or underside. Removing it can expose an incomplete background.
- Suppressing splats at render time does not automatically edit exported assets or collision geometry. Save edit state and replacement assets and verify persistence.
- A generated mesh is not automatically a suitable collision mesh. Validate alignment and simplify when appropriate.
- Same-model generations do not guarantee matching appearance. Inspect all replacements in the actual scene from multiple views.
- Connectivity probes establish access, not production readiness, geometric accuracy, evaluator reliability, or a successful repair loop.

## Initial engineering priorities

Proposed sequence for autonomous implementation, adjustable based on evidence:

1. Establish input coverage, service access, and a working asset-to-viewer path.
2. Make screenshots and camera metadata available through callable tools.
3. Demonstrate one useful reversible edit and an evidence-backed check of its effect.
4. Connect the agent's inspect/edit/recheck decisions and Weave instrumentation.
5. Expand coverage and object reconstruction while testing visual preservation and regressions.
6. Prepare a reproducible demo with clear before/after evidence, real limitations, and disclosure of reused components.

Do not treat this sequence as user approval to drop desired object/collider functionality silently. Report tradeoffs and actual completion.

## Primary technical references

Consulted September 12–13, 2026; vendor documentation is not local validation.

- [Marble exports](https://docs.worldlabs.ai/marble/export/mesh)
- [Spark overview](https://sparkjs.dev/docs/overview/) and [spatial splat editing](https://sparkjs.dev/docs/splat-editing/)
- [fal SAM 3D Objects schema](https://fal.ai/models/fal-ai/sam-3/3d-objects/api) and [queue lifecycle](https://fal.ai/docs/documentation/model-apis/inference/queue)
- [W&B Inference API](https://docs.wandb.ai/inference/api-reference) and [chat completions](https://docs.wandb.ai/inference/api-reference/chat-completions)
- [Weave overview](https://docs.wandb.ai/weave/concepts/what-is-weave) and [evaluations](https://docs.wandb.ai/weave/guides/core-types/evaluations)
