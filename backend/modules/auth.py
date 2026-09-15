import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Literal
import bcrypt
import jwt
from fastapi import APIRouter, Request, Response, Depends
from pydantic import BaseModel, ConfigDict, Field
from core.config import setting, TRUSTED_ORIGINS
from core.database import db, uid, now
from core.errors import fail
router = APIRouter(prefix='/api/auth', tags=['Identity'])
# One configured lifetime drives both the JWT exp claim and the cookie max_age so they can never drift apart.
SESSION_SECONDS = int(float(setting('SESSION_HOURS')) * 3600)
if not 1 <= SESSION_SECONDS <= 7 * 24 * 3600:
    raise RuntimeError('SESSION_HOURS must be between 0.0003 and 168 hours.')
class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Login(StrictModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=72)
class Principal(BaseModel):
    id: str
    name: str
    email: str
    role: Literal['citizen', 'operator', 'auditor', 'official', 'service']
    department: str | None = None
    subject: str | None = None
    designation: str | None = None
    unit: str | None = None
    unit_name: str | None = None
class IdentityAdapter:
    async def authenticate_user(self, email: str, password: str):
        raise NotImplementedError
class MockIdentityAdapter(IdentityAdapter):
    async def authenticate_user(self, email, password):
        user = await db.users.find_one({'email': email.lower(), 'active': True}, {'_id': 0})
        if not user or not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
            fail(401, 'INVALID_CREDENTIALS', 'Email or password is incorrect.')
        return user
async def principal(request: Request) -> Principal:
    token = request.cookies.get('samanvay_session')
    if not token:
        fail(401, 'AUTH_REQUIRED', 'Please sign in to continue.')
    try:
        claims = jwt.decode(token, setting('JWT_SECRET'), algorithms=['HS256'], audience='samanvay', issuer='samanvay-demo')
    except jwt.PyJWTError:
        fail(401, 'INVALID_SESSION', 'Your session has expired. Please sign in again.')
    session = await db.sessions.find_one({'id': claims['sid'], 'revoked': False}, {'_id': 0})
    user = await db.users.find_one({'id': claims['sub'], 'active': True}, {'_id': 0})
    if not session or not user:
        fail(401, 'INVALID_SESSION', 'Your session is no longer active.')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        csrf = request.headers.get('x-csrf-token', '')
        if not secrets.compare_digest(hashlib.sha256(csrf.encode()).hexdigest(), session['csrf_hash']):
            fail(403, 'CSRF_DENIED', 'Invalid request verification token.')
        if request.headers.get('origin') not in (None, *TRUSTED_ORIGINS):
            fail(403, 'ORIGIN_DENIED', 'Request origin is not permitted.')
    request.state.session_id = session['id']
    return Principal(**user)
@router.post('/login', response_model=Principal)
async def login(body: Login, request: Request, response: Response):
    # The preview proxy rewrites Origin; browser Fetch Metadata preserves
    # whether this login was initiated by another site or sibling origin.
    if request.headers.get('sec-fetch-site') in ('cross-site', 'same-site'):
        fail(403, 'ORIGIN_DENIED', 'Request origin is not permitted.')
    if request.headers.get('origin') not in (None, *TRUSTED_ORIGINS):
        fail(403, 'ORIGIN_DENIED', 'Request origin is not permitted.')
    user = await MockIdentityAdapter().authenticate_user(body.email, body.password)
    sid, csrf = uid('SESSION'), secrets.token_urlsafe(32)
    await db.sessions.insert_one({'id': sid, 'user_id': user['id'], 'revoked': False, 'csrf_hash': hashlib.sha256(csrf.encode()).hexdigest(), 'created_at': now()})
    # SameSite=None so the session survives when the app is embedded in a preview/portal frame;
    # cross-site abuse is blocked by the exact Origin allow-list, Fetch Metadata guard and session-bound CSRF token.
    token = jwt.encode({'sub': user['id'], 'sid': sid, 'aud': 'samanvay', 'iss': 'samanvay-demo', 'exp': datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)}, setting('JWT_SECRET'), algorithm='HS256')
    response.set_cookie('samanvay_session', token, secure=True, httponly=True, samesite='none', max_age=SESSION_SECONDS, path='/api')
    response.set_cookie('samanvay_csrf', csrf, secure=True, httponly=False, samesite='none', max_age=SESSION_SECONDS, path='/')
    return Principal(**user)
@router.get('/me', response_model=Principal)
async def me(user: Principal = Depends(principal)):
    return user
@router.post('/logout', status_code=204)
async def logout(request: Request, response: Response, user: Principal = Depends(principal)):
    await db.sessions.update_one({'id': request.state.session_id}, {'$set': {'revoked': True}})
    response.delete_cookie('samanvay_session', path='/api', secure=True, httponly=True, samesite='none')
    response.delete_cookie('samanvay_csrf', path='/', secure=True, samesite='none')