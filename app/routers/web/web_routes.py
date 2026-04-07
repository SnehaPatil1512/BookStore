"""Server-rendered web routes for authentication and dashboard flows."""

import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Cookie, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth_service import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
    UsernameAlreadyExistsError,
    authenticate_user,
    create_token_for_user,
    get_user_from_token,
    normalize_access_token,
    register_user,
    update_user_account,
)
from app.crud import book_crud, permission_crud, user_crud
from app.crud.book_crud import DuplicateBookError
from app.core.storage import InvalidPdfUpload, delete_upload_file, save_pdf_upload
from app.core.config import SETTINGS
from app.database import get_db
from app.models.user_model import User
from app.schemas.book_schema import BookCreate

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "templates")
TEMPLATES = Jinja2Templates(directory=TEMPLATE_DIR)

AUTH_COOKIE_NAME = SETTINGS.auth_cookie_name
AUTH_COOKIE_MAX_AGE = SETTINGS.auth_cookie_max_age
PERMISSION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
PROTECTED_WEB_PATHS = (
    "/dashboard",
    "/admin",
    "/admin/users",
    "/admin/books",
    "/add-book",
    "/update-book/",
    "/delete-book/",
)


def render_template(request: Request, template_name: str, **context) -> HTMLResponse:
    """Render Jinja template with standard request context."""
    return TEMPLATES.TemplateResponse(
        request=request,
        name=template_name,
        context={"request": request, **context},
    )


def build_redirect_url(
    path: str,
    *,
    success: str | None = None,
    error: str | None = None,
    fragment: str | None = None,
    query_updates: dict[str, str | int | None] | None = None,
) -> str:
    """Build redirect URL while preserving/merging query parameters and hash."""
    split_path = urlsplit(path)
    params = dict(parse_qsl(split_path.query, keep_blank_values=True))
    if query_updates:
        for key, value in query_updates.items():
            if value is None:
                params.pop(key, None)
            else:
                params[key] = str(value)
    if success:
        params["success"] = success
    if error:
        params["error"] = error
    return urlunsplit(
        (
            split_path.scheme,
            split_path.netloc,
            split_path.path,
            urlencode(params),
            fragment if fragment is not None else split_path.fragment,
        )
    )


def set_auth_cookie(response: RedirectResponse, token: str) -> None:
    """Set auth cookie containing bearer token."""
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=f"Bearer {token}",
        httponly=True,
        secure=SETTINGS.secure_cookies,
        samesite="lax",
        max_age=AUTH_COOKIE_MAX_AGE,
        path="/",
    )


def clear_auth_cookie(response: RedirectResponse) -> None:
    """Clear auth cookie from response."""
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=SETTINGS.secure_cookies,
        samesite="lax",
    )


def get_current_user_from_cookie(access_token: str | None, db: Session) -> User | None:
    """Resolve current user from cookie token value."""
    normalized = normalize_access_token(access_token)
    if not normalized:
        return None

    try:
        return get_user_from_token(db, normalized)
    except InvalidTokenError:
        return None
    except SQLAlchemyError:
        db.rollback()
        return None


def is_protected_web_path(path: str) -> bool:
    """Check whether a web path requires authentication."""
    return any(
        path == protected_path or path.startswith(protected_path)
        for protected_path in PROTECTED_WEB_PATHS
    )


def get_admin_redirect(current_user: User | None) -> RedirectResponse | None:
    """Return redirect response when admin access is unavailable."""
    if current_user is None:
        return RedirectResponse(
            build_redirect_url("/", error="Please log in to access the admin panel."),
            status_code=303,
        )

    if not current_user.is_admin:
        return RedirectResponse(
            build_redirect_url("/dashboard", error="Admin access is required."),
            status_code=303,
        )

    return None


def get_default_landing_path(current_user: User | None) -> str:
    """Return post-login landing path by role."""
    if current_user and current_user.is_admin:
        return "/admin"
    return "/dashboard"


def normalize_permission_name(name: str) -> str:
    """Normalize permission names into snake_case style."""
    normalized = re.sub(r"[\s-]+", "_", name.strip().lower())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def normalize_role_names(role_names: list[str]) -> list[str]:
    """Normalize and deduplicate role names list."""
    return sorted({
        role_name.strip().lower()
        for role_name in role_names
        if role_name and role_name.strip()
    })


def get_dashboard_variant(user: User) -> str:
    """Map user permissions to dashboard variant name."""
    if user.is_admin:
        return "admin"

    if any(
        user.has_permission(permission_name)
        for permission_name in ("create_book", "update_book", "delete_book")
    ):
        return "editor"

    return "viewer"


def get_dashboard_role_label(user: User) -> str:
    """Return human-friendly role label for dashboard topbar."""
    variant = get_dashboard_variant(user)
    if variant == "admin":
        return "Admin"
    if variant == "editor":
        return "Editor"
    return "Viewer"


def get_dashboard_sidebar_navigation(user: User) -> list[dict]:
    """Return sidebar navigation config by dashboard variant."""
    variant = get_dashboard_variant(user)
    if variant == "admin":
        return [
            {
                "title": "Admin",
                "items": [
                    {
                        "label": "Dashboard",
                        "href": "/admin#dashboard",
                        "icon": "bi-speedometer2",
                        "target_type": "section",
                        "target": "dashboard",
                    },
                    {
                        "label": "Users",
                        "href": "/admin#users",
                        "icon": "bi-people",
                        "target_type": "section",
                        "target": "users",
                    },
                    {
                        "label": "Books",
                        "href": "/admin#books",
                        "icon": "bi-book",
                        "target_type": "section",
                        "target": "books",
                    },
                    {
                        "label": "Permissions",
                        "href": "/admin#permissions",
                        "icon": "bi-shield-lock",
                        "target_type": "section",
                        "target": "permissions",
                    },
                ],
            }
        ]

    if variant == "editor":
        editor_items = [
            {
                "label": "Dashboard",
                "href": "/dashboard#books",
                "icon": "bi-speedometer2",
                "target_type": "user_section",
                "target": "books",
            },
            {
                "label": "My Books",
                "href": "/dashboard#books",
                "icon": "bi-journal-bookmark",
                "target_type": "user_section",
                "target": "books",
            },
        ]
        if user.has_permission("create_book"):
            editor_items.append(
                {
                    "label": "Add Book",
                    "href": "/dashboard#add-book",
                    "icon": "bi-plus-circle",
                    "target_type": "user_section",
                    "target": "add-book",
                }
            )
        editor_items.append(
            {
                "label": "Summaries",
                "href": "/dashboard#summary",
                "icon": "bi-stars",
                "target_type": "user_section",
                "target": "summary",
            }
        )
        return [{"title": "Editor", "items": editor_items}]

    return [
        {
            "title": "Viewer",
            "items": [
                {
                    "label": "Dashboard",
                    "href": "/dashboard#browse",
                    "icon": "bi-speedometer2",
                    "target_type": "user_section",
                    "target": "browse",
                },
                {
                    "label": "Browse Books",
                    "href": "/dashboard#browse",
                    "icon": "bi-search",
                    "target_type": "user_section",
                    "target": "browse",
                },
                {
                    "label": "Summaries",
                    "href": "/dashboard#summary",
                    "icon": "bi-stars",
                    "target_type": "user_section",
                    "target": "summary",
                },
            ],
        }
    ]


def get_user_dashboard_section(
    current_user: User,
    *,
    editor_section: str,
    viewer_section: str = "overview",
) -> str:
    if get_dashboard_variant(current_user) == "viewer":
        return viewer_section
    return editor_section


@router.get("/", response_class=HTMLResponse)
def login_page(
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    success: str | None = None,
    error: str | None = None,
):
    current_user = get_current_user_from_cookie(access_token, db)
    if current_user:
        return RedirectResponse(get_default_landing_path(current_user), status_code=303)

    response = render_template(
        request,
        "login.html",
        page_title="Login",
        success=success,
        error=error,
        form_data={},
    )
    if access_token:
        clear_auth_cookie(response)
    return response


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip()
    try:
        db_user = authenticate_user(db, username=username, password=password)
    except InvalidCredentialsError as exc:
        return render_template(
            request,
            "login.html",
            page_title="Login",
            error=str(exc),
            form_data={"username": username},
        )
    except SQLAlchemyError:
        db.rollback()
        return render_template(
            request,
            "login.html",
            page_title="Login",
            error="We could not verify your login right now. Please try again.",
            form_data={"username": username},
        )

    token = create_token_for_user(db_user)
    response = RedirectResponse(get_default_landing_path(db_user), status_code=303)
    set_auth_cookie(response, token)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    success: str | None = None,
    error: str | None = None,
):
    current_user = get_current_user_from_cookie(access_token, db)
    if current_user:
        return RedirectResponse(get_default_landing_path(current_user), status_code=303)

    response = render_template(
        request,
        "register.html",
        page_title="Register",
        success=success,
        error=error,
        form_data={},
    )
    if access_token:
        clear_auth_cookie(response)
    return response


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip()
    email = email.strip().lower()
    form_data = {"username": username, "email": email}

    if password != confirm_password:
        return render_template(
            request,
            "register.html",
            page_title="Register",
            error="Passwords do not match.",
            form_data=form_data,
        )

    try:
        register_user(db, username=username, email=email, password=password)
    except (UsernameAlreadyExistsError, EmailAlreadyExistsError) as exc:
        return render_template(
            request,
            "register.html",
            page_title="Register",
            error=str(exc),
            form_data=form_data,
        )
    except SQLAlchemyError:
        db.rollback()
        return render_template(
            request,
            "register.html",
            page_title="Register",
            error="We could not create your account right now. Please try again.",
            form_data=form_data,
        )

    return RedirectResponse(
        build_redirect_url("/", success="Account created successfully. Please sign in."),
        status_code=303,
    )


@router.post("/logout")
def logout():
    response = RedirectResponse(
        build_redirect_url("/", success="You have been logged out."),
        status_code=303,
    )
    clear_auth_cookie(response)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    edit_id: int | None = None,
    success: str | None = None,
    error: str | None = None,
):
    current_user = get_current_user_from_cookie(access_token, db)
    if current_user is None:
        return RedirectResponse(
            build_redirect_url("/", error="Please log in to access your dashboard."),
            status_code=303,
        )
    dashboard_variant = get_dashboard_variant(current_user)
    if dashboard_variant == "admin":
        return RedirectResponse("/admin", status_code=303)

    try:
        if dashboard_variant == "viewer":
            books = book_crud.get_all_books(db)
        else:
            books = book_crud.get_books(db, current_user.id)
    except SQLAlchemyError:
        db.rollback()
        books = []
        error = error or "We could not load your books right now."

    can_create_book = current_user.has_permission("create_book")
    can_update_book = current_user.has_permission("update_book")
    can_delete_book = current_user.has_permission("delete_book")
    unique_author_count = len(
        {
            (book.author or "").strip().lower()
            for book in books
            if (book.author or "").strip()
        }
    )
    unique_publisher_count = len(
        {
            (book.publisher or "").strip().lower()
            for book in books
            if (book.publisher or "").strip()
        }
    )
    primary_role = current_user.role_names[0].title() if current_user.role_names else "Member"
    permission_count = len(current_user.permission_names)

    edit_book = None
    if edit_id is not None and not can_update_book and error is None:
        error = "You do not have permission to edit books."
    elif edit_id is not None:
        edit_book = next((book for book in books if book.id == edit_id), None)
        if edit_book is None and error is None:
            error = "Selected book was not found."

    initial_section = "books"
    if edit_book is not None:
        initial_section = "edit-book"
    elif edit_id is not None:
        initial_section = "books"

    if dashboard_variant == "viewer":
        dashboard_template = "viewer_dashboard.html"
        page_title = "Viewer Dashboard"
        body_class = "viewer-body"
    else:
        dashboard_template = "user_dashboard.html"
        page_title = "Editor Dashboard"
        body_class = "user-body editor-body"

    return render_template(
        request,
        dashboard_template,
        page_title=page_title,
        app_layout=True,
        body_class=body_class,
        current_user=current_user,
        dashboard_role_label=get_dashboard_role_label(current_user),
        sidebar_navigation=get_dashboard_sidebar_navigation(current_user),
        books=books,
        edit_book=edit_book,
        can_create_book=can_create_book,
        can_update_book=can_update_book,
        can_delete_book=can_delete_book,
        unique_author_count=unique_author_count,
        unique_publisher_count=unique_publisher_count,
        primary_role=primary_role,
        permission_count=permission_count,
        initial_section=initial_section,
        success=success,
        error=error,
    )


@router.post("/add-book")
def add_book(
    title: str = Form(...),
    author: str = Form(...),
    publisher: str = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    if current_user is None:
        return RedirectResponse(
            build_redirect_url("/", error="Please log in to add a book."),
            status_code=303,
        )

    if not current_user.has_permission("create_book"):
        return RedirectResponse(
            build_redirect_url(
                "/dashboard",
                error="You do not have permission to add books.",
                fragment=get_user_dashboard_section(
                    current_user,
                    editor_section="add-book",
                    viewer_section="access",
                ),
            ),
            status_code=303,
        )

    title = title.strip()
    author = author.strip()
    publisher = publisher.strip()
    if not title or not author or not publisher:
        return RedirectResponse(
            build_redirect_url(
                "/dashboard",
                error="Title, author, and publisher are required.",
                fragment="add-book",
            ),
            status_code=303,
        )

    file_data = None
    if file and file.filename:
        try:
            file_data = save_pdf_upload(file)
        except InvalidPdfUpload as exc:
            return RedirectResponse(
                build_redirect_url("/dashboard", error=str(exc), fragment="add-book"),
                status_code=303,
            )

    book = BookCreate(title=title, author=author, publisher=publisher)
    try:
        book_crud.create_book(
            db,
            book,
            current_user.id,
            file_path=(file_data or {}).get("file_path"),
            file_name=(file_data or {}).get("file_name"),
            mime_type=(file_data or {}).get("mime_type"),
            file_size=(file_data or {}).get("file_size"),
        )
    except DuplicateBookError as exc:
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url("/dashboard", error=str(exc), fragment="add-book"),
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                "/dashboard",
                error="We could not save the book right now.",
                fragment="add-book",
            ),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url("/dashboard", success="Book added successfully.", fragment="books"),
        status_code=303,
    )


@router.post("/update-book/{book_id}")
def update_book(
    book_id: int,
    title: str = Form(...),
    author: str = Form(...),
    publisher: str = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    if current_user is None:
        return RedirectResponse(
            build_redirect_url("/", error="Please log in to update a book."),
            status_code=303,
        )

    if not current_user.has_permission("update_book"):
        return RedirectResponse(
            build_redirect_url(
                "/dashboard",
                error="You do not have permission to update books.",
                fragment=get_user_dashboard_section(
                    current_user,
                    editor_section="books",
                    viewer_section="access",
                ),
            ),
            status_code=303,
        )

    title = title.strip()
    author = author.strip()
    publisher = publisher.strip()
    if not title or not author or not publisher:
        return RedirectResponse(
            build_redirect_url(
                f"/dashboard?edit_id={book_id}",
                error="All book details are required for updates.",
                fragment="edit-book",
            ),
            status_code=303,
        )

    file_data = None
    if file and file.filename:
        try:
            file_data = save_pdf_upload(file)
        except InvalidPdfUpload as exc:
            return RedirectResponse(
                build_redirect_url(
                    f"/dashboard?edit_id={book_id}",
                    error=str(exc),
                    fragment="edit-book",
                ),
                status_code=303,
            )

    try:
        updated_book = book_crud.update_book(
            db,
            book_id,
            BookCreate(title=title, author=author, publisher=publisher),
            current_user.id,
        )
    except DuplicateBookError as exc:
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                f"/dashboard?edit_id={book_id}",
                error=str(exc),
                fragment="edit-book",
            ),
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                f"/dashboard?edit_id={book_id}",
                error="We could not update the book right now.",
                fragment="edit-book",
            ),
            status_code=303,
        )

    if updated_book is None:
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                f"/dashboard?edit_id={book_id}",
                error="Book not found.",
                fragment="edit-book",
            ),
            status_code=303,
        )

    if file_data:
        old_path = updated_book.file_path
        try:
            book_crud.update_book_file(
                db,
                updated_book,
                file_path=file_data["file_path"],
                file_name=file_data["file_name"],
                mime_type=file_data["mime_type"],
                file_size=file_data["file_size"],
            )
        except SQLAlchemyError:
            db.rollback()
            delete_upload_file(file_data.get("file_path"))
            return RedirectResponse(
                build_redirect_url(
                    f"/dashboard?edit_id={book_id}",
                    error="We could not update the PDF right now.",
                    fragment="edit-book",
                ),
                status_code=303,
            )
        delete_upload_file(old_path)

    return RedirectResponse(
        build_redirect_url("/dashboard", success="Book updated successfully.", fragment="books"),
        status_code=303,
    )


@router.post("/delete-book/{book_id}")
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    if current_user is None:
        return RedirectResponse(
            build_redirect_url("/", error="Please log in to delete a book."),
            status_code=303,
        )

    if not current_user.has_permission("delete_book"):
        return RedirectResponse(
            build_redirect_url(
                "/dashboard",
                error="You do not have permission to delete books.",
                fragment=get_user_dashboard_section(
                    current_user,
                    editor_section="books",
                    viewer_section="access",
                ),
            ),
            status_code=303,
        )

    try:
        deleted_book = book_crud.delete_book(db, book_id, current_user.id)
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                "/dashboard",
                error="We could not delete the book right now.",
                fragment="books",
            ),
            status_code=303,
        )

    if deleted_book is None:
        return RedirectResponse(
            build_redirect_url("/dashboard", error="Book not found.", fragment="books"),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url("/dashboard", success="Book deleted successfully.", fragment="books"),
        status_code=303,
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    edit_user_id: int | None = None,
    edit_permission_id: int | None = None,
    edit_book_id: int | None = None,
    open_form: str | None = None,
    success: str | None = None,
    error: str | None = None,
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    users = user_crud.get_all_users(db)
    roles = user_crud.get_all_roles(db)
    permissions = permission_crud.get_all_permissions(db)
    books = book_crud.get_all_books(db)
    admin_user_count = sum(1 for user in users if user.is_admin)
    editor_user_count = sum(1 for user in users if "editor" in user.role_names)
    viewer_user_count = sum(1 for user in users if "viewer" in user.role_names)

    valid_form_panels = {"users", "permissions", "books"}
    open_form = open_form if open_form in valid_form_panels else None

    initial_section = "dashboard"
    if edit_user_id is not None:
        initial_section = "users"
    elif edit_permission_id is not None:
        initial_section = "permissions"
    elif edit_book_id is not None:
        initial_section = "books"
    elif open_form is not None:
        initial_section = open_form

    edit_user = None
    if edit_user_id is not None:
        edit_user = next((user for user in users if user.id == edit_user_id), None)
        if edit_user is None and error is None:
            error = "Selected user was not found."

    edit_permission = None
    edit_permission_role_names: list[str] = []
    if edit_permission_id is not None:
        edit_permission = next(
            (permission for permission in permissions if permission.id == edit_permission_id),
            None,
        )
        if edit_permission is None and error is None:
            error = "Selected permission was not found."
        elif edit_permission is not None:
            edit_permission_role_names = sorted(
                role.name
                for role in edit_permission.roles
            )

    edit_book = None
    if edit_book_id is not None:
        edit_book = next((book for book in books if book.db_id == edit_book_id), None)
        if edit_book is None and error is None:
            error = "Selected book was not found."

    return render_template(
        request,
        "admin_dashboard.html",
        page_title="Admin Panel",
        admin_layout=True,
        body_class="admin-body",
        current_user=current_user,
        dashboard_role_label=get_dashboard_role_label(current_user),
        sidebar_navigation=get_dashboard_sidebar_navigation(current_user),
        users=users,
        roles=roles,
        permissions=permissions,
        books=books,
        admin_user_count=admin_user_count,
        editor_user_count=editor_user_count,
        viewer_user_count=viewer_user_count,
        initial_section=initial_section,
        open_form=open_form,
        edit_user=edit_user,
        edit_permission=edit_permission,
        edit_permission_role_names=edit_permission_role_names,
        edit_book=edit_book,
        success=success,
        error=error,
    )


@router.post("/admin/users")
def admin_create_user(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role_name: str = Form(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    username = username.strip()
    email = email.strip().lower()
    password = password.strip()
    role_name = role_name.strip().lower()

    if not username or not email or not password:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Username, email, password, and role are required.",
                fragment="users",
                query_updates={"open_form": "users"},
            ),
            status_code=303,
        )

    valid_roles = {role.name for role in user_crud.get_all_roles(db)}
    if role_name not in valid_roles:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Please choose a valid role.",
                fragment="users",
                query_updates={"open_form": "users"},
            ),
            status_code=303,
        )

    try:
        register_user(
            db,
            username=username,
            email=email,
            password=password,
            role_name=role_name,
        )
    except (UsernameAlreadyExistsError, EmailAlreadyExistsError) as exc:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error=str(exc),
                fragment="users",
                query_updates={"open_form": "users"},
            ),
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="We could not create the user right now.",
                fragment="users",
                query_updates={"open_form": "users"},
            ),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url("/admin", success="User created successfully.", fragment="users"),
        status_code=303,
    )


@router.post("/admin/users/update/{user_id}")
def admin_update_user(
    user_id: int,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(default=""),
    role_name: str = Form(...),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    username = username.strip()
    email = email.strip().lower()
    password = password.strip()
    role_name = role_name.strip().lower()

    if not username or not email:
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_user_id={user_id}",
                error="Username, email, and role are required.",
                fragment="users",
            ),
            status_code=303,
        )

    valid_roles = {role.name for role in user_crud.get_all_roles(db)}
    if role_name not in valid_roles:
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_user_id={user_id}",
                error="Please choose a valid role.",
                fragment="users",
            ),
            status_code=303,
        )

    try:
        update_user_account(
            db,
            user_id=user_id,
            username=username,
            email=email,
            role_name=role_name,
            password=password or None,
        )
    except (UsernameAlreadyExistsError, EmailAlreadyExistsError, UserNotFoundError) as exc:
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_user_id={user_id}",
                error=str(exc),
                fragment="users",
            ),
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_user_id={user_id}",
                error="We could not update the user right now.",
                fragment="users",
            ),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url("/admin", success="User updated successfully.", fragment="users"),
        status_code=303,
    )


@router.post("/admin/users/delete/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    if current_user.id == user_id:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="You cannot delete your own admin account.",
                fragment="users",
            ),
            status_code=303,
        )

    user = user_crud.get_user_by_id(db, user_id)
    if user is None:
        return RedirectResponse(
            build_redirect_url("/admin", error="User not found.", fragment="users"),
            status_code=303,
        )

    try:
        user_crud.delete_user(db, user)
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="We could not delete the user right now.",
                fragment="users",
            ),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url("/admin", success="User deleted successfully.", fragment="users"),
        status_code=303,
    )


@router.post("/admin/permissions")
def admin_create_permission(
    name: str = Form(...),
    role_names: list[str] | None = Form(default=None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    permission_name = normalize_permission_name(name)
    selected_role_names = normalize_role_names(role_names or [])
    valid_roles = {role.name for role in user_crud.get_all_roles(db)}
    invalid_roles = sorted(set(selected_role_names) - valid_roles)

    if not permission_name:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Permission name is required.",
                fragment="permissions",
                query_updates={"open_form": "permissions"},
            ),
            status_code=303,
        )

    if not PERMISSION_NAME_PATTERN.fullmatch(permission_name):
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error=(
                    "Permission names must start with a letter and use only "
                    "lowercase letters, numbers, and underscores."
                ),
                fragment="permissions",
                query_updates={"open_form": "permissions"},
            ),
            status_code=303,
        )

    if invalid_roles:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Please choose valid roles for this permission.",
                fragment="permissions",
                query_updates={"open_form": "permissions"},
            ),
            status_code=303,
        )

    if permission_crud.get_permission_by_name(db, permission_name) is not None:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error=f'The "{permission_name}" permission already exists.',
                fragment="permissions",
                query_updates={"open_form": "permissions"},
            ),
            status_code=303,
        )

    try:
        permission_crud.create_permission(
            db,
            name=permission_name,
            role_names=selected_role_names,
        )
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="We could not create the permission right now.",
                fragment="permissions",
                query_updates={"open_form": "permissions"},
            ),
            status_code=303,
        )

    success_message = f'Permission "{permission_name}" created successfully.'
    if selected_role_names:
        assigned_roles = ", ".join(role_name.title() for role_name in selected_role_names)
        success_message = (
            f'Permission "{permission_name}" created and assigned to {assigned_roles}.'
        )

    return RedirectResponse(
        build_redirect_url(
            "/admin",
            success=success_message,
            fragment="permissions",
        ),
        status_code=303,
    )


@router.post("/admin/permissions/update/{permission_id}")
def admin_update_permission_roles(
    permission_id: int,
    role_names: list[str] | None = Form(default=None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    permission = permission_crud.get_permission_by_id(db, permission_id)
    if permission is None:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Permission not found.",
                fragment="permissions",
            ),
            status_code=303,
        )

    selected_role_names = normalize_role_names(role_names or [])
    valid_roles = {role.name for role in user_crud.get_all_roles(db)}
    invalid_roles = sorted(set(selected_role_names) - valid_roles)
    if invalid_roles:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Please choose valid roles for this permission.",
                fragment="permissions",
                query_updates={"edit_permission_id": permission_id},
            ),
            status_code=303,
        )

    try:
        permission_crud.update_permission_roles(
            db,
            permission=permission,
            role_names=selected_role_names,
        )
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="We could not update the permission roles right now.",
                fragment="permissions",
                query_updates={"edit_permission_id": permission_id},
            ),
            status_code=303,
        )

    if selected_role_names:
        assigned_roles = ", ".join(role_name.title() for role_name in selected_role_names)
        success_message = f'Permission "{permission.name}" is now assigned to {assigned_roles}.'
    else:
        success_message = f'Permission "{permission.name}" has no assigned roles now.'

    return RedirectResponse(
        build_redirect_url(
            "/admin",
            success=success_message,
            fragment="permissions",
        ),
        status_code=303,
    )


@router.post("/admin/permissions/delete/{permission_id}")
def admin_delete_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    permission = permission_crud.get_permission_by_id(db, permission_id)
    if permission is None:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Permission not found.",
                fragment="permissions",
            ),
            status_code=303,
        )

    permission_name = permission.name
    try:
        permission_crud.delete_permission(db, permission=permission)
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="We could not delete the permission right now.",
                fragment="permissions",
            ),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url(
            "/admin",
            success=f'Permission "{permission_name}" deleted successfully.',
            fragment="permissions",
        ),
        status_code=303,
    )


@router.post("/admin/books")
def admin_create_book(
    owner_id: int = Form(...),
    title: str = Form(...),
    author: str = Form(...),
    publisher: str = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    title = title.strip()
    author = author.strip()
    publisher = publisher.strip()
    if not title or not author or not publisher:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Owner, title, author, and publisher are required.",
                fragment="books",
                query_updates={"open_form": "books"},
            ),
            status_code=303,
        )

    owner = user_crud.get_user_by_id(db, owner_id)
    if owner is None:
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="Selected owner was not found.",
                fragment="books",
                query_updates={"open_form": "books"},
            ),
            status_code=303,
        )

    file_data = None
    if file and file.filename:
        try:
            file_data = save_pdf_upload(file)
        except InvalidPdfUpload as exc:
            return RedirectResponse(
                build_redirect_url(
                    "/admin",
                    error=str(exc),
                    fragment="books",
                    query_updates={"open_form": "books"},
                ),
                status_code=303,
            )

    try:
        book_crud.create_book(
            db,
            BookCreate(title=title, author=author, publisher=publisher),
            owner_id,
            file_path=(file_data or {}).get("file_path"),
            file_name=(file_data or {}).get("file_name"),
            mime_type=(file_data or {}).get("mime_type"),
            file_size=(file_data or {}).get("file_size"),
        )
    except DuplicateBookError as exc:
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error=str(exc),
                fragment="books",
                query_updates={"open_form": "books"},
            ),
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="We could not create the book right now.",
                fragment="books",
                query_updates={"open_form": "books"},
            ),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url("/admin", success="Book created successfully.", fragment="books"),
        status_code=303,
    )


@router.post("/admin/books/update/{book_db_id}")
def admin_update_book(
    book_db_id: int,
    title: str = Form(...),
    author: str = Form(...),
    publisher: str = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    title = title.strip()
    author = author.strip()
    publisher = publisher.strip()
    if not title or not author or not publisher:
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_book_id={book_db_id}",
                error="Title, author, and publisher are required.",
                fragment="books",
            ),
            status_code=303,
        )

    file_data = None
    if file and file.filename:
        try:
            file_data = save_pdf_upload(file)
        except InvalidPdfUpload as exc:
            return RedirectResponse(
                build_redirect_url(
                    f"/admin?edit_book_id={book_db_id}",
                    error=str(exc),
                    fragment="books",
                ),
                status_code=303,
            )

    try:
        updated_book = book_crud.update_book_by_db_id(
            db,
            book_db_id,
            BookCreate(title=title, author=author, publisher=publisher),
        )
    except DuplicateBookError as exc:
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_book_id={book_db_id}",
                error=str(exc),
                fragment="books",
            ),
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_book_id={book_db_id}",
                error="We could not update the book right now.",
                fragment="books",
            ),
            status_code=303,
        )

    if updated_book is None:
        delete_upload_file((file_data or {}).get("file_path"))
        return RedirectResponse(
            build_redirect_url(
                f"/admin?edit_book_id={book_db_id}",
                error="Book not found.",
                fragment="books",
            ),
            status_code=303,
        )

    if file_data:
        old_path = updated_book.file_path
        try:
            book_crud.update_book_file(
                db,
                updated_book,
                file_path=file_data["file_path"],
                file_name=file_data["file_name"],
                mime_type=file_data["mime_type"],
                file_size=file_data["file_size"],
            )
        except SQLAlchemyError:
            db.rollback()
            delete_upload_file(file_data.get("file_path"))
            return RedirectResponse(
                build_redirect_url(
                    f"/admin?edit_book_id={book_db_id}",
                    error="We could not update the PDF right now.",
                    fragment="books",
                ),
                status_code=303,
            )
        delete_upload_file(old_path)

    return RedirectResponse(
        build_redirect_url("/admin", success="Book updated successfully.", fragment="books"),
        status_code=303,
    )


@router.post("/admin/books/delete/{book_db_id}")
def admin_delete_book(
    book_db_id: int,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    current_user = get_current_user_from_cookie(access_token, db)
    access_redirect = get_admin_redirect(current_user)
    if access_redirect:
        return access_redirect

    try:
        deleted_book = book_crud.delete_book_by_db_id(db, book_db_id)
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            build_redirect_url(
                "/admin",
                error="We could not delete the book right now.",
                fragment="books",
            ),
            status_code=303,
        )

    if deleted_book is None:
        return RedirectResponse(
            build_redirect_url("/admin", error="Book not found.", fragment="books"),
            status_code=303,
        )

    return RedirectResponse(
        build_redirect_url("/admin", success="Book deleted successfully.", fragment="books"),
        status_code=303,
    )
