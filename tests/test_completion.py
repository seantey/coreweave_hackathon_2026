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
        lambda *args: {"accepted": True, "assessment": {"people_absent": True, "furniture_preserved": True, "layout_preserved": True, "new_visible_damage": False, "evidence": "Broad review missed an occupant", "remaining_issues": [], "uncertainties": []}},
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


def test_masked_edit_preserves_unselected_pixels_inside_crop(tmp_path, monkeypatch):
    import numpy as np
    monkeypatch.setattr(completion, 'media_path', lambda path: tmp_path / path)
    source = tmp_path / 'source.png'
    Image.new('RGB', (200, 100), 'red').save(source)
    mask = Image.new('L', (200, 100), 0)
    mask.paste(255, (95, 45, 105, 55))
    mask.save(tmp_path / 'mask.png')
    output = tmp_path / 'edit'
    output.mkdir()
    (output / 'job.json').write_text('{}')
    Image.new('RGB', (200, 100), 'blue').save(output / 'edited-crop.png')
    monkeypatch.setattr(completion.fal_jobs, 'resume', lambda *args, **kwargs: {})
    result = completion.edit_completion(str(source), str(source), 'Remove the person', str(output),
                                        {'minimum': [.1, .1], 'maximum': [.9, .9]}, 'mask.png')
    edited = np.array(Image.open(result['candidate']))
    assert (edited[50, 100] == [0, 0, 255]).all()
    assert (edited[25, 40] == [255, 0, 0]).all()
    assert (edited[:10] == [255, 0, 0]).all()


def test_uncertainty_review_requires_every_question_and_keeps_visible_ambiguity(monkeypatch):
    import json
    import pytest
    monkeypatch.setattr(completion, 'read_images', lambda paths: [])
    monkeypatch.setattr(completion.Image, 'open', lambda path: Image.new('RGB', (40, 20)))
    responses = iter([
        {'decisions': [{'index': 0, 'category': 'unobserved_surface', 'evidence': 'Surface was occluded'}]},
        {'decisions': [{'index': 0, 'category': 'unobserved_surface', 'evidence': 'Surface was occluded'},
                       {'index': 1, 'category': 'unresolved_visible', 'evidence': 'Possible head remains visible'}]},
    ])
    monkeypatch.setattr(completion.agent, 'vision_review', lambda *args: {'text': json.dumps(next(responses))})
    evaluation = {'assessment': {'uncertainties': ['Hidden surface', 'Possible person']}}
    with pytest.raises(ValueError, match='each original question'):
        completion.review_visible_uncertainties('source', 'candidate', evaluation)
    assert completion.review_visible_uncertainties('source', 'candidate', evaluation)['visible_questions_resolved'] is False


def test_regional_generation_receives_original_reference_at_matching_coordinates(tmp_path, monkeypatch):
    import base64
    import io
    source = tmp_path / 'source.png'
    original = Image.new('RGB', (400, 200), 'red')
    original.paste('green', (200, 0, 400, 200))
    original.save(source)
    candidate = tmp_path / 'candidate.png'
    Image.new('RGB', (200, 100), 'blue').save(candidate)
    output = tmp_path / 'edit'
    output.mkdir()
    Image.new('RGB', (200, 100), 'blue').save(output / 'edited-crop.png')
    received = []
    def submit(endpoint, payload, directory):
        received.extend(Image.open(io.BytesIO(base64.b64decode(value.split(',', 1)[1]))).copy()
                        for value in payload['image_urls'])
        path = directory / 'job.json'
        path.write_text('{}')
        return path
    monkeypatch.setattr(completion.fal_jobs, 'submit', submit)
    monkeypatch.setattr(completion.fal_jobs, 'resume', lambda *args, **kwargs: {})
    completion.edit_completion(str(source), str(candidate), 'Preserve original furnishings', str(output),
                               {'minimum': [.6, .2], 'maximum': [.9, .8]})
    assert len(received) == 2
    assert received[0].size == received[1].size
    assert received[0].getpixel((100, 100)) == (0, 0, 255)
    assert received[1].getpixel((100, 100)) == (0, 128, 0)
