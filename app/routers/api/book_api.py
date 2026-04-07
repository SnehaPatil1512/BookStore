"""Book API routes."""

from datetime import datetime, timedelta, timezone
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.crud import book_crud, user_crud
from app.crud.book_crud import DuplicateBookError, get_book_by_db_id
from app.core.dependencies import require_permission, require_permission_any
from app.core.storage import (
    FileStorageError,
    InvalidPdfUpload,
    delete_upload_file,
    resolve_upload_path,
    save_pdf_upload,
)
from app.core.config import ALGORITHM, SECRET_KEY
from app.schemas.common_schema import MessageResponse
from app.schemas.book_schema import BookCreate, BookResponse, ReadTokenResponse, SummaryResponse

from app.core.ai_service import summarize_book

router = APIRouter()


def can_access_book(current_user: Any, book: Any) -> bool:
    """Check whether the user can access the target book."""
    if current_user.is_admin:
        return True
    if "viewer" in current_user.role_names:
        return True
    return book.owner_id == current_user.id


def build_safe_pdf_filename(book: Any) -> str:
    """Return a filesystem-safe inline PDF filename."""
    base = book.file_name or f"{book.title or 'book'}.pdf"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or "book.pdf"
    if not safe.lower().endswith(".pdf"):
        safe = f"{safe}.pdf"
    return safe


def serve_book_pdf(*, book_db_id: int, db: Session, current_user: Any):
    """Resolve and stream a book PDF if the user has access."""
    book = book_crud.get_book_by_db_id(db, book_db_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not can_access_book(current_user, book):
        raise HTTPException(status_code=403, detail="Permission denied")

    if not book.file_path:
        raise HTTPException(status_code=404, detail="PDF not available")

    try:
        file_path = resolve_upload_path(book.file_path)
    except FileStorageError:
        raise HTTPException(status_code=404, detail="PDF not available")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF not available")

    headers = {"Content-Disposition": f'inline; filename="{build_safe_pdf_filename(book)}"'}
    return FileResponse(
        path=str(file_path),
        media_type=book.mime_type or "application/pdf",
        headers=headers,
    )


@router.post("/", response_model=BookResponse)
def create_book(
    book: BookCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("create_book")),
):
    """Create a metadata-only book entry for current user."""
    try:
        return book_crud.create_book(db, book, current_user.id)
    except DuplicateBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def serialize_book(book: Any, current_user: Any) -> dict[str, Any]:
    """Serialize a book model for API response based on role visibility."""
    data = BookResponse.model_validate(book).model_dump()
    data["has_pdf"] = bool(getattr(book, "file_path", None))
    if "viewer" in current_user.role_names:
        data.pop("pdf_url", None)
    return data


@router.get("/", response_model=list[BookResponse])
def get_books(
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("view_book")),
):
    """List books for current user with optional pagination."""
    if current_user.is_admin:
        books = book_crud.get_all_books(db, offset=offset, limit=limit)
    elif "viewer" in current_user.role_names:
        books = book_crud.get_all_books(db, offset=offset, limit=limit)
    else:
        books = book_crud.get_books(db, current_user.id, offset=offset, limit=limit)

    return [serialize_book(book, current_user) for book in books]


@router.put("/{book_id}", response_model=BookResponse)
def update_book(
    book_id: int,
    book: BookCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("update_book")),
):
    """Update an owned book by user-visible id."""
    try:
        updated = book_crud.update_book(db, book_id, book, current_user.id)
    except DuplicateBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not updated:
        raise HTTPException(status_code=404, detail="Book not found")
    return updated


@router.delete("/{book_id}", response_model=MessageResponse)
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("delete_book")),
):
    """Delete an owned book by user-visible id."""
    deleted = book_crud.delete_book(db, book_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"message": "Deleted successfully"}


@router.post("/upload", response_model=BookResponse)
def upload_book(
    title: str = Form(...),
    author: str = Form(...),
    publisher: str = Form(...),
    file: UploadFile = File(...),
    owner_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("create_book")),
):
    """Upload a PDF-backed book entry."""
    title = title.strip()
    author = author.strip()
    publisher = publisher.strip()
    if not title or not author or not publisher:
        raise HTTPException(status_code=400, detail="Title, author, and publisher are required.")

    if current_user.is_admin:
        if owner_id is None:
            owner_id = current_user.id
        else:
            owner = user_crud.get_user_by_id(db, owner_id)
            if owner is None:
                raise HTTPException(status_code=404, detail="Owner not found.")
    else:
        owner_id = current_user.id

    try:
        file_data = save_pdf_upload(file)
    except InvalidPdfUpload as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        return book_crud.create_book(
            db,
            BookCreate(title=title, author=author, publisher=publisher),
            owner_id,
            file_path=file_data["file_path"],
            file_name=file_data["file_name"],
            mime_type=file_data["mime_type"],
            file_size=file_data["file_size"],
        )
    except DuplicateBookError as exc:
        delete_upload_file(file_data.get("file_path"))
        raise HTTPException(status_code=400, detail=str(exc))
    except SQLAlchemyError:
        db.rollback()
        delete_upload_file(file_data.get("file_path"))
        raise HTTPException(status_code=500, detail="Could not save the book right now.")


READ_TOKEN_EXPIRE_SECONDS = 60


def create_read_token(*, book_db_id: int, user_id: int) -> str:
    """Create a short-lived token for PDF read access."""
    expires = datetime.now(timezone.utc) + timedelta(seconds=READ_TOKEN_EXPIRE_SECONDS)
    payload = {
        "sub": str(user_id),
        "book_db_id": book_db_id,
        "scope": "read_pdf",
        "exp": expires,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_read_token(token: str) -> dict:
    """Decode and validate a short-lived PDF read token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("scope") != "read_pdf":
        raise HTTPException(status_code=401, detail="Invalid token scope")

    return payload


@router.get("/read-token/{book_db_id}", response_model=ReadTokenResponse)
def get_read_token(
    book_db_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission_any("view_book")),
) -> ReadTokenResponse:
    """Issue a short-lived token used to read a protected PDF."""
    book = book_crud.get_book_by_db_id(db, book_db_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not can_access_book(current_user, book):
        raise HTTPException(status_code=403, detail="Permission denied")

    if not book.file_path:
        raise HTTPException(status_code=404, detail="PDF not available")

    return ReadTokenResponse(token=create_read_token(book_db_id=book_db_id, user_id=current_user.id))


@router.post("/read")
def read_book_token(
    token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Read a PDF by submitting a short-lived read token."""
    payload = decode_read_token(token)
    token_user_id = payload.get("sub")
    if not token_user_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    user = user_crud.get_user_by_id(db, int(token_user_id))
    if not user:
        raise HTTPException(status_code=403, detail="Permission denied")

    book_db_id = payload.get("book_db_id")
    if book_db_id is None:
        raise HTTPException(status_code=400, detail="Invalid token")

    return serve_book_pdf(book_db_id=int(book_db_id), db=db, current_user=user)


@router.get("/read/{book_db_id}")
def read_book(
    book_db_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission_any("view_book")),
):
    """Read a PDF by authenticated direct route."""
    return serve_book_pdf(book_db_id=book_db_id, db=db, current_user=current_user)


@router.get("/{book_db_id}/summarize", response_model=SummaryResponse)
def summarize(
    book_db_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission_any("view_book")),
) -> SummaryResponse:
    """Generate an AI summary for a readable book payload."""
    book = get_book_by_db_id(db, book_db_id)

    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not can_access_book(current_user, book):
        raise HTTPException(status_code=403, detail="Permission denied")

    source_text = getattr(book, "description", None) or getattr(book, "content", None)
    if not source_text:
        source_text = "\n".join(
            filter(
                None,
                [
                    book.title and f"Title: {book.title}",
                    book.author and f"Author: {book.author}",
                    book.publisher and f"Publisher: {book.publisher}",
                    "Generate a concise bookstore-style summary based on the available metadata.",
                ],
            )
        )

    if not source_text.strip():
        raise HTTPException(status_code=400, detail="No summary source available for this book")

    summary = summarize_book(source_text)
    return SummaryResponse(summary=summary)
