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
