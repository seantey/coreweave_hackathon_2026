"""Provider adapters. Keys remain in request headers and are never returned to tools."""

import base64, io, json, os, time
from pathlib import Path
from PIL import Image
import httpx
from .storage import DATA, identifier, write_json


def vision(prompt: str, images: list[Path | Image.Image], max_tokens=4096):
    key = os.environ.get("WANDB_API_KEY")
    if not key:
        raise ValueError("WANDB_API_KEY is not configured")
    content = [{"type": "text", "text": prompt}]
    for image in images:
        if isinstance(image, Image.Image):
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            mime = "image/png"
        else:
            image_bytes = image.read_bytes()
            mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
        if len(image_bytes) > 10_000_000:
            raise ValueError("Resize inspection images below 10 MB")
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,"
                    + base64.b64encode(image_bytes).decode()
                },
            }
        )
    headers = {
        "Authorization": "Bearer " + key,
        "User-Agent": "clean-room-imputation/0.1",
    }
    if os.environ.get("WANDB_ENTITY"):
        headers["OpenAI-Project"] = (
            os.environ["WANDB_ENTITY"]
            + "/"
            + os.environ.get("WANDB_PROJECT", "clean-room-imputation")
        )
    with httpx.Client(timeout=httpx.Timeout(600, connect=30)) as client:
        response = client.post(
            "https://api.inference.wandb.ai/v1/chat/completions",
            headers=headers,
            json={
                "model": os.environ.get("CLEANROOM_MODEL", "zai-org/GLM-5.3-Flash"),
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": content}],
            },
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"W&B inference returned HTTP {response.status_code}; check account access and credits"
            )
        data = response.json()
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length" or not choice["message"].get("content"):
        raise RuntimeError(
            "Inference exhausted its output allowance; no complete evaluation was obtained"
        )
    # Persist final answers and usage, not hidden reasoning or base64 request bodies.
    return {
        "text": choice["message"]["content"],
        "usage": data.get("usage", {}),
        "model": data.get("model"),
        "request_id": data.get("id"),
    }


def structured(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def reconstruct(image: Path, box: dict, seed=42):
    """Submit once, checkpoint its id before polling, and preserve downloaded output."""
    key = os.environ.get("FAL_KEY")
    if not key:
        raise ValueError("FAL_KEY is not configured")
    output = DATA / "assets" / identifier("sam3d")
    output.mkdir(parents=True)
    headers = {"Authorization": "Key " + key}
    image_uri = (
        "data:image/jpeg;base64," + base64.b64encode(image.read_bytes()).decode()
    )
    with httpx.Client(timeout=60) as client:
        r = client.post(
            "https://queue.fal.run/fal-ai/sam-3/3d-objects",
            headers=headers,
            json={"image_url": image_uri, "box_prompts": [box], "seed": seed},
        )
        r.raise_for_status()
        job = r.json()
        write_json(output / "job.json", job)
        for _ in range(180):
            status = client.get(job["status_url"], headers=headers)
            status.raise_for_status()
            if status.json()["status"] == "COMPLETED":
                break
            time.sleep(2)
        else:
            raise RuntimeError(
                f"Job still pending; resume from {output / 'job.json'} rather than resubmitting"
            )
        r = client.get(job["response_url"], headers=headers)
        r.raise_for_status()
        result = r.json()
        write_json(output / "result.json", result)
        files = {}
        for field, ext in [("gaussian_splat", "ply"), ("model_glb", "glb")]:
            if result.get(field):
                asset = client.get(result[field]["url"])
                asset.raise_for_status()
                path = output / f"object.{ext}"
                path.write_bytes(asset.content)
                files[field] = str(path.relative_to(DATA))
    return {
        "request_id": job["request_id"],
        "files": files,
        "metadata": result.get("metadata", []),
    }
