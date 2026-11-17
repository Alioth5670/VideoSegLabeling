from app.config import get_settings
from app.services.annotation_store import AnnotationStore
from app.services.export_jobs import ExportJobs
from app.services.sam_pool import SAMPool
from app.services.video_service import VideoService

settings = get_settings()
video_service = VideoService(settings.projects_dir)
annotation_store = AnnotationStore(settings.projects_dir)
sam_service = SAMPool(settings, annotation_store)

account_store = video_service.account_store

export_jobs = ExportJobs(settings.projects_dir)
