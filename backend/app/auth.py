"""Registration, password verification, and short-lived bearer access tokens."""
from datetime import datetime, timedelta, timezone
import os
import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

router = APIRouter(prefix='/api/auth', tags=['Authentication'])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login')
password_hasher = PasswordHash.recommended()
dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', '')
if len(SECRET_KEY) < 32:
    raise RuntimeError('JWT_SECRET_KEY must contain at least 32 characters')
TOKEN_MINUTES = 30


class Registration(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r'^[a-z0-9_]+$')
    password: SecretStr


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int = TOKEN_MINUTES * 60


def unauthorized():
    return HTTPException(401, 'Invalid credentials or token', headers={'WWW-Authenticate': 'Bearer'})


def create_access_token(user_id):
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': str(user_id), 'iat': now,
                       'exp': now + timedelta(minutes=TOKEN_MINUTES),
                       'iss': 'skywatch', 'aud': 'skywatch-api'}, SECRET_KEY, algorithm='HS256')


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=['HS256'],
                            audience='skywatch-api', issuer='skywatch',
                            options={'require': ['sub', 'exp', 'iat', 'iss', 'aud']})
        user_id = int(claims['sub'])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


def require_roles(*allowed_roles):
    """Check the user's database role on every request."""
    def check_role(user: User = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(403, 'You do not have permission for this action')
        return user
    return check_role


@router.post('/register', response_model=UserResponse, status_code=201)
def register(payload: Registration, db: Session = Depends(get_db)):
    password = payload.password.get_secret_value()
    if not 12 <= len(password) <= 128:
        raise HTTPException(422, 'Password must contain 12 to 128 characters')
    user = User(username=payload.username, password_hash=password_hasher.hash(password), role='viewer')
    try:
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Username already registered')
    db.refresh(user)
    return user


@router.post('/login', response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    if len(form.password) > 128:
        raise unauthorized()
    user = db.query(User).filter(User.username == form.username).first()
    valid = password_hasher.verify(form.password, user.password_hash if user else dummy_hash)
    if not valid or user is None or not user.is_active:
        raise unauthorized()
    return TokenResponse(access_token=create_access_token(user.id))


@router.get('/me', response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
