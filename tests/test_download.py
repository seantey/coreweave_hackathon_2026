"""Validate that resumed provider downloads cannot mix byte ranges or versions."""

import json
from contextlib import contextmanager
import httpx
import pytest
from backend import download


def mock_archive(monkeypatch, content=b"known archive bytes", honor_range=True):
    request = httpx.Request("HEAD", "https://example.test/archive")

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def head(self, url):
            return httpx.Response(
                200,
                headers={
                    "content-length": str(len(content)),
                    "accept-ranges": "bytes",
                    "etag": "version-1",
                },
                request=request,
            )

    requested = []

    @contextmanager
    def stream(method, url, headers, **kwargs):
        requested.append(headers)
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        response = httpx.Response(
            206 if honor_range else 200,
            headers={"content-range": f"bytes {start}-{end}/{len(content)}"},
            content=content[start : end + 1],
            request=request,
        )
        yield response

    monkeypatch.setattr(download.httpx, "Client", Client)
    monkeypatch.setattr(download.httpx, "stream", stream)
    return requested


def test_partial_chunk_resumes_at_exact_offset(tmp_path, monkeypatch):
    requested = mock_archive(monkeypatch)
    target = tmp_path / "world.zip"
    parts = target.with_suffix(".parts")
    parts.mkdir()
    (parts / "000000000000.part").write_bytes(b"known ")
    download.download_archive("https://example.test/archive", target)
    assert target.read_bytes() == b"known archive bytes"
    assert requested[0]["Range"] == "bytes=6-18"
    assert requested[0]["If-Match"] == "version-1"


def test_wrong_range_response_never_publishes_archive(tmp_path, monkeypatch):
    mock_archive(monkeypatch, honor_range=False)
    target = tmp_path / "world.zip"
    with pytest.raises(ValueError, match="byte range"):
        download.download_archive("https://example.test/archive", target)
    assert not target.exists()


def test_changed_remote_version_rejects_old_parts(tmp_path, monkeypatch):
    mock_archive(monkeypatch)
    target = tmp_path / "world.zip"
    parts = target.with_suffix(".parts")
    parts.mkdir()
    (parts / "manifest.json").write_text(
        json.dumps({"length": 19, "etag": "older", "chunk_size": 16777216})
    )
    with pytest.raises(ValueError, match="changed"):
        download.download_archive("https://example.test/archive", target)
    assert not target.exists()
