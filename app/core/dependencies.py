"""FastAPI dependency helpers for auth and permission checks."""

from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import SETTINGS
from app.database import get_db
from app.models import User
from app.core.auth_service import (
    InvalidTokenError,
    get_user_from_token,
    normalize_access_token,
    oauth2_scheme,
)

optional_oauth2_scheme = HTTPBearer(auto_error=False)


def get_current_api_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve authenticated user from Authorization header for API endpoints."""
    try:
        return get_user_from_token(db, credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def get_current_user_from_request(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_oauth2_scheme),
    access_token: str | None = Cookie(default=None, alias=SETTINGS.auth_cookie_name),
    db: Session = Depends(get_db),
) -> User:
    """Resolve user from bearer header first, then auth cookie."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        token = normalize_access_token(access_token)

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        return get_user_from_token(db, token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def require_permission(permission_name: str):
    """Require a single permission name."""

    def permission_checker(
        user: User = Depends(get_current_user_from_request),
    ) -> User:
        if not user.has_permission(permission_name):
            raise HTTPException(status_code=403, detail="Permission denied")

        return user

    return permission_checker


def require_permission_any(*permission_names: str):
    """Require that user has at least one permission from the provided list."""
    if not permission_names:
        raise ValueError("At least one permission name is required.")

    def permission_checker(
        user: User = Depends(get_current_user_from_request),
    ) -> User:
        if not any(user.has_permission(permission_name) for permission_name in permission_names):
            raise HTTPException(status_code=403, detail="Permission denied")

        return user

    return permission_checker

