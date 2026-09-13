"""Mechanical evidence checks that complement, rather than replace, visual judgment."""

import numpy as np
from PIL import Image
from pydantic import Field, StrictBool
from .models import StrictModel
from .storage import media_path


class VisualAssessment(StrictModel):
    defect_resolved: StrictBool | None
    furniture_preserved: StrictBool | None
    new_visible_damage: StrictBool | None
    evidence: str = Field(min_length=10)
    uncertainties: list[str]

    def passes(self):
        return (
            self.defect_resolved is True
            and self.furniture_preserved is True
            and self.new_visible_damage is False
            and not self.uncertainties
        )


def compare_views(before: list[dict], after: list[dict]):
    """Require matched cameras and measurable change; change alone is not improvement.

    The two-level pixel threshold tolerates small render/quantization variations.
    Its values are engineering defaults, not a validated perceptual quality metric.
    """
    if not before or len(before) != len(after):
        raise ValueError("Comparison requires matched before/after views")
    results = []
    for original, candidate in zip(before, after, strict=True):
        for field in (
            "scene_id",
            "camera_name",
            "camera_matrix",
            "projection_matrix",
            "viewport",
        ):
            if field not in original or original[field] != candidate.get(field):
                raise ValueError(f"Comparison camera mismatch: {field}")
        with Image.open(media_path(original["image"])) as image:
            pixels_before = np.asarray(image.convert("RGB"), dtype=np.int16)
        with Image.open(media_path(candidate["image"])) as image:
            pixels_after = np.asarray(image.convert("RGB"), dtype=np.int16)
        if pixels_before.shape != pixels_after.shape:
            raise ValueError("Comparison image dimensions differ")
        if original.get("isolated_asset") != candidate.get("isolated_asset"):
            raise ValueError("Comparison requires the same asset visibility scope")
        difference = np.abs(pixels_before - pixels_after)
        changed_fraction = float((difference.max(axis=2) > 3).mean())
        results.append(
            {
                "camera": original["camera_name"],
                "changed_fraction": changed_fraction,
                "mean_channel_difference": float(difference.mean()),
            }
        )
    return {
        "views": results,
        "visible_change": any(v["changed_fraction"] > 0.0001 for v in results),
        "threshold_note": "More than 0.01% of pixels differ by over 3/255 in a channel; not a quality score",
    }
