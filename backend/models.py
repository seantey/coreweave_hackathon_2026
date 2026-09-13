"""Portable scene contracts shared by the editor, automation, and evidence store."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import math


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Vector = tuple[float, float, float]


class Transform(StrictModel):
    position: Vector = (0, 0, 0)
    rotation: Vector = (0, 0, 0)
    scale: Vector = (1, 1, 1)

    @model_validator(mode="after")
    def valid_scale(self):
        if any(s <= 0 or s > 1000 for s in self.scale):
            raise ValueError("Scale must be positive and at most 1000")
        return self


class Bounds(StrictModel):
    minimum: Vector
    maximum: Vector

    @model_validator(mode="after")
    def ordered(self):
        if any(a >= b for a, b in zip(self.minimum, self.maximum)):
            raise ValueError("Every bounds minimum must be less than maximum")
        return self

    def volume(self):
        return math.prod(b-a for a,b in zip(self.minimum, self.maximum))


class Camera(StrictModel):
    position: Vector = (3, 2, 4)
    target: Vector = (0, 0.5, 0)
    fov: float = Field(default=55, ge=15, le=110)

    @model_validator(mode="after")
    def different(self):
        if sum((a-b)**2 for a,b in zip(self.position,self.target)) < 1e-8:
            raise ValueError("Camera position must differ from target")
        return self


class Asset(StrictModel):
    id: str
    label: str
    kind: Literal["splat", "mesh", "box"]
    path: str | None = None
    collider_path: str | None = None
    collider_matrix: tuple[float, ...] | None = None
    transform: Transform = Field(default_factory=Transform)
    size: Vector = (1, 1, 1)
    color: str = "#b9b0a0"
    provenance: str = "Unverified"
    protected: bool = False

    @model_validator(mode="after")
    def valid_matrix(self):
        if self.collider_matrix is not None and len(self.collider_matrix) != 16:
            raise ValueError("Collider matrix must have 16 column-major values")
        return self


class Edit(StrictModel):
    id: str
    operation: Literal["hide_region", "transform_asset", "add_surface"]
    asset_id: str
    reason: str = Field(min_length=5)
    evidence: list[str] = Field(min_length=1)
    bounds: Bounds | None = None
    transform: Transform | None = None
    size: Vector | None = None
    color: str = "#b9b0a0"

    @model_validator(mode="after")
    def arguments_present(self):
        if self.operation == "hide_region" and not self.bounds:
            raise ValueError("hide_region requires bounds")
        if self.operation in ("transform_asset", "add_surface") and not self.transform:
            raise ValueError("This edit requires a transform")
        if self.operation == "add_surface" and (not self.size or any(s <= 0 for s in self.size)):
            raise ValueError("add_surface requires positive size")
        return self


class Revision(StrictModel):
    id: str
    parent_id: str | None = None
    label: str
    edits: list[Edit] = Field(default_factory=list)
    status: Literal["baseline", "candidate", "accepted", "rejected"] = "candidate"
    evaluation: dict | None = None
    created_at: str


class Scene(StrictModel):
    id: str
    title: str
    description: str
    goal: str = "Recreate this same office as if nobody were there. Preserve furniture, layout, and visual identity. Do not redecorate or erase furniture."
    assets: list[Asset]
    references: list[str] = Field(default_factory=list)
    video: str | None = None
    cameras: dict[str, Camera]
    bounds: Bounds
    revisions: list[Revision]
    current_revision: str
    metric_status: str = "unverified"
    source_kind: Literal["captured_room", "object_probe", "synthetic_fixture"] = "captured_room"


def validate_edit(scene: Scene, edit: Edit):
    """Reject unsupported edits and broad erasure before any visual evaluation."""
    assets = {a.id: a for a in scene.assets}
    if edit.operation != "add_surface" and edit.asset_id not in assets:
        raise ValueError("Unknown target asset")
    if edit.operation != 'add_surface' and assets[edit.asset_id].protected:
        raise ValueError('Target is protected')
    if edit.operation == "hide_region":
        target = assets[edit.asset_id]
        if target.kind != "splat":
            raise ValueError("Region removal currently supports splats only")
        if edit.bounds.volume() > scene.bounds.volume() * 0.12:
            raise ValueError("Removal exceeds 12% of scene bounding volume; narrow the region")
        if any(a < s or b > e for a,b,s,e in zip(edit.bounds.minimum,edit.bounds.maximum,scene.bounds.minimum,scene.bounds.maximum)):
            raise ValueError("Removal extends outside declared scene bounds")
    if edit.operation == "add_surface":
        if math.prod(edit.size) * math.prod(edit.transform.scale) > scene.bounds.volume() * 0.12:
            raise ValueError("Surface completion exceeds edit size limit")
    return edit
