"""Exercise loop decisions locally; mocked model output is not a model-quality evaluation."""

import json
import pytest
from PIL import Image
from backend import agent, storage
from backend.models import Scene, Asset, Camera, Bounds, Revision


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    monkeypatch.setattr(agent, "DATA", tmp_path)
    monkeypatch.setattr(agent, "CLIENT", None)
    scene = Scene(
        id="fixture",
        title="Test fixture",
        description="Synthetic unit test",
        source_kind="synthetic_fixture",
        assets=[Asset(id="room", label="Room", kind="splat")],
        cameras={name: Camera() for name in ("Front", "Side", "Back")},
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
    storage.save_scene(scene)
    captures = []

    def capture(scene_id, revision, camera):
        name = f"{revision}-{camera}.png"
        Image.new("RGB", (32, 32), "black" if revision == "original" else "white").save(
            tmp_path / name
        )
        captures.append((revision, camera))
        return {
            "image": name,
            "scene_id": scene_id,
            "revision_id": revision,
            "camera_name": camera,
            "camera_matrix": [1, 0, 0, 1],
            "projection_matrix": [1, 0, 0, 1],
            "viewport": [32, 32],
        }

    monkeypatch.setattr(agent, "capture", capture)
    monkeypatch.setattr(
        agent,
        "observe_scene",
        lambda *args: {
            "assessment": {
                "next_action": "repair",
                "edit": {
                    "operation": "hide_region",
                    "asset_id": "room",
                    "reason": "Known synthetic test defect",
                    "evidence": ["Front"],
                    "bounds": {"minimum": [0, 0, 0], "maximum": [0.5, 1, 0.5]},
                },
            }
        },
    )
    return tmp_path, captures


def model_result(**overrides):
    value = {
        "defect_resolved": True,
        "furniture_preserved": True,
        "new_visible_damage": False,
        "evidence": "The fixture change is visible in all supplied views.",
        "uncertainties": [],
    }
    value.update(overrides)
    return {"text": json.dumps(value)}


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({}, "accepted"),
        ({"furniture_preserved": None}, "rejected"),
        ({"uncertainties": ["Furniture behind the edit is not visible"]}, "rejected"),
        ({"new_visible_damage": True}, "rejected"),
    ],
)
def test_loop_decisions_and_held_out_camera(
    workspace, monkeypatch, overrides, expected
):
    monkeypatch.setattr(
        agent.providers, "vision", lambda *args, **kwargs: model_result(**overrides)
    )
    result = agent.repair_loop("fixture", 1)
    scene = storage.read_scene("fixture")
    assert result["passes"][0]["outcome"] == expected
    assert scene.revisions[-1].status == expected
    assert (scene.current_revision != "original") == (expected == "accepted")
    assert ("original", "Back") in workspace[1]
    assert (scene.revisions[-1].id, "Back") in workspace[1]


def test_malformed_evaluator_cannot_accept_candidate(workspace, monkeypatch):
    monkeypatch.setattr(
        agent.providers, "vision", lambda *args, **kwargs: model_result(defect_resolved="true")
    )
    with pytest.raises(ValueError):
        agent.repair_loop("fixture", 1)
    scene = storage.read_scene("fixture")
    assert scene.current_revision == "original"
    assert scene.revisions[-1].status == "rejected"


def test_identical_views_reject_without_paid_judgment(workspace, monkeypatch):
    original_capture = agent.capture

    def unchanged(scene_id, revision, camera):
        return original_capture(scene_id, "original", camera)

    monkeypatch.setattr(agent, "capture", unchanged)

    def forbidden(*args):
        raise AssertionError("Unchanged candidate should not invoke inference")

    monkeypatch.setattr(agent.providers, "vision", forbidden)
    result = agent.repair_loop("fixture", 1)
    assert result["passes"][0]["outcome"] == "rejected"


def test_camera_mismatch_rejects_candidate(workspace, monkeypatch):
    original_capture = agent.capture

    def moved(scene_id, revision, camera):
        record = original_capture(scene_id, revision, camera)
        if revision != "original":
            record["camera_matrix"] = [2, 0, 0, 1]
        return record

    monkeypatch.setattr(agent, "capture", moved)
    with pytest.raises(ValueError, match="camera mismatch"):
        agent.repair_loop("fixture", 1)
    assert storage.read_scene("fixture").current_revision == "original"


def test_rejected_edit_cannot_be_repeated_in_same_run(workspace, monkeypatch):
    calls = []

    def reject(*args, **kwargs):
        calls.append(1)
        return model_result(new_visible_damage=True)

    monkeypatch.setattr(agent.providers, "vision", reject)
    result = agent.repair_loop("fixture", 2)
    assert result["passes"][0]["outcome"] == "rejected"
    assert (
        result["passes"][1]["reason"] == "Repeated proposal; no new spatial hypothesis"
    )
    assert len(calls) == 1
    assert len(storage.read_scene("fixture").revisions) == 2


def test_new_hypothesis_can_follow_rejection(workspace, monkeypatch):
    original_observe = agent.observe_scene
    observations = []

    def revised_hypothesis(*args):
        choice = original_observe(*args)
        if observations:
            assert storage.read_scene("fixture").revisions[-1].status == "rejected"
            choice["assessment"]["edit"]["bounds"]["maximum"] = [0.25, 1, 0.25]
        observations.append(1)
        return choice

    results = iter([model_result(new_visible_damage=True), model_result()])
    monkeypatch.setattr(agent, "observe_scene", revised_hypothesis)
    monkeypatch.setattr(agent.providers, "vision", lambda *args, **kwargs: next(results))
    result = agent.repair_loop("fixture", 2)
    assert [step["outcome"] for step in result["passes"]] == ["rejected", "accepted"]
    scene = storage.read_scene("fixture")
    assert scene.revisions[-1].parent_id == "original"
    assert len(scene.revisions[-1].edits) == 1
