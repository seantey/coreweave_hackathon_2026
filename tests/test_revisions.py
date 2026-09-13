import pytest
from pydantic import ValidationError
from backend.models import Scene, Asset, Camera, Bounds, Revision, Edit, Transform
from backend import storage


@pytest.fixture
def scene(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    s = Scene(
        id="office",
        title="Office",
        description="Test",
        assets=[Asset(id="room", label="Room", kind="splat")],
        cameras={"Front": Camera()},
        bounds=Bounds(minimum=(-5, -1, -5), maximum=(5, 4, 5)),
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
    storage.save_scene(s)
    return s


def removal(id="remove-person"):
    return Edit(
        id=id,
        operation="hide_region",
        asset_id="room",
        reason="Remove identified person",
        evidence=["Front", "Side"],
        bounds=Bounds(minimum=(0, 0, 0), maximum=(0.5, 1.8, 0.5)),
    )


def test_rejected_candidate_does_not_change_scene(scene):
    r = storage.propose(scene.id, removal())
    assert storage.read_scene(scene.id).current_revision == "original"
    storage.decide(scene.id, r.id, False, {"new_visible_damage": True})
    s = storage.read_scene(scene.id)
    assert s.current_revision == "original"
    assert s.revisions[-1].status == "rejected"


def test_branch_from_stale_scene_cannot_overwrite_accepted_work(scene):
    a = storage.propose(scene.id, removal("a"))
    b = storage.propose(scene.id, removal("b"))
    storage.decide(scene.id, a.id, True, {"source": "test"})
    with pytest.raises(ValueError, match="Scene changed"):
        storage.decide(scene.id, b.id, True, {})
    assert storage.read_scene(scene.id).current_revision == a.id


def test_mass_erasure_is_rejected(scene):
    edit = removal().model_copy(update={"bounds": scene.bounds})
    with pytest.raises(ValueError, match="12%"):
        storage.propose(scene.id, edit)


def test_edits_accumulate_without_mutating_original(scene):
    first = storage.propose(scene.id, removal("first"))
    storage.decide(scene.id, first.id, True, {})
    second = storage.propose(scene.id, removal("second"))
    assert len(second.edits) == 2
    assert not storage.read_scene(scene.id).revisions[0].edits


def test_asset_path_cannot_escape_data(scene):
    with pytest.raises(ValueError):
        storage.media_path("../.env")
    with pytest.raises(ValueError):
        storage.media_path(str(storage.DATA / "image.png"))


def test_invalid_geometry_is_rejected():
    with pytest.raises(ValidationError):
        Bounds(minimum=(0, 0, 0), maximum=(0, 1, 1))
    with pytest.raises(ValidationError):
        Transform(scale=(-1, 1, 1))
    with pytest.raises(ValidationError):
        Camera(position=(0, 0, 0), target=(0, 0, 0))
    with pytest.raises(ValidationError):
        Transform(position=(float("nan"), 0, 0))


def test_protected_asset_cannot_be_moved(scene):
    scene.assets[0].protected = True
    storage.save_scene(scene)
    edit = Edit(
        id="move",
        operation="transform_asset",
        asset_id="room",
        reason="Move protected asset",
        evidence=["Front"],
        transform=Transform(position=(1, 0, 0)),
    )
    with pytest.raises(ValueError, match="protected"):
        storage.propose(scene.id, edit)


def test_scaled_surface_cannot_bypass_size_limit(scene):
    edit = Edit(
        id="surface",
        operation="add_surface",
        asset_id="surface",
        reason="Complete a surface",
        evidence=["Front"],
        size=(1, 1, 1),
        transform=Transform(scale=(10, 10, 10)),
    )
    with pytest.raises(ValueError, match="size limit"):
        storage.propose(scene.id, edit)


def test_library_placement_does_not_change_original(scene):
    scene.assets.append(
        Asset(
            id="chair-library",
            label="Reusable chair",
            kind="splat",
            initially_visible=False,
        )
    )
    storage.save_scene(scene)
    edit = Edit(
        id="place",
        operation="place_asset",
        asset_id="chair-library",
        reason="Replace incomplete chair",
        evidence=["Front"],
        transform=Transform(position=(1, 0, 0)),
    )
    revision = storage.propose(scene.id, edit)
    saved = storage.read_scene(scene.id)
    assert saved.current_revision == "original"
    assert not saved.revisions[0].edits
    assert not saved.assets[-1].initially_visible
    assert revision.edits[-1].operation == "place_asset"
