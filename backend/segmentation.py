"""Text-guided segmentation of source images or saved simulation views."""

import base64
from pathlib import Path
import httpx
from PIL import Image
from .fal_jobs import submit, resume
from .storage import DATA, identifier, write_json


def segment(image: Path, prompt: str, maximum_masks: int = 32):
    if not 1 <= maximum_masks <= 32:
        raise ValueError("Use one to thirty-two masks")
    with Image.open(image) as opened:
        size = opened.size
        mime = Image.MIME.get(opened.format, "image/jpeg")
    directory = DATA / "segmentation" / identifier("sam")
    job = submit(
        "fal-ai/sam-3/image",
        {
            "image_url": f"data:{mime};base64,"
            + base64.b64encode(image.read_bytes()).decode(),
            "prompt": prompt,
            "apply_mask": False,
            "return_multiple_masks": True,
            "max_masks": maximum_masks,
            "include_scores": True,
            "include_boxes": True,
            "output_format": "png",
        },
        directory,
    )
    result = resume(job)
    masks = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for index, description in enumerate(result.get("masks", [])):
            response = client.get(description["url"])
            response.raise_for_status()
            path = directory / f"mask-{index:02}.png"
            path.write_bytes(response.content)
            with Image.open(path) as mask:
                if mask.size != size:
                    raise ValueError("Mask dimensions do not match the source image")
            metadata = next(
                (
                    value
                    for value in result.get("metadata", [])
                    if value.get("index") == index
                ),
                {},
            )
            masks.append({"path": str(path.relative_to(DATA)), **metadata})
    output = {
        "source_image": str(image),
        "source_size": size,
        "prompt": prompt,
        "masks": masks,
        "scores": result.get("scores", []),
        "boxes_normalized_cxcywh": result.get("boxes", []),
        "job": str(job.relative_to(DATA)),
        "interpretation": "Model detections, not verified identities or three-dimensional selections",
    }
    write_json(directory / "segmentation.json", output)
    return output
