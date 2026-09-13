"""Test completion feedback and checkpoint replay without calling generation models."""

from pathlib import Path
from PIL import Image
from backend import completion


def test_rejected_completion_is_revised_and_checkpoints_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(completion, "DATA", tmp_path)
    source = tmp_path / "input.png"
    Image.new("RGB", (40, 20), "red").save(source)
    evaluations = iter(
        [
            {
                "accepted": False,
                "assessment": {"remaining_issues": ["person at right desk"]},
            },
            {"accepted": True, "assessment": {"remaining_issues": []}},
        ]
    )
    feedback = []

    def plan(original, candidate, evaluation):
        feedback.append(evaluation)
        return {
            "plan": {
                "action": "edit",
                "reason": "Remove observed occupant",
                "edit_prompt": "Remove the person at right desk; preserve the chair",
            }
        }

    def edit(original, candidate, instruction, directory):
        path = Path(directory) / "candidate.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 20), "blue").save(path)
        return {"candidate": str(path)}

    monkeypatch.setattr(
        completion, "evaluate_completion", lambda *args: next(evaluations)
    )
    monkeypatch.setattr(completion, "plan_completion", plan)
    monkeypatch.setattr(completion, "edit_completion", edit)
    result = completion.completion_loop(str(source), "example", 2)
    assert result["accepted"] is True
    assert len(result["history"]) == 2
    assert feedback[0]["assessment"]["remaining_issues"] == ["person at right desk"]
    # Resuming uses saved judgments and plans; edit_completion owns paid-job replay.
    repeated = completion.completion_loop(str(source), "example", 2)
    assert repeated == result
    assert len(feedback) == 1


def test_ambiguous_outcome_cannot_pass():
    assessment = completion.Assessment(
        people_absent=True,
        furniture_preserved=True,
        layout_preserved=True,
        new_visible_damage=False,
        evidence="No definite person",
        remaining_issues=[],
        uncertainties=["Shape behind divider is unresolved"],
    )
    assert not assessment.passes()


def test_unapproved_input_cannot_start_world_generation(tmp_path, monkeypatch):
    import json
    import pytest

    monkeypatch.setattr(completion, "DATA", tmp_path)
    directory = tmp_path / "completion" / "uncertain"
    directory.mkdir(parents=True)
    (directory / "summary.json").write_text(json.dumps({"accepted": False}))

    def forbidden(*args, **kwargs):
        raise AssertionError("Do not spend on unapproved input")

    monkeypatch.setattr(completion.fal_jobs, "submit", forbidden)
    with pytest.raises(ValueError, match="not passed"):
        completion.reconstruct_completion("uncertain", "room", "reference.png")


def test_localized_person_evidence_blocks_broad_absence_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(completion, "DATA", tmp_path)
    source = tmp_path / "source.png"
    Image.new("RGB", (40, 20), "red").save(source)
    monkeypatch.setattr(
        completion,
        "evaluate_completion",
        lambda *args: {"accepted": True, "assessment": {"people_absent": True}},
    )
    monkeypatch.setattr(
        completion,
        "audit_completion_people",
        lambda *args: {
            "people_count": 1,
            "uncertain_count": 0,
            "sheets": [],
            "detections": [{"classification": "person"}],
        },
    )
    result = completion.completion_loop(str(source), "audit-example", 0)
    assert result["accepted"] is False
    assert result["history"][0]["evaluation"].endswith(
        "evaluation-with-person-audit.json"
    )


def test_regional_edit_preserves_every_pixel_outside_crop(tmp_path, monkeypatch):
    import numpy as np

    source = tmp_path / "source.png"
    Image.new("RGB", (100, 50), "red").save(source)
    output = tmp_path / "edit"
    output.mkdir()
    (output / "job.json").write_text("{}")
    Image.new("RGB", (200, 100), "blue").save(output / "edited-crop.png")
    monkeypatch.setattr(completion.fal_jobs, "resume", lambda *args, **kwargs: {})
    result = completion.edit_completion(
        str(source),
        str(source),
        "Remove the observed person",
        str(output),
        {"minimum": [0.3, 0.2], "maximum": [0.7, 0.8]},
    )
    original = np.array(Image.open(source))
    edited = np.array(Image.open(result["candidate"]))
    outside = np.ones((50, 100), dtype=bool)
    outside[10:40, 30:70] = False
    assert np.array_equal(original[outside], edited[outside])
    assert not np.array_equal(original[25, 50], edited[25, 50])
