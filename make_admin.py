"""Utility script to grant admin role to an existing user."""

from __future__ import annotations

import argparse
import logging

from app.core.auth_service import UserNotFoundError, update_user_account
from app.crud import user_crud
from app.database import SessionLocal, init_database

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Promote an existing user to admin.")
    parser.add_argument(
        "--email",
        default="admin@gmail.com",
        help="Email of the user to promote (default: admin@gmail.com).",
    )
    return parser.parse_args()


def promote_user_to_admin(email: str) -> None:
    """Promote existing user to admin role."""
    init_database()
    db = SessionLocal()
    try:
        user = user_crud.get_user_by_email(db, email.strip().lower())
        if user is None:
            raise UserNotFoundError(f"User with email '{email}' was not found.")

        update_user_account(
            db,
            user_id=user.id,
            username=user.username,
            email=user.email,
            role_name="admin",
        )
        logger.info("User '%s' is now admin.", user.username)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
    args = parse_args()
    promote_user_to_admin(args.email)

