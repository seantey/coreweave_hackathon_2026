"""Checkpointed source-image completion with a fixed preservation evaluator.

This prepares reconstruction inputs; it does not claim that a 2D verdict validates
3D geometry. The model chooses targeted edits from prior evaluation feedback.
"""

import base64
import hashlib
import json
import shutil
from pathlib import Path
import httpx
import weave
from PIL import Image
from pydantic import Field, StrictBool
from .models import StrictModel, ImageRegion
from . import agent, providers, fal_jobs
from .storage import DATA, write_json, media_path

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
    crop_region: ImageRegion | None = None


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
    parsed = providers.structured(result["text"])
    # Some responses echo the requested version as metadata. It is not a verdict
    # field; only the exact known value may be omitted before strict validation.
    if parsed.get("version") == VERSION:
        parsed.pop("version")
    assessment = Assessment.model_validate(parsed)
    return {
        "prompt_version": VERSION,
        "prompt": prompt,
        **result,
        "assessment": assessment.model_dump(),
        "accepted": assessment.passes(),
    }


@weave.op()
def audit_completion_people(candidate: str, directory: str):
    from .segmentation import segment
    from .mask_review import review_segmentation

    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    reference_path = output / "segmentation-reference.json"
    if reference_path.exists():
        segmentation_path = media_path(
            json.loads(reference_path.read_text())["segmentation"]
        )
        record = json.loads(segmentation_path.read_text())
        if (
            hashlib.sha256(media_path(record["source_image"]).read_bytes()).digest()
            != hashlib.sha256(Path(candidate).read_bytes()).digest()
        ):
            raise ValueError("Person audit belongs to another candidate")
    else:
        record = segment(
            Path(candidate),
            "person",
            maximum_masks=12,
            directory=output / "segmentation",
        )
        segmentation_path = output / "segmentation" / "segmentation.json"
        write_json(
            reference_path, {"segmentation": str(segmentation_path.relative_to(DATA))}
        )
    reviewed = review_segmentation(str(segmentation_path))
    detections = [
        {
            **decision,
            "box_normalized_cxcywh": record["masks"][decision["mask_id"]]["box"],
        }
        for decision in reviewed["decisions"]
    ]
    result = {
        "detections": detections,
        "people_count": sum(
            d["classification"] in ("person", "mixed_person_and_furniture")
            for d in detections
        ),
        "uncertain_count": sum(d["classification"] == "uncertain" for d in detections),
        "sheets": [
            str(path.relative_to(DATA))
            for path in sorted(segmentation_path.parent.glob("review-*.png"))
        ],
        "scope": "Independent detector plus crop review; detections are fallible and zero detections alone cannot prove absence",
    }
    write_json(output / "audit.json", result)
    return result


@weave.op()
def plan_completion(original: str, candidate: str, evaluation: dict):
    prompt = f"""You control an image-completion tool to achieve: {GOAL}
Image 1 is the original; image 2 is the latest candidate. Evaluation feedback: {json.dumps(evaluation['assessment'])}.
Choose one targeted correction or stop if the evidence is insufficient. The editing tool will receive the latest candidate first and the original second. Preserve source composition and exact aspect ratio. It must remove people without removing furniture or belongings. Treat detections as fallible; explain actual evidence.
Return JSON: {{"action":"edit"|"stop","reason":string,"edit_prompt":string|null,"crop_region":null|{{"minimum":[left,top],"maximum":[right,bottom]}}}}.
For a single small remaining person, use crop_region in normalized candidate coordinates to isolate that person plus nearby context (roughly 5-15% of image width). The tool edits that crop at larger resolution and composites it back, keeping outside pixels exactly unchanged. Write the edit prompt for this crop, not for the whole panorama. A whole-image edit often misses tiny background figures.
The edit_prompt must be a complete, concrete instruction to the image model, naming locations and what must remain unchanged. Do not merely ask it to improve quality or beautify the office. Keep the same panoramic projection if the input is a panorama."""
    images = read_images([original, candidate])
    if evaluation.get("person_audit"):
        prompt += (
            "\nAn independent person segmentation and localized crop review provides counter-evidence: "
            + json.dumps(evaluation["person_audit"])
            + ". Additional images are its enlarged crop/mask sheets. Inspect these actual pixels; do not dismiss a localized head and torso because a broad scene description said people were absent. The normalized boxes locate each detection in the candidate."
        )
        images += read_images(
            [media_path(path) for path in evaluation["person_audit"]["sheets"]]
        )
    elif evaluation["assessment"].get("uncertainties"):
        prompt += "\nAdditional images are four ORIGINAL/CANDIDATE crop pairs, left to right across the horizon band (normalized y=0.38 to 0.72). Inspect these enlarged details to resolve the reported ambiguities before choosing an edit. They are crops of the same inputs, not additional captured viewpoints."
        for column in range(4):
            for path in (original, candidate):
                with Image.open(path) as full:
                    width, height = full.size
                    crop = full.convert("RGB").crop(
                        (
                            int(column * width / 4),
                            int(0.38 * height),
                            int((column + 1) * width / 4),
                            int(0.72 * height),
                        )
                    )
                    crop.thumbnail((900, 700))
                    images.append(crop)
    result = agent.vision_review(prompt, images)
    plan = Plan.model_validate(providers.structured(result["text"]))
    if plan.action not in ("edit", "stop") or (
        plan.action == "edit" and not plan.edit_prompt
    ):
        raise ValueError("Invalid completion action")
    return {"prompt": prompt, **result, "plan": plan.model_dump()}


@weave.op()
def edit_completion(
    original: str,
    candidate: str,
    instruction: str,
    directory: str,
    crop_region: dict | None = None,
):
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    job = output / "job.json"
    crop_box = None
    input_paths = (candidate, original)
    if crop_region:
        region = ImageRegion.model_validate(crop_region)
        with Image.open(candidate) as full:
            crop_box = (
                int(region.minimum[0] * full.width),
                int(region.minimum[1] * full.height),
                int(region.maximum[0] * full.width),
                int(region.maximum[1] * full.height),
            )
            if crop_box[2] - crop_box[0] < 8 or crop_box[3] - crop_box[1] < 8:
                raise ValueError("Crop is too small for a meaningful edit")
            crop = full.convert("RGB").crop(crop_box)
            crop = crop.resize(
                (1024, max(32, round(1024 * crop.height / crop.width))),
                Image.Resampling.LANCZOS,
            )
            crop.save(output / "input-crop.png")
        input_paths = (str(output / "input-crop.png"),)
    if not job.exists():
        images = []
        for path in input_paths:
            with Image.open(path) as image:
                mime = Image.MIME.get(image.format, "image/png")
            images.append(
                f"data:{mime};base64,"
                + base64.b64encode(Path(path).read_bytes()).decode()
            )
        write_json(
            output / "instruction.json",
            {
                "prompt": instruction,
                "original": original,
                "candidate": candidate,
                "crop_region": crop_region,
            },
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
    path = output / ("edited-crop.png" if crop_box else "candidate.png")
    if not path.exists():
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(result["images"][0]["url"])
            response.raise_for_status()
            temporary = output / "candidate.partial"
            temporary.write_bytes(response.content)
            with Image.open(temporary) as image:
                image.verify()
            temporary.replace(path)
    if crop_box:
        import numpy as np

        with Image.open(candidate) as full, Image.open(path) as patch:
            full = full.convert("RGB")
            size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
            patch = patch.convert("RGB").resize(size, Image.Resampling.LANCZOS)
            yy, xx = np.indices((size[1], size[0]))
            distance = np.minimum.reduce([xx, yy, size[0] - 1 - xx, size[1] - 1 - yy])
            feather = max(2, min(size) // 12)
            alpha = Image.fromarray(np.uint8(np.clip(distance / feather, 0, 1) * 255))
            full.paste(patch, crop_box[:2], alpha)
            path = output / "candidate.png"
            full.save(path)
        write_json(
            output / "composition.json",
            {
                "box_pixels": crop_box,
                "crop_region": crop_region,
                "feather_pixels": feather,
                "outside_pixels": "unchanged",
            },
        )
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
    if (
        original.exists()
        and hashlib.sha256(original.read_bytes()).digest()
        != hashlib.sha256(Path(source).read_bytes()).digest()
    ):
        raise ValueError("Run id already belongs to a different source image")
    if not original.exists():
        shutil.copy2(source, original)
    candidate = original
    if initial_candidate:
        candidate = directory / ("initial" + Path(initial_candidate).suffix.lower())
        if (
            candidate.exists()
            and hashlib.sha256(candidate.read_bytes()).digest()
            != hashlib.sha256(Path(initial_candidate).read_bytes()).digest()
        ):
            raise ValueError("Run id already belongs to a different initial candidate")
        if not candidate.exists():
            shutil.copy2(initial_candidate, candidate)
    history = []
    for index in range(max_edits + 1):
        step = directory / f"pass-{index:02}"
        step.mkdir(exist_ok=True)
        evaluation_path = step / "evaluation.json"
        if evaluation_path.exists():
            evaluation = json.loads(evaluation_path.read_text())
            if evaluation.get("prompt_version", VERSION) != VERSION:
                raise ValueError("Evaluation version changed; use a new run id")
        else:
            evaluation = evaluate_completion(str(original), str(candidate))
            write_json(evaluation_path, evaluation)
        person_audit = None
        if evaluation["assessment"].get("people_absent") is True:
            person_audit = audit_completion_people(
                str(candidate), str(step / "person-audit")
            )
            evaluation = {**evaluation, "person_audit": person_audit}
            evaluation["accepted"] = bool(
                evaluation["accepted"]
                and person_audit["people_count"] == 0
                and person_audit["uncertain_count"] == 0
            )
            combined_path = step / "evaluation-with-person-audit.json"
            write_json(combined_path, evaluation)
            evaluation_path = combined_path
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
        plan_path = step / (
            "plan-with-person-audit.json" if person_audit else "plan.json"
        )
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
            **(
                {"crop_region": planned["plan"]["crop_region"]}
                if planned["plan"].get("crop_region")
                else {}
            ),
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
