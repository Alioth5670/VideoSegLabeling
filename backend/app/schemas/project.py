from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_dir: str | None = Field(default=None, max_length=4096)


class ProjectCreated(BaseModel):
    project_id: str
    name: str


class ProjectInfo(BaseModel):
    project_id: str
    name: str
    videos: list[dict] = []
    active_video_id: str | None = None
    video_path: str | None = None
    frames_dir: str | None = None
    fps: float = 0
    width: int = 0
    height: int = 0
    frame_count: int = 0
    duration: float = 0
    paths: dict[str, str] = {}
    created_at: str
    updated_at: str
