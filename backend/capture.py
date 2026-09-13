import os
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
from .models import ImageRegion
from .storage import DATA, identifier, write_json


def capture(
    scene_id: str, revision_id: str, camera_name: str, region: ImageRegion | None = None
):
    """Render the same scene revision and calibrated camera used by the interactive UI."""
    base = os.environ.get("CLEANROOM_VIEWER_URL", "http://127.0.0.1:5173")
    directory = DATA / "captures" / identifier("view")
    directory.mkdir(parents=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", headless=True, args=["--use-angle=metal"]
        )
        try:
            page = browser.new_page(
                viewport={"width": 1280, "height": 900}, device_scale_factor=1
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            query = urlencode(
                {"scene": scene_id, "revision": revision_id, "capture": 1}
            )
            page.goto(f"{base}/?{query}", wait_until="networkidle", timeout=90000)
            page.wait_for_function("window.cleanroom?.ready === true", timeout=90000)
            info = page.evaluate(
                "async name => await window.cleanroom.capture(name)", camera_name
            )
            if info["scene_id"] != scene_id or info["revision_id"] != revision_id:
                raise ValueError("Viewer did not load the requested scene revision")
            if errors:
                raise RuntimeError("Viewer failed during capture: " + errors[0])
            if region:
                info["geometry_probe"] = page.evaluate(
                    "region => window.cleanroom.probeRegion(region)",
                    region.model_dump(),
                )
            page.locator("#viewport canvas").screenshot(
                path=str(directory / "image.png")
            )
            write_json(directory / "camera.json", info)
        finally:
            browser.close()
    return {
        "image": str((directory / "image.png").relative_to(DATA)),
        "metadata": str((directory / "camera.json").relative_to(DATA)),
        **info,
    }
