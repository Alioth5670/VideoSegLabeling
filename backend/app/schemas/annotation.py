from pydantic import BaseModel, Field


class ObjectUpdate(BaseModel):
    category: str | None = None
    visible: bool | None = None
    locked: bool | None = None
    color: tuple[int, int, int] | None = None


class ManualMaskRequest(BaseModel):
    frame_index: int
    object_id: int | None = None
    mask: str
    format: str = "png_base64"
    is_keyframe: bool = True
    allow_overwrite: bool = False


class ManualPolygonRequest(BaseModel):
    frame_index: int
    object_id: int | None = None
    polygons: list[list[tuple[float, float]]]
    is_keyframe: bool = True
    allow_overwrite: bool = False


class ManualBBoxRequest(BaseModel):
    frame_index: int
    object_id: int | None = None
    bbox: tuple[float, float, float, float]
    is_keyframe: bool = True
    allow_overwrite: bool = False


class BatchDeleteAnnotationsRequest(BaseModel):
    start_frame: int
    end_frame: int
    object_ids: list[int] | None = None
    delete_annotations: bool = True
    delete_prompts: bool = True


class TrackedObjectCreate(BaseModel):
    category: str = "object"
    frame_index: int = 0
    color: tuple[int, int, int] | None = None
