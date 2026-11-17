import os
import sqlite3

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import account_store, video_service

router = APIRouter(prefix='/api/auth', tags=['accounts'])
COOKIE = 'vsl_session'


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=6, max_length=256)


class PasswordReset(BaseModel):
    password: str = Field(min_length=6, max_length=256)


class PasswordChange(BaseModel):
    model_config = {'extra': 'forbid'}
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=6, max_length=256)


class ActiveUpdate(BaseModel):
    active: bool


def admin_user(request: Request) -> dict:
    user = getattr(request.state, 'user', None)
    if not user or not user['admin']:
        raise HTTPException(403, '需要管理员权限')
    return user


@router.get('/status')
def status() -> dict:
    return {'initialized': account_store.initialized()}


@router.post('/setup')
def setup(payload: Credentials) -> dict:
    if account_store.initialized():
        raise HTTPException(409, '系统已经初始化')
    projects = video_service.list_projects()
    try:
        account_store.create_user(payload.username, payload.password, admin=True, bootstrap=True, projects=projects)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'ok': True}


@router.post('/login')
def login(payload: Credentials, response: Response) -> dict:
    token = account_store.login(payload.username, payload.password)
    if not token:
        raise HTTPException(401, '用户名或密码错误，或账户已停用')
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict',
                        secure=os.getenv('AUTH_COOKIE_SECURE', 'false').lower() == 'true', max_age=86400)
    return {'user': account_store.current_user(token)}


@router.post('/logout')
def logout(request: Request, response: Response) -> dict:
    account_store.logout(request.cookies.get(COOKIE, ''))
    response.delete_cookie(COOKIE)
    return {'ok': True}


@router.get('/me')
def me(request: Request) -> dict:
    return {'user': request.state.user}


@router.get('/users')
def users(request: Request) -> dict:
    admin_user(request)
    return {'users': account_store.users()}


@router.post('/users')
def create_user(payload: Credentials, request: Request) -> dict:
    admin_user(request)
    try:
        return account_store.create_user(payload.username, payload.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, '用户名已存在') from exc


@router.patch('/users/{user_id}')
def update_user(user_id: str, payload: ActiveUpdate, request: Request) -> dict:
    user = admin_user(request)
    if user_id == user['id']:
        raise HTTPException(400, '不能停用自己的账户')
    try:
        account_store.set_active(user_id, payload.active)
    except KeyError as exc:
        raise HTTPException(404, '账户不存在') from exc
    return {'ok': True}


@router.post('/users/{user_id}/password')
def reset_password(user_id: str, payload: PasswordReset, request: Request) -> dict:
    admin_user(request)
    try:
        account_store.reset_password(user_id, payload.password)
    except KeyError as exc:
        raise HTTPException(404, '账户不存在') from exc
    return {'ok': True}


@router.post('/password')
def change_own_password(payload: PasswordChange, request: Request, response: Response) -> dict:
    if not account_store.change_password(request.state.user['id'], payload.current_password, payload.new_password):
        raise HTTPException(400, '当前密码不正确，请重新输入')
    response.delete_cookie(COOKIE)
    return {'ok': True}
