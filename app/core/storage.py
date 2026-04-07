"""Helpers for validated PDF file persistence."""

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile


class FileStorageError(Exception):
    """Base file storage error."""


class InvalidPdfUpload(FileStorageError):
    """Raised when upload is not a valid PDF payload."""


UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


def ensure_upload_dir() -> None:
    """Ensure upload directory exists."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def is_pdf_upload(upload: UploadFile) -> bool:
    """Validate uploaded file as PDF by mime type or extension."""
    content_type = (upload.content_type or "").lower()
    if content_type == "application/pdf":
        return True
    filename = (upload.filename or "").lower()
    return filename.endswith(".pdf")


def save_pdf_upload(upload: UploadFile) -> dict[str, str | int]:
    """Persist PDF upload to local storage and return metadata."""
    if upload is None or not upload.filename:
        raise InvalidPdfUpload("PDF file is required.")

    if not is_pdf_upload(upload):
        raise InvalidPdfUpload("Only PDF files are allowed.")

    ensure_upload_dir()

    file_id = uuid.uuid4().hex
    stored_name = f"{file_id}.pdf"
    destination = UPLOAD_DIR / stored_name

    upload.file.seek(0)
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    file_size = destination.stat().st_size
    if file_size == 0:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise InvalidPdfUpload("Uploaded PDF was empty.")

    return {
        "file_path": stored_name,
        "file_name": upload.filename,
        "mime_type": upload.content_type or "application/pdf",
        "file_size": file_size,
    }


def resolve_upload_path(file_path: str) -> Path:
    """Resolve upload file path and prevent path traversal."""
    if not file_path:
        raise FileStorageError("Missing file path.")

    upload_root = UPLOAD_DIR.resolve()
    candidate = (UPLOAD_DIR / file_path).resolve()
    if upload_root not in candidate.parents and candidate != upload_root:
        raise FileStorageError("Invalid file path.")

    return candidate


def delete_upload_file(file_path: str | None) -> None:
    """Delete upload file if it exists and path is valid."""
    if not file_path:
        return

    try:
        candidate = resolve_upload_path(file_path)
    except FileStorageError:
        return

    try:
        candidate.unlink()
    except FileNotFoundError:
        pass
