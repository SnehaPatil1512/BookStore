"""User and role persistence helpers."""

from sqlalchemy.orm import Session, selectinload

from app.core import security
from app.core.storage import delete_upload_file
from app.models.role import Role
from app.models.user_model import User


def _user_query(db: Session):
    """Return base eager-loading query for users."""
    return db.query(User).options(
        selectinload(User.roles).selectinload(Role.permissions),
        selectinload(User.books),
    )


def create_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    role_name: str = "editor",
) -> User:
    """Create a user and optionally assign a role by name."""
    user = User(
        username=username,
        email=email,
        hashed_password=security.hash_password(password),
    )

    selected_role = db.query(Role).filter(Role.name == role_name).first()
    if selected_role is not None:
        user.roles = [selected_role]

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def get_user_by_username(db: Session, username: str) -> User | None:
    """Fetch user by username."""
    return _user_query(db).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    """Fetch user by email."""
    return _user_query(db).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Fetch user by id."""
    return _user_query(db).filter(User.id == user_id).first()


def get_all_users(db: Session) -> list[User]:
    """List all users."""
    return _user_query(db).order_by(User.id).all()


def get_all_roles(db: Session) -> list[Role]:
    """List all roles sorted by name."""
    return db.query(Role).order_by(Role.name).all()


def update_user(
    db: Session,
    *,
    user: User,
    username: str,
    email: str,
    role_name: str,
    password: str | None = None,
) -> User:
    """Update user profile, role, and optional password."""
    user.username = username
    user.email = email

    if password:
        user.hashed_password = security.hash_password(password)

    selected_role = db.query(Role).filter(Role.name == role_name).first()
    if selected_role is not None:
        user.roles = [selected_role]

    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    """Delete user with associated books and role links."""
    user.roles.clear()
    for book in list(user.books):
        delete_upload_file(book.file_path)
        db.delete(book)

    db.delete(user)
    db.commit()
