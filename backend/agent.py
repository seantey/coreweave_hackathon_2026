"""Bounded inspection/repair loop, callable from the UI or CLI and traced in Weave."""

import json, os
import weave
from PIL import Image
from . import providers
from .capture import capture
from .models import Edit, ImageRegion
from .verification import VisualAssessment, compare_views
from .storage import (
    read_scene,
    propose,
    decide,
    event,
    identifier,
    media_path,
    write_json,
    DATA,
)

PROMPT_VERSION = "office-preservation-v4"
CLIENT = None


def initialize_tracing():
    global CLIENT
    if (
        CLIENT is None
        and os.environ.get("WANDB_API_KEY")
        and os.environ.get("CLEANROOM_WEAVE", "true").lower() == "true"
    ):
        CLIENT = weave.init(
            os.environ.get("WANDB_ENTITY", "")
            + "/"
            + os.environ.get("WANDB_PROJECT", "clean-room-imputation")
        )


@weave.op()
def vision_review(prompt: str, images: list[Image.Image], max_tokens: int = 4096):
    """Attach the exact reviewed image pixels to the trace, alongside the final answer."""
    return providers.vision(prompt, images, max_tokens=max_tokens)


def review_paths(prompt, paths):
    images = []
    for path in paths:
        with Image.open(path) as image:
            images.append(image.convert("RGB"))
    return vision_review(prompt, images)


@weave.op()
def observe_scene(scene_id: str, revision_id: str, views: list[dict]):
    scene = read_scene(scene_id)
    recent_attempts = [
        {
            "status": revision.status,
            "edit": revision.edits[-1].model_dump(),
            "evaluation": (revision.evaluation or {}).get(
                "assessment", revision.evaluation
            ),
        }
        for revision in scene.revisions[-4:]
        if revision.edits and revision.status in ("accepted", "rejected")
    ]
    prompt = f"""You inspect a 3D reconstruction, not a real room. Goal: {scene.goal}
Source kind: {scene.source_kind}. An object_probe is only an isolated model test, not an office.
Never invent people or claim hidden geometry is correct. Report specific visible defects and uncertainty.
The first images are simulation views; their camera metadata is {json.dumps(views)}.
Any final images are original references, not current renderings.
Asset inventory: {json.dumps([a.model_dump() for a in scene.assets])}
Recent attempted edits and evaluator feedback: {json.dumps(recent_attempts)}.
When an edit was rejected, use the evidence to revise the hypothesis or stop. Do not repeat the same edit.
All lengths are arbitrary scene units unless metric_status is explicitly calibrated. Never label them meters or infer real furniture size from them. World up and semantic front are also unverified for imported objects.
Scene bounds (world coordinates): {scene.bounds.model_dump()}.
Return concise JSON only, with at most three observations and these keys:
observations: list of {{issue, evidence_views: [camera names], confidence: 'high'|'medium'|'low', needs_more_evidence: boolean}},
next_action: 'inspect'|'probe'|'repair'|'stop',
reason: string,
camera: existing camera name or null,
region: null or {{minimum:[left,top],maximum:[right,bottom]}} in normalized image coordinates [0,1],
edit: null or {{operation:'hide_region'|'transform_asset'|'place_asset'|'add_surface',asset_id:string,reason:string,evidence:[view names],bounds:{{minimum:[x,y,z],maximum:[x,y,z]}} or null,transform:{{position:[x,y,z],rotation:[x,y,z],scale:[x,y,z]}} or null,size:[x,y,z] or null,color:'#hex'}}.
Only propose a spatial edit when its coordinates are grounded in supplied geometry metadata.
Use next_action='probe', camera, and region to inspect collider intersections beneath a specific image region.
Probe samples contain actual collider hits, not segmentation or independent evidence of real geometry.
A hit may be a background surface behind an unmodeled person. Do not erase the entire sampled volume blindly.
hide_region suppresses a box in one splat asset, and removes its matching collider triangles; it may expose holes.
transform_asset moves an entire independent asset. add_surface adds a plain box: use only for simple missing surfaces with evidence, never to cover people.
place_asset activates an existing library asset (initially_visible=false) at a grounded transform. It does not generate an asset. Use only when its identity and placement are supported; do not duplicate existing furniture.
Do not improve appearances by changing the original design. Stop with uncertainty when no supported repair is available.
Do not transcribe screens or signs. Prompt version {PROMPT_VERSION}."""
    paths = [media_path(v["image"]) for v in views]
    paths += [media_path(r) for r in scene.references[:1]]
    result = review_paths(prompt, paths)
    return {
        "prompt_version": PROMPT_VERSION,
        "prompt": prompt,
        **result,
        "assessment": providers.structured(result["text"]),
    }


@weave.op()
def evaluate_revision(scene_id: str, edit: dict, before: list[dict], after: list[dict]):
    scene = read_scene(scene_id)
    mechanical = compare_views(before, after)
    if not mechanical["visible_change"]:
        return {
            "prompt_version": PROMPT_VERSION,
            "accepted": False,
            "mechanical": mechanical,
            "assessment": {
                "evidence": "No measurable visible change in the compared views",
                "uncertainties": ["The proposed repair was not demonstrated"],
            },
        }
    prompt = f"""Evaluate a proposed 3D scene repair against this unchanged goal: {scene.goal}
Proposed edit: {json.dumps(edit)}.
Images are ordered: {len(before)} BEFORE views, then {len(after)} AFTER views at exactly the same cameras.
Camera names: {[v["camera_name"] for v in before]}.
Any remaining images are original source references. Use them to check furniture identity and preservation.
Assess actual visual evidence. An unchanged image is not improvement. Missing evidence means uncertain, not pass.
Return JSON only: {{"defect_resolved":true|false|null,"furniture_preserved":true|false|null,
"new_visible_damage":true|false|null,"evidence":string,"uncertainties":[string]}}.
All three checks need decisive evidence to accept: resolved=true, preserved=true, damage=false, and no unresolved uncertainties.
Do not reward removal of furniture or simply covering a defect. This checks rendered consistency, not unseen real geometry.
Prompt version {PROMPT_VERSION}."""
    result = review_paths(
        prompt,
        [media_path(v["image"]) for v in before + after]
        + [media_path(r) for r in scene.references[:1]],
    )
    assessment = VisualAssessment.model_validate(providers.structured(result["text"]))
    return {
        "prompt_version": PROMPT_VERSION,
        "prompt": prompt,
        **result,
        "mechanical": mechanical,
        "assessment": assessment.model_dump(),
        "accepted": assessment.passes(),
    }


@weave.op()
def repair_loop(scene_id: str, max_passes: int = 2, job_id: str | None = None):
    """No implicit asset-generation calls. Every pass is checkpointed and bounded."""
    if not 1 <= max_passes <= 5:
        raise ValueError("Use between 1 and 5 passes")
    job_id = job_id or identifier("loop")
    history = []
    attempted = set()
    for index in range(max_passes):
        scene = read_scene(scene_id)
        selected = list(scene.cameras)[:2]
        event(
            scene_id,
            "inspection_started",
            {"job_id": job_id, "pass": index + 1, "revision": scene.current_revision},
        )
        before = [capture(scene_id, scene.current_revision, c) for c in selected]
        observation = observe_scene(scene_id, scene.current_revision, before)
        event(
            scene_id,
            "observation",
            {"job_id": job_id, "pass": index + 1, "views": before, **observation},
        )
        choice = observation["assessment"]
        if (
            choice.get("next_action") == "probe"
            and choice.get("camera") in scene.cameras
        ):
            region = ImageRegion.model_validate(choice.get("region"))
            probed = capture(scene_id, scene.current_revision, choice["camera"], region)
            before = [v for v in before if v["camera_name"] != choice["camera"]] + [
                probed
            ]
            observation = observe_scene(scene_id, scene.current_revision, before)
            event(
                scene_id,
                "geometry_observation",
                {"job_id": job_id, "views": before, **observation},
            )
            choice = observation["assessment"]
        if (
            choice.get("next_action") == "inspect"
            and choice.get("camera") in scene.cameras
        ):
            name = choice["camera"]
            if name not in selected:
                before.append(capture(scene_id, scene.current_revision, name))
                observation = observe_scene(scene_id, scene.current_revision, before)
                event(
                    scene_id,
                    "additional_observation",
                    {"job_id": job_id, "views": before, **observation},
                )
                choice = observation["assessment"]
        if choice.get("next_action") != "repair" or not choice.get("edit"):
            history.append(
                {
                    "pass": index + 1,
                    "outcome": "stopped",
                    "reason": choice.get("reason", "Insufficient evidence"),
                }
            )
            break
        try:
            edit = Edit.model_validate({**choice["edit"], "id": identifier("edit")})
            signature = json.dumps(
                edit.model_dump(exclude={"id", "reason", "evidence"}), sort_keys=True
            )
            if signature in attempted:
                history.append(
                    {
                        "pass": index + 1,
                        "outcome": "stopped",
                        "reason": "Repeated proposal; no new spatial hypothesis",
                    }
                )
                break
            attempted.add(signature)
            revision = propose(scene_id, edit, scene.current_revision)
        except ValueError as e:
            history.append(
                {"pass": index + 1, "outcome": "invalid_proposal", "reason": str(e)}
            )
            event(scene_id, "proposal_rejected", history[-1])
            break
        event(
            scene_id,
            "candidate",
            {"job_id": job_id, "revision": revision.model_dump(mode="json")},
        )
        try:
            # Keep one available camera out of the repair proposal, then check it for regressions.
            held_out = next(
                (
                    name
                    for name in scene.cameras
                    if name not in {v["camera_name"] for v in before}
                ),
                None,
            )
            if held_out:
                before.append(capture(scene_id, scene.current_revision, held_out))
            after = [capture(scene_id, revision.id, v["camera_name"]) for v in before]
            evaluation = evaluate_revision(
                scene_id, edit.model_dump(mode="json"), before, after
            )
            decide(scene_id, revision.id, evaluation["accepted"], evaluation)
        except Exception:
            decide(
                scene_id,
                revision.id,
                False,
                {"reason": "Verification failed; original revision retained"},
            )
            raise
        history.append(
            {
                "pass": index + 1,
                "revision": revision.id,
                "outcome": "accepted" if evaluation["accepted"] else "rejected",
            }
        )
        event(
            scene_id,
            "evaluation",
            {
                "job_id": job_id,
                "before": before,
                "after": after,
                **evaluation,
                **history[-1],
            },
        )
        # The next bounded pass sees the rejection and evaluator evidence. An identical
        # spatial proposal is stopped above rather than spending again on repetition.
    result = {
        "job_id": job_id,
        "scene_id": scene_id,
        "passes": history,
        "prompt_version": PROMPT_VERSION,
    }
    write_json(DATA / "runs" / (job_id + ".json"), result)
    event(scene_id, "loop_finished", result)
    return result


def run_traced_loop(scene_id: str, max_passes: int = 2, job_id: str | None = None):
    """Flush only after the decorated call has ended and queued its completion.

    Flushing inside an active traced operation can wait indefinitely for that
    same operation's completion record in the call batch processor.
    """
    job_id = job_id or identifier("loop")
    initialize_tracing()
    try:
        return repair_loop(scene_id, max_passes, job_id)
    except Exception as error:
        message = str(error)
        for name in ("WANDB_API_KEY", "FAL_KEY"):
            if os.environ.get(name):
                message = message.replace(os.environ[name], "[redacted]")
        failure = {
            "job_id": job_id,
            "scene_id": scene_id,
            "status": "failed",
            "error": message[:1000],
            "prompt_version": PROMPT_VERSION,
        }
        write_json(DATA / "runs" / (job_id + ".json"), failure)
        event(scene_id, "loop_failed", failure)
        raise
    finally:
        if CLIENT:
            CLIENT.flush()
