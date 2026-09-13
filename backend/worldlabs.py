"""Direct Marble API jobs, using the documented image/video input and operation API.

This optional route avoids Mint's image-preview dependency. It needs a separate
World Labs API key; Mint credits and authentication are not transferable.
"""

import base64
import json
import os
import time
from pathlib import Path
from urllib.parse import quote
import httpx
from dotenv import dotenv_values
from .storage import DATA, identifier, write_json

BASE = "https://api.worldlabs.ai/marble/v1"


def headers():
    key = os.environ.get("WORLDLABS_API_KEY") or dotenv_values(
        os.environ.get("CLEANROOM_ENV_FILE", ".env")
    ).get("WORLDLABS_API_KEY")
    if not key:
        raise ValueError("WORLDLABS_API_KEY is required for direct Marble generation")
    return {"WLT-Api-Key": key, "Content-Type": "application/json"}


def generate(source: Path, prompt: str, title: str, model: str = "marble-1.1"):
    authentication = headers()
    if not source.is_file():
        raise ValueError("Source media does not exist")
    if source.stat().st_size > 10_000_000:
        raise ValueError(
            "Compress the working input below 10 MB for this inline upload route; preserve the original"
        )
    media_type = (
        "video"
        if source.suffix.lower() in (".mp4", ".mov", ".webm", ".avi")
        else "image"
    )
    world_prompt = {
        "type": media_type,
        "text_prompt": prompt,
        media_type + "_prompt": {
            "source": "data_base64",
            "extension": source.suffix.lstrip("."),
            "data_base64": base64.b64encode(source.read_bytes()).decode(),
        },
    }
    directory = DATA / "world-generation" / identifier("marble")
    directory.mkdir(parents=True)
    write_json(
        directory / "request-description.json",
        {"source": str(source), "prompt": prompt, "title": title, "model": model},
    )
    with httpx.Client(timeout=120) as client:
        response = client.post(
            BASE + "/worlds:generate",
            headers=authentication,
            json={
                "display_name": title,
                "model": model,
                "permission": {"public": False},
                "world_prompt": world_prompt,
            },
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"World Labs returned HTTP {response.status_code}; inspect API access and credits"
            )
        operation = response.json()
    write_json(directory / "operation.json", operation)
    return directory / "operation.json"


def resume(operation_path: Path, timeout: float = 600):
    operation = json.loads(operation_path.read_text())
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=120) as client:
        while True:
            if operation.get("done"):
                if operation.get("error"):
                    raise RuntimeError(
                        "World Labs generation failed: " + str(operation["error"])
                    )
                write_json(operation_path.parent / "world.json", operation["response"])
                return operation["response"]
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Generation pending; resume {operation_path} without resubmitting"
                )
            response = client.get(
                BASE + "/operations/" + quote(operation["operation_id"], safe=""),
                headers=headers(),
            )
            response.raise_for_status()
            operation = response.json()
            write_json(operation_path, operation)
            if not operation.get("done"):
                time.sleep(5)
