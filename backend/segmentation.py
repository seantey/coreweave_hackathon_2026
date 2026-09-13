"""Text-guided segmentation of source images or saved simulation views."""

import base64
import hashlib
import json
import shutil
from pathlib import Path
import httpx
from PIL import Image
from .fal_jobs import submit, resume
from .storage import DATA, identifier, write_json


def segment(
    image: Path, prompt: str, maximum_masks: int = 32, directory: Path | None = None
):
    if not 1 <= maximum_masks <= 32:
        raise ValueError("Use one to thirty-two masks")
    with Image.open(image) as opened:
        size = opened.size
        mime = Image.MIME.get(opened.format, "image/jpeg")
    directory = directory or DATA / "segmentation" / identifier("sam")
    directory.mkdir(parents=True, exist_ok=True)
    request = {
        "source_hash": hashlib.sha256(image.read_bytes()).hexdigest(),
        "prompt": prompt,
        "maximum_masks": maximum_masks,
    }
    request_path = directory / "request.json"
    if request_path.exists() and json.loads(request_path.read_text()) != request:
        raise ValueError("Segmentation directory belongs to another request")
    write_json(request_path, request)
    if (directory / "segmentation.json").exists():
        return json.loads((directory / "segmentation.json").read_text())
    preserved_source = directory / ("source" + image.suffix.lower())
    if image.resolve() != preserved_source.resolve():
        shutil.copy2(image, preserved_source)
    job = directory / "job.json"
    if not job.exists():
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
            # Returned masks and metadata are sorted together by confidence. The
            # metadata index is the detector's original index, not the mask-list offset.
            entries = result.get("metadata", [])
            metadata = entries[index] if index < len(entries) else {}
            masks.append(
                {
                    "path": str(path.relative_to(DATA)),
                    "mask_id": index,
                    "provider_index": metadata.get("index"),
                    "score": metadata.get("score"),
                    "box": metadata.get("box"),
                }
            )
    output = {
        "source_image": str(preserved_source.relative_to(DATA)),
        "input_origin": str(image.resolve()),
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
