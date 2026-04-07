"""FastAPI application entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal, init_database
from app.core.config import SETTINGS
from app.core.error_handlers import register_error_handlers
from app.routers.api import auth_api, book_api, admin_api
from app.routers.web.web_routes import (
    clear_auth_cookie,
    get_current_user_from_cookie,
    is_protected_web_path,
    router as web_router,
)

logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    logger.info("Application startup complete.")
    yield


app = FastAPI(
    title=SETTINGS.app_name,
    docs_url="/api/docs" if SETTINGS.docs_enabled else None,
    redoc_url="/api/redoc" if SETTINGS.docs_enabled else None,
    openapi_url="/api/openapi.json" if SETTINGS.docs_enabled else None,
    lifespan=lifespan,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/uploads", StaticFiles(directory="app/uploads"), name="uploads")

if SETTINGS.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=SETTINGS.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth_api.router, prefix="/api/auth", tags=["api-auth"])
app.include_router(book_api.router, prefix="/api/books", tags=["api-books"])
app.include_router(admin_api.router, prefix="/api/admin", tags=["api-admin"])
app.include_router(web_router, prefix="", include_in_schema=False)
register_error_handlers(app)


@app.middleware("http")
async def protect_authorized_book_routes(request: Request, call_next):
    """Block protected web pages when no valid auth cookie is present."""
    if not is_protected_web_path(request.url.path):
        return await call_next(request)

    db = SessionLocal()
    try:
        current_user = get_current_user_from_cookie(
            request.cookies.get(SETTINGS.auth_cookie_name),
            db,
        )
    finally:
        db.close()

    if current_user is None:
        response = RedirectResponse("/?error=Please+log+in+to+continue.", status_code=303)
        clear_auth_cookie(response)
        return response

    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach baseline security headers to all responses."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response


@app.get("/docs", include_in_schema=False)
def redirect_docs():
    """Redirect pretty docs URL to API docs endpoint."""
    if not SETTINGS.docs_enabled:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return RedirectResponse("/api/docs", status_code=302)


@app.get("/redoc", include_in_schema=False)
def redirect_redoc():
    """Redirect pretty redoc URL to API redoc endpoint."""
    if not SETTINGS.docs_enabled:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return RedirectResponse("/api/redoc", status_code=302)


@app.get("/api/health/live", tags=["health"])
def liveness_probe():
    """Simple liveness probe."""
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["health"])
def readiness_probe():
    """Readiness probe that validates database connectivity."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except SQLAlchemyError:
        logger.exception("Readiness check failed")
        return JSONResponse({"status": "not_ready"}, status_code=503)
    finally:
        db.close()
