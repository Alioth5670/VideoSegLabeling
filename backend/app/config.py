import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class Settings:
    project_root: Path
    projects_dir: Path
    sam_repo_path: Path
    sam_checkpoint_path: Path
    sam31_checkpoint_path: Path
    sam_backend: str
    sam_precision: str
    sam_device: str
    sam_frame_cache_size: int = 8
    sam_feature_cache_size: int = 4
    sam_offload_state_to_cpu: bool = True
    sam_debug_logging: bool = False


@lru_cache
def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[2]
    settings = Settings(
        project_root=project_root,
        projects_dir=Path(os.getenv("PROJECTS_DIR", project_root / "projects")),
        sam_repo_path=Path(os.getenv("SAM_REPO_PATH", project_root / "sam3")),
        sam_checkpoint_path=Path(os.getenv("SAM_CHECKPOINT_PATH", project_root / "checkpoints" / "sam3.pt")),
        sam31_checkpoint_path=Path(
            os.getenv("SAM31_CHECKPOINT_PATH", project_root / "checkpoints" / "sam3.1_multiplex.pt")
        ),
        sam_debug_logging=os.getenv("SAM_DEBUG_LOGGING", "false").lower() == "true",
        sam_frame_cache_size=max(1, int(os.getenv("SAM_FRAME_CACHE_SIZE", "8"))),
        sam_feature_cache_size=max(1, int(os.getenv("SAM_FEATURE_CACHE_SIZE", "4"))),
        sam_offload_state_to_cpu=os.getenv("SAM_OFFLOAD_STATE_TO_CPU", "true").lower() == "true",
        sam_backend=os.getenv("SAM_BACKEND", "mock"),
        sam_precision=os.getenv("SAM_PRECISION", "bfloat16"),
        sam_device=os.getenv("SAM_DEVICE", os.getenv("SAM_CUDA_DEVICE", "cuda:0")),
    )
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    return settings
