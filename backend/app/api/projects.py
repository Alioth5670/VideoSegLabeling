import shutil

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import account_store, annotation_store, sam_service, settings, video_service, export_jobs
from app.schemas.annotation import ObjectUpdate, TrackedObjectCreate
from app.schemas.project import ProjectCreate, ProjectRename, ProjectTransfer, ProjectPermanentDelete
from app.services.account_store import DuplicateProjectNameError
from app.utils.paths import project_dir
from app.services.project_management import ProjectManagement, ProjectAccessError, ProjectPermissionError

router = APIRouter(prefix="/api/projects", tags=["projects"])
management = ProjectManagement(account_store, video_service)


@router.post("")
def create_project(payload: ProjectCreate, request: Request) -> dict:
    if payload.project_dir and not request.state.user['admin']:
        raise HTTPException(403, '自定义存储路径需要管理员权限')
    owner_id = payload.owner_id or request.state.user['id']
    if owner_id != request.state.user['id'] and not request.state.user['admin']:
        raise HTTPException(403, '不能为其他账户创建项目')
    owner = account_store.user(owner_id)
    if not owner or not owner['active']:
        raise HTTPException(400, '目标账户不存在或已停用')
    try:
        with account_store.project_creation(owner_id, payload.name) as db:
            project = video_service.create_project(payload.name, payload.project_dir)
            account_store.index_project(project, owner_id, connection=db)
        return project
    except DuplicateProjectNameError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=400, detail="Project directory already contains a project.json") from exc


@router.get("")
def list_projects(request: Request, q: str = Query(default='', max_length=120),
                  offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200),
                  owner_id: str | None = None, all_accounts: bool = False, deleted: bool = False) -> dict:
    user = request.state.user
    if not user['admin'] and (all_accounts or owner_id not in (None, user['id'])):
        raise HTTPException(403, '只能管理自己的项目')
    owner = owner_id if user['admin'] and all_accounts else owner_id or user['id']
    result = account_store.list_projects(owner, q, offset, limit, deleted=deleted)
    availability = video_service.project_availability([row['project_id'] for row in result['projects']])
    for row in result['projects']:
        row.update(availability[row['project_id']])
    return result


def change_project(project_id: str, request: Request, **changes) -> dict:
    try:
        return management.change(project_id, request.state.user, **changes)
    except ProjectAccessError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProjectPermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except DuplicateProjectNameError as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, '项目文件不存在') from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, '项目正在推理，请停止任务后再操作') from exc


@router.patch('/{project_id}')
def rename_project(project_id: str, payload: ProjectRename, request: Request) -> dict:
    return change_project(project_id, request, name=payload.name)


@router.post('/{project_id}/transfer')
def transfer_project(project_id: str, payload: ProjectTransfer, request: Request) -> dict:
    if not request.state.user['admin']:
        raise HTTPException(403, '只有管理员可以转移项目')
    return change_project(project_id, request, owner_id=payload.owner_id,
                          before_change=lambda: sam_service.close_project_sessions(project_id))


@router.delete('/{project_id}')
def recycle_project(project_id: str, request: Request) -> dict:
    return change_project(project_id, request, deleted=True,
                          before_change=lambda: sam_service.close_project_sessions(project_id))


@router.delete('/{project_id}/permanent')
def permanently_delete_project(project_id: str, payload: ProjectPermanentDelete, request: Request) -> dict:
    try:
        with export_jobs.project_deletion(project_id):
            management.permanently_delete(project_id, request.state.user, payload.confirmation_name,
                                          before_delete=lambda: sam_service.close_project_sessions(project_id))
    except ProjectAccessError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(409, '删除项目文件失败，项目记录已保留；请检查目录权限后重试') from exc
    return {'ok': True}


@router.post('/{project_id}/restore')
def restore_project(project_id: str, request: Request) -> dict:
    return change_project(project_id, request, deleted=False)


@router.get("/{project_id}")
def get_project(project_id: str, video_id: str | None = Query(default=None), summary: bool = False) -> dict:
    try:
        project = video_service.load_project(project_id)
        if video_id:
            project = video_service.set_active_video(project_id, video_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Video not found") from exc
    return {"project": project, "annotations": (annotation_store.summary(project_id, video_id) if summary else annotation_store.load(project_id, video_id))}


@router.get("/{project_id}/videos")
def list_videos(project_id: str) -> dict:
    try:
        project = video_service.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return {"videos": project.get("videos", []), "active_video_id": project.get("active_video_id")}


@router.post("/{project_id}/videos/{video_id}/activate")
def activate_video(project_id: str, video_id: str, summary: bool = False) -> dict:
    try:
        project = video_service.set_active_video(project_id, video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Video not found") from exc
    return {"project": project, "annotations": (annotation_store.summary(project_id, video_id) if summary else annotation_store.load(project_id, video_id))}


@router.post("/{project_id}/objects")
def create_object(project_id: str, payload: TrackedObjectCreate, video_id: str | None = Query(default=None)) -> dict:
    obj = annotation_store.ensure_object(project_id, None, payload.category, payload.frame_index, video_id)
    if payload.color is not None:
        obj = annotation_store.update_object(project_id, obj["object_id"], {"color": list(payload.color)}, video_id)
    return obj


@router.patch("/{project_id}/objects/{object_id}")
def update_object(project_id: str, object_id: int, payload: ObjectUpdate, video_id: str | None = Query(default=None)) -> dict:
    try:
        return annotation_store.update_object(project_id, object_id, payload.model_dump(), video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Object not found") from exc


@router.post("/{project_id}/objects/{object_id}/session/remove")
def remove_object_from_session(
    project_id: str,
    object_id: int,
    session_id: str = Query(...),
    video_id: str | None = Query(default=None),
) -> dict:
    _ = video_service.active_video_id(project_id, video_id)
    try:
        sam_service.remove_object(project_id, session_id, object_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "object_id": object_id, "session_id": session_id}


@router.delete("/{project_id}/objects/{object_id}")
def delete_object(
    project_id: str,
    object_id: int,
    video_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
) -> dict:
    sam_warning = None
    sam_removed = False
    if session_id:
        try:
            sam_service.remove_object(project_id, session_id, object_id)
            sam_removed = True
        except Exception as exc:
            sam_warning = str(exc)
    annotation_store.delete_object(project_id, object_id, video_id)
    resolved_video_id = video_service.active_video_id(project_id, video_id)
    root = project_dir(settings.projects_dir, project_id)
    base = video_service.video_path(project_id, resolved_video_id) if resolved_video_id else root
    shutil.rmtree(base / "masks" / f"object_{object_id}", ignore_errors=True)
    return {"ok": True, "sam_removed": sam_removed, "sam_warning": sam_warning}
