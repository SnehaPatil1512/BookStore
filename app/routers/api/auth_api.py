"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth_service import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    UsernameAlreadyExistsError,
    authenticate_user,
    create_token_for_user,
    get_user_from_token,
    register_user,
)
from app.database import get_db
from app.schemas.user_schema import AuthTokenResponse, UserCreate, UserPublic, UserRead

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@router.post("/register", response_model=UserPublic)
def register_user_route(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user account."""
    try:
        new_user = register_user(
            db,
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
        )
        return new_user
    except (UsernameAlreadyExistsError, EmailAlreadyExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/login", response_model=AuthTokenResponse)
def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate a user and return an access token."""
    try:
        db_user = authenticate_user(
            db,
            username=form_data.username,
            password=form_data.password,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_token_for_user(db_user)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
def read_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Return currently authenticated user profile."""
    try:
        return get_user_from_token(db, token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
