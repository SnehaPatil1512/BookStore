"""Pydantic schemas for book payloads."""

from pydantic import BaseModel, ConfigDict, field_validator


class BookBase(BaseModel):
    """Shared book metadata fields."""

    title: str
    author: str
    publisher: str

    @field_validator("title", "author", "publisher")
    @classmethod
    def strip_text_fields(cls, value: str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class BookCreate(BookBase):
    """Payload used to create or update books."""

    pass


class BookResponse(BookBase):
    """Book payload returned by APIs."""

    id: int
    db_id: int
    pdf_url: str | None = None
    has_pdf: bool = False

    model_config = ConfigDict(from_attributes=True)


class ReadTokenResponse(BaseModel):
    """Payload with short-lived read token."""

    token: str


class SummaryResponse(BaseModel):
    """Payload with generated summary text."""

    summary: str
