"""Centralized exception handlers for API and web routes."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.ai_service import SummaryProviderError
from app.core.auth_service import (
    AuthError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
    UsernameAlreadyExistsError,
)
from app.core.storage import InvalidPdfUpload
from app.crud.book_crud import DuplicateBookError


logger = logging.getLogger(__name__)


def _is_api_request(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _web_error_redirect(message: str, status_code: int = 303) -> RedirectResponse:
    safe_message = quote_plus(message)
    return RedirectResponse(f"/?error={safe_message}", status_code=status_code)


def _http_status_for_auth_error(exc: AuthError) -> int:
    if isinstance(exc, (InvalidCredentialsError, InvalidTokenError)):
        return 401
    if isinstance(exc, UserNotFoundError):
        return 404
    if isinstance(exc, (UsernameAlreadyExistsError, EmailAlreadyExistsError)):
        return 400
    return 400


def register_error_handlers(app: FastAPI) -> None:
    """Attach exception handlers used across the application."""

    @app.exception_handler(AuthError)
    async def handle_auth_error(request: Request, exc: AuthError):
        status_code = _http_status_for_auth_error(exc)
        if _is_api_request(request):
            return JSONResponse({"detail": str(exc)}, status_code=status_code)
        return _web_error_redirect(str(exc))

    @app.exception_handler(DuplicateBookError)
    async def handle_duplicate_book(request: Request, exc: DuplicateBookError):
        if _is_api_request(request):
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return _web_error_redirect(str(exc))

    @app.exception_handler(InvalidPdfUpload)
    async def handle_invalid_pdf_upload(request: Request, exc: InvalidPdfUpload):
        if _is_api_request(request):
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return _web_error_redirect(str(exc))

    @app.exception_handler(SummaryProviderError)
    async def handle_summary_provider_error(request: Request, exc: SummaryProviderError):
        if _is_api_request(request):
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return _web_error_redirect(str(exc))

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_error(request: Request, exc: SQLAlchemyError):
        logger.exception("Database error: %s", exc)
        if _is_api_request(request):
            return JSONResponse({"detail": "A database error occurred."}, status_code=500)
        return _web_error_redirect("A database error occurred. Please try again.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception("Unhandled server error: %s", exc)
        if _is_api_request(request):
            return JSONResponse({"detail": "Internal server error."}, status_code=500)
        return _web_error_redirect("Unexpected error. Please try again.")
