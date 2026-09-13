from pathlib import Path
from datetime import datetime, timezone
import json, os, threading, uuid
from dotenv import load_dotenv
from .models import Scene, Edit, Revision, validate_edit

load_dotenv(os.environ.get("CLEANROOM_ENV_FILE", ".env"))
DATA = Path(os.environ.get("CLEANROOM_DATA_DIR", "data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def identifier(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def media_path(relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ValueError("Media paths must be relative to the data directory")
    p = (DATA / relative).resolve()
    if not p.is_relative_to(DATA):
        raise ValueError("Path must remain inside the data directory")
    return p


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False))
    temp.replace(path)


def scene_path(scene_id):
    if not scene_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid scene id")
    return DATA / "scenes" / scene_id / "scene.json"


def read_scene(scene_id) -> Scene:
    return Scene.model_validate_json(scene_path(scene_id).read_text())


def save_scene(scene: Scene):
    with LOCK:
        write_json(scene_path(scene.id), scene.model_dump(mode="json"))


def list_scenes():
    return [
        Scene.model_validate_json(p.read_text())
        for p in sorted(DATA.glob("scenes/*/scene.json"))
    ]


def propose(scene_id: str, edit: Edit, parent_id: str | None = None):
    with LOCK:
        scene = read_scene(scene_id)
        validate_edit(scene, edit)
        parent = next(
            (
                r
                for r in scene.revisions
                if r.id == (parent_id or scene.current_revision)
            ),
            None,
        )
        if parent is None or parent.status not in ("baseline", "accepted"):
            raise ValueError("Edits must branch from an accepted revision")
        if any(e.id == edit.id for r in scene.revisions for e in r.edits):
            raise ValueError("Edit id already exists")
        revision = Revision(
            id=identifier("revision"),
            parent_id=parent.id,
            label=edit.reason,
            edits=[*parent.edits, edit],
            created_at=timestamp(),
        )
        scene.revisions.append(revision)
        save_scene(scene)
        return revision


def decide(scene_id, revision_id, accept, evaluation):
    with LOCK:
        scene = read_scene(scene_id)
        revision = next(r for r in scene.revisions if r.id == revision_id)
        if revision.status != "candidate":
            raise ValueError("Only pending candidates may be decided")
        if accept and revision.parent_id != scene.current_revision:
            raise ValueError(
                "Scene changed during evaluation; candidate must be reevaluated"
            )
        revision.status = "accepted" if accept else "rejected"
        revision.evaluation = evaluation
        if accept:
            scene.current_revision = revision.id
        save_scene(scene)
        return revision


def event(scene_id, kind, payload):
    entry = {
        "id": identifier("event"),
        "time": timestamp(),
        "kind": kind,
        "payload": payload,
    }
    with LOCK:
        p = scene_path(scene_id).parent / "events.jsonl"
        with p.open("a") as f:
            f.write(json.dumps(entry, allow_nan=False) + "\n")
    return entry
