from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_dir: str | None = Field(default=None, max_length=4096)
    owner_id: str | None = Field(default=None, max_length=80)

    @field_validator('name', mode='before')
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value



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


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator('name', mode='before')
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ProjectTransfer(BaseModel):
    owner_id: str = Field(min_length=1, max_length=80)


class ProjectPermanentDelete(BaseModel):
    confirmation_name: str = Field(min_length=1, max_length=256)
