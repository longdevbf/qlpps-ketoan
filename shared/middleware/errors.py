"""Global FastAPI exception handlers — JSON cho /api/, HTML 500 page cho /."""
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException


_log = logging.getLogger("app")


def _json_safe(v) -> bool:
    if v is None or isinstance(v, (str, int, float, bool)):
        return True
    if isinstance(v, (list, tuple)):
        return all(_json_safe(x) for x in v)
    if isinstance(v, dict):
        return all(isinstance(k, str) and _json_safe(x) for k, x in v.items())
    return False


def _wants_json(request: Request) -> bool:
    return (
        request.url.path.startswith("/api/")
        or "application/json" in request.headers.get("accept", "")
    )


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        # Redirect (3xx) phải giữ Location header — pattern dùng để bảo vệ trang HTML
        # qua dependency raise HTTPException(307, headers={"Location": "/login"}).
        if 300 <= exc.status_code < 400:
            location = (exc.headers or {}).get("Location") or (exc.headers or {}).get("location")
            if location:
                return RedirectResponse(location, status_code=exc.status_code)
        if _wants_json(request):
            return JSONResponse(
                {"error": exc.detail, "code": exc.status_code},
                status_code=exc.status_code,
            )
        return HTMLResponse(
            f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>",
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        # exc.errors() có thể chứa `ctx.input` là bytes/UploadFile (multipart)
        # → JSON không serialize được. Strip những giá trị non-JSON-safe.
        safe_errors = []
        for err in exc.errors():
            err = dict(err)
            ctx = err.get("ctx")
            if isinstance(ctx, dict):
                ctx = {
                    k: (
                        f"<{type(v).__name__} len={len(v)}>"
                        if isinstance(v, (bytes, bytearray))
                        else (f"<{type(v).__name__}>" if not _json_safe(v) else v)
                    )
                    for k, v in ctx.items()
                }
                err["ctx"] = ctx
            inp = err.get("input")
            if isinstance(inp, (bytes, bytearray)):
                err["input"] = f"<bytes len={len(inp)}>"
            elif inp is not None and not _json_safe(inp):
                err["input"] = f"<{type(inp).__name__}>"
            safe_errors.append(err)
        try:
            _log.warning("validation_failed %s %s details=%s",
                         request.method, request.url.path, safe_errors)
        except Exception:
            pass
        return JSONResponse(
            {"error": "validation_failed", "details": safe_errors, "code": 422},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(IntegrityError)
    async def db_integrity_exc(request: Request, exc: IntegrityError):
        _log.warning("integrity error: %s", exc.orig)
        return JSONResponse(
            {"error": "data_conflict", "detail": str(exc.orig), "code": 409},
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(SQLAlchemyError)
    async def db_exc(request: Request, exc: SQLAlchemyError):
        _log.error("db error: %s", exc)
        return JSONResponse(
            {"error": "database_error", "code": 500},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception):
        _log.exception("unhandled: %s", exc)
        if _wants_json(request):
            return JSONResponse(
                {"error": "internal_error", "code": 500},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return HTMLResponse(
            "<h1>500</h1><p>Internal server error</p>",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
