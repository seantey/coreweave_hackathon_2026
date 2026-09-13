"""Review segmentation hypotheses against source crops before any removal is considered."""

import json
from pathlib import Path
import weave
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from pydantic import Field, StrictBool
from typing import Literal
from .models import StrictModel
from .storage import media_path, write_json
from .agent import vision_review


class MaskDecision(StrictModel):
    mask_id: int
    classification: Literal[
        "person", "mixed_person_and_furniture", "not_person", "uncertain"
    ]
    visible_person_only: StrictBool
    explanation: str = Field(min_length=5)


class ReviewBatch(StrictModel):
    decisions: list[MaskDecision]


def review_sheet(source: Image.Image, masks: list[tuple[int, Image.Image]]):
    sheet = Image.new("RGB", (960, 260 * len(masks)), (22, 29, 27))
    draw = ImageDraw.Draw(sheet)
    for row, (index, mask) in enumerate(masks):
        bbox = mask.getbbox()
        if bbox is None:
            raise ValueError("Cannot review an empty mask")
        x0, y0, x1, y1 = bbox
        padding = max(30, int(max(x1 - x0, y1 - y0) * 0.3))
        box = (
            max(0, x0 - padding),
            max(0, y0 - padding),
            min(source.width, x1 + padding),
            min(source.height, y1 + padding),
        )
        crop = source.crop(box)
        local_mask = mask.crop(box)
        tint = Image.new("RGB", crop.size, (244, 72, 99))
        overlay = Image.composite(Image.blend(crop, tint, 0.55), crop, local_mask)
        for column, image in enumerate([crop, overlay]):
            image = ImageOps.contain(image, (460, 220), Image.Resampling.LANCZOS)
            sheet.paste(
                image,
                (
                    column * 480 + (460 - image.width) // 2,
                    row * 260 + 30 + (220 - image.height) // 2,
                ),
            )
        draw.text((12, row * 260 + 9), f"Mask {index}: source crop", fill="white")
        draw.text(
            (492, row * 260 + 9),
            f"Mask {index}: red overlay is selected region",
            fill="white",
        )
    return sheet


@weave.op()
def review_segmentation(segmentation_path: str):
    path = Path(segmentation_path)
    record = json.loads(path.read_text())
    source = Image.open(media_path(record["source_image"])).convert("RGB")
    decisions = []
    for start in range(0, len(record["masks"]), 5):
        selected = record["masks"][start : start + 5]
        masks = [
            (start + index, Image.open(media_path(item["path"])).convert("L"))
            for index, item in enumerate(selected)
        ]
        sheet_path = path.parent / f"review-{start:02}.png"
        checkpoint = path.parent / f"review-{start:02}-response.json"
        if checkpoint.exists() and sheet_path.exists():
            sheet = Image.open(sheet_path).convert("RGB")
        else:
            sheet = review_sheet(source, masks)
            sheet.save(sheet_path)
        prompt = f"""Review person-segmentation candidates from a source office photo. The first image is the source.
The second contains paired crops: unmodified on the left, selected mask tinted red on the right.
Judge ONLY the red selected pixels, not every object in the crop. Preserve chairs, desks, monitors and belongings.
Return JSON with decisions for exactly mask_ids {[index for index, _ in masks]}.
Each decision: {{"mask_id":integer,"classification":"person"|"mixed_person_and_furniture"|"not_person"|"uncertain",
"visible_person_only":boolean,"explanation":string}}. Keep explanations under 25 words.
Use visible_person_only=true only for a visible person mask with no furniture included. Low-resolution ambiguity is uncertain.
Do not infer identity or transcribe screens/signs. This assesses two-dimensional masks, not reconstructed geometry or hidden surfaces."""
        if checkpoint.exists():
            response = json.loads(checkpoint.read_text())
        else:
            response = vision_review(prompt, [source, sheet], max_tokens=32768)
            write_json(checkpoint, response)
        # Some providers return the requested decision list without its outer object.
        # Normalize only that container; every decision still undergoes strict validation.
        text = response["text"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        batch = ReviewBatch.model_validate(
            {"decisions": parsed} if isinstance(parsed, list) else parsed
        )
        if sorted(d.mask_id for d in batch.decisions) != [index for index, _ in masks]:
            raise ValueError("Reviewer did not return exactly the requested mask IDs")
        decisions.extend(decision.model_dump() for decision in batch.decisions)
        write_json(
            path.parent / f"review-{start:02}.json",
            {
                "prompt": prompt,
                **response,
                "decisions": [d.model_dump() for d in batch.decisions],
            },
        )
    union = np.zeros((source.height, source.width), dtype=bool)
    for decision in decisions:
        if decision["classification"] == "person" and decision["visible_person_only"]:
            mask = Image.open(
                media_path(record["masks"][decision["mask_id"]]["path"])
            ).convert("L")
            union |= np.asarray(mask) > 127
    Image.fromarray(union.astype(np.uint8) * 255).save(
        path.parent / "reviewed-person-mask.png"
    )
    result = {
        "decisions": decisions,
        "candidate_count": len(decisions),
        "selected_count": sum(
            d["classification"] == "person" and d["visible_person_only"]
            for d in decisions
        ),
        "selected_pixel_fraction": float(union.mean()),
        "scope": "VLM-reviewed two-dimensional hypotheses; no image or 3D scene has been modified",
    }
    write_json(path.parent / "review.json", result)
    return result
