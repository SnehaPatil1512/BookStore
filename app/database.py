"""Database engine/session setup and startup data migrations."""

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import SETTINGS

DATABASE_URL = SETTINGS.database_url

if SETTINGS.environment == "production" and DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "Invalid production database configuration: SQLite is not allowed in production."
    )

engine_kwargs: dict = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_database() -> None:
    """Initialize schema and run lightweight compatibility migrations."""
    from app import models

    Base.metadata.create_all(bind=engine)
    ensure_book_ids()
    ensure_book_file_columns()
    ensure_rbac_setup()


def ensure_book_ids() -> None:
    """Backfill per-owner `book_id` and enforce unique owner/book index."""
    inspector = inspect(engine)
    if "books" not in inspector.get_table_names():
        return

    book_columns = {column["name"] for column in inspector.get_columns("books")}

    with engine.begin() as connection:
        if "book_id" not in book_columns:
            connection.execute(text("ALTER TABLE books ADD COLUMN book_id INTEGER"))
            needs_backfill = True
        else:
            needs_backfill = (
                connection.execute(
                    text("SELECT COUNT(*) FROM books WHERE book_id IS NULL")
                ).scalar_one()
                > 0
            )

        if needs_backfill:
            rows = connection.execute(
                text("SELECT id, owner_id FROM books ORDER BY owner_id, id")
            ).mappings()

            current_owner_id = object()
            next_book_id = 1

            for row in rows:
                if row["owner_id"] != current_owner_id:
                    current_owner_id = row["owner_id"]
                    next_book_id = 1

                connection.execute(
                    text("UPDATE books SET book_id = :book_id WHERE id = :id"),
                    {"book_id": next_book_id, "id": row["id"]},
                )
                next_book_id += 1

        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_books_owner_book_id ON books (owner_id, book_id)"
            )
        )


def ensure_book_file_columns() -> None:
    """Ensure file metadata columns are available on books table."""
    inspector = inspect(engine)
    if "books" not in inspector.get_table_names():
        return

    book_columns = {column["name"] for column in inspector.get_columns("books")}
    additions = []
    if "file_path" not in book_columns:
        additions.append(("file_path", "TEXT"))
    if "file_name" not in book_columns:
        additions.append(("file_name", "TEXT"))
    if "mime_type" not in book_columns:
        additions.append(("mime_type", "TEXT"))
    if "file_size" not in book_columns:
        additions.append(("file_size", "INTEGER"))

    if not additions:
        return

    with engine.begin() as connection:
        for column_name, column_type in additions:
            connection.execute(
                text(f"ALTER TABLE books ADD COLUMN {column_name} {column_type}")
            )


def ensure_rbac_setup() -> None:
    """Seed roles/permissions and backfill role assignments for existing users."""
    from app.models.role import Role
    from app.models.user_model import User
    from app.scripts.seed_rbac import seed_rbac

    session = SessionLocal()
    try:
        seed_rbac(session)

        role_lookup = {
            role.name: role
            for role in session.query(Role).all()
        }

        user_columns = {
            column["name"]
            for column in inspect(engine).get_columns("users")
        }
        has_legacy_role_column = "role" in user_columns

        legacy_roles = {}
        if has_legacy_role_column:
            rows = session.execute(
                text("SELECT id, role FROM users")
            ).mappings().all()
            legacy_roles = {
                row["id"]: (row["role"] or "").strip().lower()
                for row in rows
            }

        role_map = {
            "admin": "admin",
            "viewer": "viewer",
            "editor": "editor",
            "user": "editor",
        }

        for user in session.query(User).all():
            if user.roles:
                continue

            selected_role = role_lookup.get(
                role_map.get(legacy_roles.get(user.id, "editor"), "editor")
            )
            if selected_role is not None:
                user.roles = [selected_role]

        session.commit()
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """Provide request-scoped database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
