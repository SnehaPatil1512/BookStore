"""Book persistence helpers."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.storage import delete_upload_file
from app.models.book_model import Book
from app.schemas.book_schema import BookCreate


class DuplicateBookError(Exception):
    """Raised when a duplicate book exists for the same owner."""


def _find_duplicate_book(
    db: Session,
    *,
    user_id: int,
    title: str,
    author: str,
    publisher: str,
    exclude_book_id: int | None = None,
) -> Book | None:
    """Find duplicate book by normalized title/author/publisher for an owner."""
    query = db.query(Book).filter(
        Book.owner_id == user_id,
        func.lower(func.trim(Book.title)) == title.lower(),
        func.lower(func.trim(Book.author)) == author.lower(),
        func.lower(func.trim(Book.publisher)) == publisher.lower(),
    )

    if exclude_book_id is not None:
        query = query.filter(Book.book_id != exclude_book_id)

    return query.first()


def create_book(
    db: Session,
    book: BookCreate,
    user_id: int,
    *,
    file_path: str | None = None,
    file_name: str | None = None,
    mime_type: str | None = None,
    file_size: int | None = None,
) -> Book:
    """Create a new book row for owner and assign sequential per-owner id."""
    if _find_duplicate_book(
        db,
        user_id=user_id,
        title=book.title,
        author=book.author,
        publisher=book.publisher,
    ):
        raise DuplicateBookError("This book is already present in your library.")

    next_book_id = (
        db.query(func.max(Book.book_id))
        .filter(Book.owner_id == user_id)
        .scalar()
        or 0
    ) + 1

    db_book = Book(
        **book.model_dump(),
        owner_id=user_id,
        book_id=next_book_id,
        file_path=file_path,
        file_name=file_name,
        mime_type=mime_type,
        file_size=file_size,
    )
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book


def get_books(
    db: Session,
    user_id: int,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[Book]:
    """List books for a specific owner."""
    query = (
        db.query(Book)
        .filter(Book.owner_id == user_id)
        .order_by(Book.book_id)
    )

    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    return query.all()


def update_book(db: Session, book_id: int, book: BookCreate, user_id: int) -> Book | None:
    """Update a book identified by user-visible id and owner id."""
    db_book = db.query(Book).filter(
        Book.book_id == book_id,
        Book.owner_id == user_id
    ).first()

    if not db_book:
        return None

    if _find_duplicate_book(
        db,
        user_id=user_id,
        title=book.title,
        author=book.author,
        publisher=book.publisher,
        exclude_book_id=book_id,
    ):
        raise DuplicateBookError("This book is already present in your library.")

    for key, value in book.model_dump().items():
        setattr(db_book, key, value)

    db.commit()
    db.refresh(db_book)
    return db_book


def delete_book(db: Session, book_id: int, user_id: int) -> Book | None:
    """Delete a book by user-visible id and owner id."""
    db_book = db.query(Book).filter(
        Book.book_id == book_id,
        Book.owner_id == user_id
    ).first()

    if not db_book:
        return None

    delete_upload_file(db_book.file_path)
    db.delete(db_book)
    db.commit()
    return db_book


def get_all_books(
    db: Session,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[Book]:
    """List all books across owners."""
    query = db.query(Book).order_by(Book.owner_id, Book.book_id)

    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    return query.all()


def get_book_by_db_id(db: Session, db_id: int) -> Book | None:
    """Fetch a book by global database id."""
    return db.query(Book).filter(Book.db_id == db_id).first()


def update_book_by_db_id(db: Session, db_id: int, book: BookCreate) -> Book | None:
    """Update a book by global database id."""
    db_book = get_book_by_db_id(db, db_id)
    if not db_book:
        return None

    if _find_duplicate_book(
        db,
        user_id=db_book.owner_id,
        title=book.title,
        author=book.author,
        publisher=book.publisher,
        exclude_book_id=db_book.book_id,
    ):
        raise DuplicateBookError("This book is already present in your library.")

    for key, value in book.model_dump().items():
        setattr(db_book, key, value)

    db.commit()
    db.refresh(db_book)
    return db_book


def delete_book_by_db_id(db: Session, db_id: int) -> Book | None:
    """Delete a book by global database id."""
    db_book = get_book_by_db_id(db, db_id)
    if not db_book:
        return None

    delete_upload_file(db_book.file_path)
    db.delete(db_book)
    db.commit()
    return db_book


def update_book_file(
    db: Session,
    db_book: Book,
    *,
    file_path: str,
    file_name: str | None = None,
    mime_type: str | None = None,
    file_size: int | None = None,
):
    """Update file metadata for a book row."""
    db_book.file_path = file_path
    db_book.file_name = file_name
    db_book.mime_type = mime_type
    db_book.file_size = file_size
    db.commit()
    db.refresh(db_book)
    return db_book
