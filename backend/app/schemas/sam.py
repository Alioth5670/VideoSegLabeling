from typing import Literal

from pydantic import BaseModel, Field


class PointPrompt(BaseModel):
    x: float
    y: float
    label: Literal[0, 1]


class SegmentRequest(BaseModel):
    session_id: str | None = None
    frame_index: int
    object_id: int | None = None
    category: str | None = None
    text: str | None = None
    box: list[float] | None = None
    points: list[PointPrompt] = Field(default_factory=list)


class PropagateRequest(BaseModel):
    session_id: str
    object_ids: list[int] | None = None
    start_frame: int
    end_frame: int
    direction: Literal["forward", "backward", "bidirectional"] = "bidirectional"
    mode: Literal["auto", "multiplex", "per_object"] = "auto"
