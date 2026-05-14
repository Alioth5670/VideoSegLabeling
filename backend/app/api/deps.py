from app.config import get_settings
from app.services.annotation_store import AnnotationStore
from app.services.export_service import ExportService
from app.services.sam_service import SAMService
from app.services.video_service import VideoService

settings = get_settings()
video_service = VideoService(settings.projects_dir)
annotation_store = AnnotationStore(settings.projects_dir)
sam_service = SAMService(settings, annotation_store)
export_service = ExportService(settings.projects_dir)
