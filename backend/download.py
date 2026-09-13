"""Resumable byte-range downloads for large provider reconstruction archives."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import shutil
import time
import httpx


def download_archive(url: str, destination: Path, workers: int = 24):
    if destination.exists():
        return destination
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.head(url)
        response.raise_for_status()
        length = int(response.headers.get("content-length", 0))
        etag = response.headers.get("etag")
        if not length or response.headers.get("accept-ranges") != "bytes":
            with client.stream("GET", url) as stream:
                stream.raise_for_status()
                temporary = destination.with_suffix(".partial")
                with temporary.open("wb") as output:
                    for chunk in stream.iter_bytes():
                        output.write(chunk)
                temporary.replace(destination)
            return destination
    directory = destination.with_suffix(".parts")
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {"length": length, "etag": etag, "chunk_size": 16 * 1024 * 1024}
    manifest = directory / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != metadata:
        raise ValueError("Remote archive changed; retained parts cannot be mixed")
    manifest.write_text(json.dumps(metadata))
    chunk_size = metadata["chunk_size"]
    ranges = [
        (start, min(start + chunk_size, length) - 1)
        for start in range(0, length, chunk_size)
    ]

    def transfer(bounds):
        start, end = bounds
        part = directory / f"{start:012}.part"
        for attempt in range(4):
            present = part.stat().st_size if part.exists() else 0
            if present == end - start + 1:
                return part
            if present > end - start + 1:
                raise ValueError("Oversized archive segment")
            offset = start + present
            try:
                headers = {"Range": f"bytes={offset}-{end}"}
                if etag:
                    headers["If-Match"] = etag
                with httpx.stream(
                    "GET", url, headers=headers, timeout=60, follow_redirects=True
                ) as response:
                    response.raise_for_status()
                    if (
                        response.status_code != 206
                        or response.headers.get("content-range")
                        != f"bytes {offset}-{end}/{length}"
                    ):
                        raise ValueError(
                            "Server did not honor the requested byte range"
                        )
                    with part.open("ab") as output:
                        for chunk in response.iter_bytes():
                            output.write(chunk)
                if part.stat().st_size != end - start + 1:
                    raise httpx.ReadError("Incomplete archive segment")
                return part
            except httpx.TransportError:
                if attempt == 3:
                    raise
                time.sleep(1 + attempt)
        raise RuntimeError("Download attempts exhausted")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        parts = list(executor.map(transfer, ranges))
    assembled = destination.with_suffix(".assembled")
    with assembled.open("wb") as output:
        for part in parts:
            with part.open("rb") as source:
                shutil.copyfileobj(source, output)
    if assembled.stat().st_size != length:
        raise ValueError("Archive byte count mismatch")
    assembled.replace(destination)
    return destination
