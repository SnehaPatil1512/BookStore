"""SQLAlchemy book model."""

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Book(Base):
    """Book entity stored per owner with local and global IDs."""

    __tablename__ = "books"
    __table_args__ = (
        UniqueConstraint("owner_id", "book_id", name="uq_books_owner_book_id"),
    )

    db_id = Column("id", Integer, primary_key=True, index=True)
    book_id = Column(Integer, nullable=False)
    title = Column(String)
    author = Column(String)
    publisher = Column(String)
    file_path = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="books")

    @property
    def id(self) -> int:
        return self.book_id

    @property
    def pdf_url(self) -> str | None:
        if not self.file_path:
            return None
        return f"/api/books/read/{self.db_id}"
