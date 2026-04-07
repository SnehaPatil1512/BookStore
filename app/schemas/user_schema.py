"""Pydantic schemas for user/auth payloads."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    """Shared user identity fields."""

    username: str
    email: str


class UserCreate(UserBase):
    """Payload used to register a new user."""

    password: str


class UserPublic(UserBase):
    """Public user representation used by auth endpoints."""

    id: int

    model_config = ConfigDict(from_attributes=True)


class UserRead(UserBase):
    """Authenticated user profile including roles and permissions."""

    id: int
    role_names: list[str] = Field(default_factory=list)
    permission_names: list[str] = Field(default_factory=list)
    is_admin: bool = False

    model_config = ConfigDict(from_attributes=True)


class AuthTokenResponse(BaseModel):
    """OAuth-compatible access token payload."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
