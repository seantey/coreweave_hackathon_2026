"""Provider protocol checks run without paid inference or real credentials."""

import json
import httpx
import pytest
from PIL import Image
from backend import fal_jobs, worldlabs
from backend.models import Asset


def install_transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_fal_resume_does_not_resubmit_completed_job(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fixture")
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "request_id": "fixture",
                    "status_url": "https://queue.fal.run/status",
                    "response_url": "https://queue.fal.run/result",
                },
            )
        if request.url.path == "/status":
            return httpx.Response(200, json={"status": "COMPLETED"})
        return httpx.Response(200, json={"masks": []})

    install_transport(monkeypatch, handler)
    path = fal_jobs.submit("fal-ai/sam-3/image", {"prompt": "person"}, tmp_path)
    assert fal_jobs.resume(path) == {"masks": []}
    assert fal_jobs.resume(path) == {"masks": []}
    assert calls == ["POST", "GET", "GET"]
    with pytest.raises(ValueError, match="already submitted"):
        fal_jobs.submit("fal-ai/sam-3/image", {}, tmp_path)


def test_fal_refuses_to_send_key_to_foreign_polling_host(tmp_path, monkeypatch):
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {
                "status_url": "https://example.com/status",
                "response_url": "https://queue.fal.run/result",
            }
        )
    )
    with pytest.raises(ValueError, match="fal queue"):
        fal_jobs.resume(path)


def test_marble_generation_checkpoints_operation_before_polling(tmp_path, monkeypatch):
    monkeypatch.setenv("WORLDLABS_API_KEY", "fixture")
    monkeypatch.setattr(worldlabs, "DATA", tmp_path)
    image = tmp_path / "input.png"
    Image.new("RGB", (4, 4)).save(image)
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["permission"]["public"] is False
            assert payload["world_prompt"]["image_prompt"]["source"] == "data_base64"
            return httpx.Response(200, json={"operation_id": "fixture", "done": False})
        return httpx.Response(
            200,
            json={
                "operation_id": "fixture",
                "done": True,
                "response": {"world_id": "world-fixture"},
            },
        )

    install_transport(monkeypatch, handler)
    path = worldlabs.generate(image, "Preserve the office", "Test")
    assert json.loads(path.read_text())["operation_id"] == "fixture"
    assert len(requests) == 1
    assert worldlabs.resume(path) == {"world_id": "world-fixture"}
    assert [request.method for request in requests] == ["POST", "GET"]


def test_remote_assets_cannot_embed_credentials_or_ambiguous_sources():
    with pytest.raises(ValueError):
        Asset(
            id="bad",
            label="Bad",
            kind="splat",
            remote_url="https://user:password@example.com/world.rad",
        )
    with pytest.raises(ValueError):
        Asset(
            id="bad",
            label="Bad",
            kind="splat",
            remote_url="https://example.com/world.rad",
            path="world.ply",
        )
