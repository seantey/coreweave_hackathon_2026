"""Checkpointed fal jobs that can resume without submitting another paid request."""

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .storage import write_json


def queue_headers():
    key = os.environ.get("FAL_KEY")
    if not key:
        raise ValueError("FAL_KEY is not configured")
    return {"Authorization": "Key " + key}


def submit(endpoint: str, payload: dict, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    job_path = directory / "job.json"
    if job_path.exists():
        raise ValueError("Job already submitted; resume it instead")
    with httpx.Client(timeout=120) as client:
        response = client.post(
            "https://queue.fal.run/" + endpoint, headers=queue_headers(), json=payload
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"fal submission returned HTTP {response.status_code}: {response.text[:500]}"
            )
        job = response.json()
    write_json(job_path, {"endpoint": endpoint, **job})
    return job_path


def resume(job_path: Path, timeout: float = 180):
    job = json.loads(job_path.read_text())
    result_path = job_path.parent / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    for field in ("status_url", "response_url"):
        url = urlparse(job[field])
        if (
            url.scheme != "https"
            or url.hostname != "queue.fal.run"
            or url.username
            or url.password
        ):
            raise ValueError("Job polling URLs must belong to the fal queue")
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=60) as client:
        while time.monotonic() < deadline:
            response = client.get(job["status_url"], headers=queue_headers())
            response.raise_for_status()
            status = response.json()
            write_json(job_path.parent / "status.json", status)
            if status["status"] == "COMPLETED":
                response = client.get(job["response_url"], headers=queue_headers())
                response.raise_for_status()
                result = response.json()
                write_json(result_path, result)
                return result
            if status["status"] in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"fal job ended with status {status['status']}")
            time.sleep(2)
    raise TimeoutError(f"Job still pending; resume {job_path} without resubmitting")
