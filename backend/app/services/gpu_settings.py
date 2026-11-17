"""Validated administrator settings; runtime overrides live with project metadata."""
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GPUSettings(BaseModel):
    model_config = {'extra': 'forbid'}
    sam_backend: Literal['mock', 'sam3_video', 'sam3_multiplex_video']
    sam_gpu_pool: bool = Field(strict=True)
    sam_gpu_devices: str = Field(max_length=4096)
    sam_gpu_min_free_mb: int = Field(strict=True, ge=1, le=1048576)
    sam_gpu_max_used_mb: int = Field(strict=True, ge=0, le=1048576)
    sam_gpu_max_utilization: int = Field(strict=True, ge=0, le=100)
    sam_session_idle_seconds: int = Field(strict=True, ge=30, le=604800)
    sam_worker_timeout_seconds: int = Field(strict=True, ge=30, le=86400)

    @field_validator('sam_gpu_devices')
    @classmethod
    def devices(cls, value):
        parts = [part.strip() for part in value.split(',') if part.strip()]
        if any(not re.fullmatch(r'(?:\d+|GPU-[a-zA-Z0-9-]+)', part) for part in parts):
            raise ValueError('显卡列表只能包含物理编号或 GPU UUID，以逗号分隔')
        return ','.join(dict.fromkeys(parts))

    @classmethod
    def from_config(cls, config):
        return cls(**{name: getattr(config, name) for name in cls.model_fields})


def load_gpu_settings(path: Path, config) -> GPUSettings:
    defaults = GPUSettings.from_config(config).model_dump()
    if path.exists():
        defaults.update(json.loads(path.read_text(encoding='utf-8')))
    return GPUSettings(**defaults)


def save_gpu_settings(path: Path, values: GPUSettings):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(values.model_dump(), stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
