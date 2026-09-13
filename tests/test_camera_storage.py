"""Saved evidence views must stay reproducible when later inspections add cameras."""

import pytest
from backend import storage
from backend.models import Scene, Asset, Bounds, Camera, Revision


def test_saved_view_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    scene = Scene(
        id="fixture",
        title="Fixture",
        description="Test only",
        assets=[Asset(id="room", label="Room", kind="mesh")],
        cameras={"original-view": Camera()},
        bounds=Bounds(minimum=(-5, -5, -5), maximum=(5, 5, 5)),
        revisions=[
            Revision(
                id="original",
                label="Original",
                status="baseline",
                created_at=storage.timestamp(),
            )
        ],
        current_revision="original",
    )
    storage.save_scene(scene)
    new = Camera(position=(1, 1, 1), target=(0, 0, 0))
    name = storage.save_camera(scene.id, new, "Inspect from the side")
    with pytest.raises(ValueError, match="overwritten"):
        storage.save_camera(scene.id, new, "Replace prior evidence", "original-view")
    current = storage.read_scene(scene.id)
    assert current.cameras[name] == new
    assert current.cameras["original-view"] == Camera()
    assert current.revisions == scene.revisions
    assert current.current_revision == "original"


def test_asset_removal_cannot_erase_remaining_scene(tmp_path, monkeypatch):
    from backend.models import Edit

    monkeypatch.setattr(storage, "DATA", tmp_path)
    scene = Scene(
        id="fixture",
        title="Fixture",
        description="Test only",
        assets=[
            Asset(id="person-layer", label="Layer", kind="mesh"),
            Asset(id="room", label="Room", kind="mesh"),
        ],
        cameras={"Front": Camera()},
        bounds=Bounds(minimum=(-5, -5, -5), maximum=(5, 5, 5)),
        revisions=[
            Revision(
                id="original",
                label="Original",
                status="baseline",
                created_at=storage.timestamp(),
            )
        ],
        current_revision="original",
    )
    storage.save_scene(scene)
    first = storage.propose(
        scene.id,
        Edit(
            id="remove-person",
            operation="hide_asset",
            asset_id="person-layer",
            reason="Synthetic removal test",
            evidence=["Front"],
        ),
    )
    storage.decide(scene.id, first.id, True, {"source": "test fixture"})
    with pytest.raises(ValueError, match="only visible"):
        storage.propose(
            scene.id,
            Edit(
                id="remove-room",
                operation="hide_asset",
                asset_id="room",
                reason="Synthetic removal test",
                evidence=["Front"],
            ),
        )
    assert storage.read_scene(scene.id).current_revision == first.id
