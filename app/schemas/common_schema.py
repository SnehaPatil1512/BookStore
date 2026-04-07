"""Common reusable API response schemas."""

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Simple API message response wrapper."""

    message: str
