"""Authentication service helpers and domain-level auth errors."""

from __future__ import annotations

from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import ALGORITHM, SECRET_KEY
from app.crud import user_crud
from app.models.user_model import User


oauth2_scheme = HTTPBearer()


class AuthError(Exception):
    """Base class for auth-related domain errors."""


class InvalidCredentialsError(AuthError):
    """Raised when provided credentials are invalid."""


class InvalidTokenError(AuthError):
    """Raised when an auth token is invalid."""


class UsernameAlreadyExistsError(AuthError):
    """Raised when registering/updating to a duplicate username."""


class EmailAlreadyExistsError(AuthError):
    """Raised when registering/updating to a duplicate email."""


class UserNotFoundError(AuthError):
    """Raised when a user does not exist."""


def normalize_access_token(access_token: str | None) -> str | None:
    """Normalize cookie/header token values into a bare JWT string."""
    if access_token is None:
        return None

    normalized = access_token.strip()
    if normalized.lower().startswith("bearer "):
        normalized = normalized[7:].strip()

    return normalized or None


def register_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    role_name: str = "editor",
) -> User:
    """Register a new user and validate uniqueness constraints."""
    username = username.strip()
    email = email.strip().lower()

    if user_crud.get_user_by_username(db, username):
        raise UsernameAlreadyExistsError("That username is already taken.")

    if user_crud.get_user_by_email(db, email):
        raise EmailAlreadyExistsError("That email is already registered.")

    return user_crud.create_user(
        db,
        username=username,
        email=email,
        password=password,
        role_name=role_name,
    )


def update_user_account(
    db: Session,
    *,
    user_id: int,
    username: str,
    email: str,
    role_name: str,
    password: str | None = None,
) -> User:
    """Update user profile and optional password with uniqueness checks."""
    user = user_crud.get_user_by_id(db, user_id)
    if user is None:
        raise UserNotFoundError("User not found.")

    username = username.strip()
    email = email.strip().lower()
    password = password.strip() if password else None

    existing_user = user_crud.get_user_by_username(db, username)
    if existing_user and existing_user.id != user_id:
        raise UsernameAlreadyExistsError("That username is already taken.")

    existing_email = user_crud.get_user_by_email(db, email)
    if existing_email and existing_email.id != user_id:
        raise EmailAlreadyExistsError("That email is already registered.")

    return user_crud.update_user(
        db,
        user=user,
        username=username,
        email=email,
        role_name=role_name,
        password=password,
    )


def authenticate_user(db: Session, *, username: str, password: str) -> User:
    """Authenticate by username/email and password."""
    identifier = username.strip()
    db_user = user_crud.get_user_by_username(db, identifier)
    if db_user is None:
        db_user = user_crud.get_user_by_email(db, identifier.lower())

    if not db_user or not security.verify_password(password, db_user.hashed_password):
        raise InvalidCredentialsError("Invalid username or password.")

    return db_user


def create_token_for_user(user: User) -> str:
    """Create JWT token payload for an authenticated user."""
    return security.create_access_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "roles": user.role_names,
            "permissions": user.permission_names,
        }
    )


def get_user_from_token(db: Session, token: str) -> User:
    """Decode token and resolve current user from database."""
    normalized_token = normalize_access_token(token)
    if not normalized_token:
        raise InvalidTokenError("Invalid token.")

    try:
        payload = jwt.decode(normalized_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError("Invalid token.") from exc

    user_id = payload.get("user_id")
    if user_id is None:
        raise InvalidTokenError("Invalid token.")

    user = user_crud.get_user_by_id(db, user_id)

    if user is None:
        raise InvalidTokenError("User not found.")

    return user
