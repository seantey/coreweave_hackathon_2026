"""Checkpointed source-image completion with a fixed preservation evaluator.

This prepares reconstruction inputs; it does not claim that a 2D verdict validates
3D geometry. The model chooses targeted edits from prior evaluation feedback.
"""

import base64
import json
import shutil
from pathlib import Path
import httpx
import weave
from PIL import Image
from pydantic import Field, StrictBool
from .models import StrictModel
from . import agent, providers, fal_jobs
from .storage import DATA, write_json

VERSION = "source-preservation-v1"
GOAL = "Recreate the same office as if nobody were there. Preserve furniture, layout, architecture, belongings, lighting and visual identity. Reconstruct only what people occluded."


class Assessment(StrictModel):
    people_absent: StrictBool | None
    furniture_preserved: StrictBool | None
    layout_preserved: StrictBool | None
    new_visible_damage: StrictBool | None
    evidence: str
    remaining_issues: list[str]
    uncertainties: list[str]

    def passes(self):
        return (
            self.people_absent is True
            and self.furniture_preserved is True
            and self.layout_preserved is True
            and self.new_visible_damage is False
            and not self.remaining_issues
            and not self.uncertainties
        )


class Plan(StrictModel):
    action: str
    reason: str = Field(min_length=5)
    edit_prompt: str | None = None


def read_images(paths):
    images = []
    for path in paths:
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            image.thumbnail((1774, 1200))
            images.append(image)
    return images


@weave.op()
def evaluate_completion(original: str, candidate: str):
    prompt = f"""Evaluate two images against this fixed goal: {GOAL}
Image 1 is the original source; image 2 is the candidate. Identify actual visible people/remnants and regressions, including small background people. Do not mistake chair backs, hanging jackets, or monitor content for physical people. Do not transcribe screens or signs.
Check whether original visible furniture, architecture, belongings and camera composition are preserved. Plausible newly exposed surfaces are inferred, not physical ground truth. Judge visible consistency here; do not fail solely because the real hidden surface cannot be known.
Return concise JSON with keys people_absent, furniture_preserved, layout_preserved, new_visible_damage (each boolean or null), evidence (string), remaining_issues (list of specific visible defects with locations), uncertainties (list of unresolved visible ambiguities). Missing evidence is null, not pass. Version {VERSION}."""
    result = agent.vision_review(prompt, read_images([original, candidate]))
    assessment = Assessment.model_validate(providers.structured(result["text"]))
    return {
        "prompt_version": VERSION,
        "prompt": prompt,
        **result,
        "assessment": assessment.model_dump(),
        "accepted": assessment.passes(),
    }


@weave.op()
def plan_completion(original: str, candidate: str, evaluation: dict):
    prompt = f"""You control an image-completion tool to achieve: {GOAL}
Image 1 is the original; image 2 is the latest candidate. Evaluation feedback: {json.dumps(evaluation['assessment'])}.
Choose one targeted correction or stop if the evidence is insufficient. The editing tool will receive the latest candidate first and the original second. Preserve source composition and exact aspect ratio. It must remove people without removing furniture or belongings. Treat detections as fallible; explain actual evidence.
Return JSON: {{"action":"edit"|"stop","reason":string,"edit_prompt":string|null}}.
The edit_prompt must be a complete, concrete instruction to the image model, naming locations and what must remain unchanged. Do not merely ask it to improve quality or beautify the office. Keep the same panoramic projection if the input is a panorama."""
    result = agent.vision_review(prompt, read_images([original, candidate]))
    plan = Plan.model_validate(providers.structured(result["text"]))
    if plan.action not in ("edit", "stop") or (
        plan.action == "edit" and not plan.edit_prompt
    ):
        raise ValueError("Invalid completion action")
    return {"prompt": prompt, **result, "plan": plan.model_dump()}


@weave.op()
def edit_completion(original: str, candidate: str, instruction: str, directory: str):
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    job = output / "job.json"
    if not job.exists():
        images = []
        for path in (candidate, original):
            with Image.open(path) as image:
                mime = Image.MIME.get(image.format, "image/png")
            images.append(
                f"data:{mime};base64,"
                + base64.b64encode(Path(path).read_bytes()).decode()
            )
        write_json(
            output / "instruction.json",
            {"prompt": instruction, "original": original, "candidate": candidate},
        )
        job = fal_jobs.submit(
            "fal-ai/nano-banana-2/edit",
            {
                "prompt": instruction,
                "image_urls": images,
                "resolution": "2K",
                "aspect_ratio": "auto",
                "output_format": "png",
                "num_images": 1,
            },
            output,
        )
    result = fal_jobs.resume(job, timeout=900)
    path = output / "candidate.png"
    if not path.exists():
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(result["images"][0]["url"])
            response.raise_for_status()
            temporary = output / "candidate.partial"
            temporary.write_bytes(response.content)
            with Image.open(temporary) as image:
                image.verify()
            temporary.replace(path)
    with Image.open(original) as source, Image.open(path) as edited:
        if (
            abs((source.width / source.height) / (edited.width / edited.height) - 1)
            > 0.02
        ):
            raise ValueError(
                "Completion changed the aspect ratio; do not reconstruct this candidate"
            )
    return {
        "candidate": str(path),
        "job": str(job),
        "provider": "fal-ai/nano-banana-2/edit",
    }


@weave.op()
def completion_loop(
    source: str, run_id: str, max_edits: int = 3, initial_candidate: str | None = None
):
    if not 0 <= max_edits <= 5:
        raise ValueError("Use zero to five edits")
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Run id must be a simple identifier")
    directory = DATA / "completion" / run_id
    directory.mkdir(parents=True, exist_ok=True)
    original = directory / ("original" + Path(source).suffix.lower())
    if not original.exists():
        shutil.copy2(source, original)
    candidate = original
    if initial_candidate:
        candidate = directory / ("initial" + Path(initial_candidate).suffix.lower())
        if not candidate.exists():
            shutil.copy2(initial_candidate, candidate)
    history = []
    for index in range(max_edits + 1):
        step = directory / f"pass-{index:02}"
        step.mkdir(exist_ok=True)
        evaluation_path = step / "evaluation.json"
        if evaluation_path.exists():
            evaluation = json.loads(evaluation_path.read_text())
        else:
            evaluation = evaluate_completion(str(original), str(candidate))
            write_json(evaluation_path, evaluation)
        history.append(
            {
                "candidate": str(candidate.relative_to(DATA)),
                "evaluation": str(evaluation_path.relative_to(DATA)),
                "accepted": evaluation["accepted"],
            }
        )
        summary = {
            "run_id": run_id,
            "prompt_version": VERSION,
            "history": history,
            "accepted": evaluation["accepted"],
            "candidate": str(candidate.relative_to(DATA)),
            "scope": "2D reconstruction input; 3D consistency requires separate validation",
        }
        write_json(directory / "summary.json", summary)
        if evaluation["accepted"] or index == max_edits:
            return summary
        plan_path = step / "plan.json"
        if plan_path.exists():
            planned = json.loads(plan_path.read_text())
        else:
            planned = plan_completion(str(original), str(candidate), evaluation)
            write_json(plan_path, planned)
        if planned["plan"]["action"] == "stop":
            summary["stop_reason"] = planned["plan"]["reason"]
            write_json(directory / "summary.json", summary)
            return summary
        edited = edit_completion(
            str(original),
            str(candidate),
            planned["plan"]["edit_prompt"],
            str(step / "edit"),
        )
        candidate = Path(edited["candidate"])
    raise AssertionError("Completion loop did not terminate")


def run_completion(*args, **kwargs):
    agent.initialize_tracing()
    try:
        return completion_loop(*args, **kwargs)
    finally:
        if agent.CLIENT:
            agent.CLIENT.flush()


@weave.op()
def reconstruct_completion(run_id: str, scene_id: str, reference: str):
    """Build a room only from an approved image, preserving the completion audit."""
    from .hunyuan import import_world
    from .storage import event, read_scene, scene_path, media_path

    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Run id must be a simple identifier")
    summary = json.loads((DATA / "completion" / run_id / "summary.json").read_text())
    if summary.get("accepted") is not True:
        raise ValueError("Source completion has not passed preservation review")
    candidate = media_path(summary["candidate"])
    with Image.open(candidate) as image:
        if image.width != 2 * image.height:
            raise ValueError("World reconstruction requires an exact 2:1 panorama")
    output = DATA / "world-generation" / (run_id + "-world")
    job = output / "job.json"
    if not job.exists():
        job = fal_jobs.submit(
            "fal-ai/hunyuan_world/image-to-world",
            {
                "image_url": "data:image/png;base64,"
                + base64.b64encode(candidate.read_bytes()).decode(),
                "labels_fg1": "chair",
                "labels_fg2": "desk, table, monitor",
                "classes": "indoor",
            },
            output,
        )
        write_json(output / "completion-source.json", summary)
    fal_jobs.resume(job, timeout=1200)
    if scene_path(scene_id).exists():
        scene = read_scene(scene_id)
        manifest = json.loads((scene_path(scene_id).parent / "import.json").read_text())
        if Path(manifest["job"]).resolve() != job.resolve():
            raise ValueError("Scene id belongs to a different reconstruction")
    else:
        scene = import_world(
            job, scene_id, "Clean Room Imputation — restored input", [reference]
        )
        event(
            scene_id,
            "source_completion",
            {
                **summary,
                "note": "Approved 2D input; this generated 3D reconstruction still requires inspection",
            },
        )
    return {"scene_id": scene.id, "completion": summary, "world_job": str(job)}
