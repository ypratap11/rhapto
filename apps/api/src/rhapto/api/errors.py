from __future__ import annotations

import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from rhapto.engine.types import EngineError, ProfileError
from rhapto.services.jobtext import JobTextError
from rhapto.services.llm import LLMNotConfiguredError
from rhapto.services.secrets import KeyUnreadableError, SecretsError

PROBLEM = "application/problem+json"
KEY_UNREADABLE_MESSAGE = (
    "Your stored API key can no longer be decrypted (the server secret changed). "
    "Re-enter it in Settings."
)
logger = logging.getLogger("rhapto.api")


def problem(status: int, title: str, detail: str | None = None, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def status_title(status: int) -> str:
    """RFC 7807 title for a status code; non-standard codes have no phrase."""
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def not_found(what: str, ident: object) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} {ident} not found")


def _json_safe_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """The validation errors, minus anything that came from the request.

    ``input`` is dropped outright: pydantic sets it to the value that failed, and for a ``missing``
    error that value is the *whole* request body — so echoing it turns "you forgot a field" into a
    response that quotes the provider API key the client sent alongside it. ``loc`` and ``msg``
    already say what is wrong. Raw exception objects pydantic embeds in ``ctx.error`` are
    stringified so the list can be JSON-encoded (e.g. a model_validator raising ValueError).
    """
    sanitized: list[dict[str, Any]] = []
    for raw in errors:
        error = {k: v for k, v in dict(raw).items() if k != "input"}
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            error["ctx"] = {
                k: str(v) if isinstance(v, BaseException) else v for k, v in ctx.items()
            }
        sanitized.append(error)
    return sanitized


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = status_title(exc.status_code)
        detail = exc.detail if isinstance(exc.detail, str) else None
        response = problem(exc.status_code, title, detail)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(
            422,
            "Unprocessable Entity",
            "request validation failed",
            errors=_json_safe_errors(exc.errors()),
        )

    @app.exception_handler(ProfileError)
    async def _profile(request: Request, exc: ProfileError) -> JSONResponse:
        return problem(422, "Unprocessable Entity", str(exc))

    @app.exception_handler(JobTextError)
    async def _jobtext(request: Request, exc: JobTextError) -> JSONResponse:
        return problem(422, "Unprocessable Entity", str(exc))

    @app.exception_handler(LLMNotConfiguredError)
    async def _llm_not_configured(request: Request, exc: LLMNotConfiguredError) -> JSONResponse:
        # 409, not 422: the request was fine, the account is not set up yet. `code` lets the web
        # app route the user to Settings instead of showing a bare message.
        return problem(409, "Conflict", str(exc), code="llm_not_configured")

    @app.exception_handler(SecretsError)
    async def _secrets(request: Request, exc: SecretsError) -> JSONResponse:
        # Both halves are setup conflicts the caller can act on, never a 500: a rotated secret
        # leaves the stored key as unreadable ciphertext (the user re-enters it), while a malformed
        # RHAPTO_SECRET_KEY is the operator's to fix and keeps its own message, which carries the
        # "generate one with ..." hint.
        logger.warning("provider key secret problem: %s", exc)
        detail = KEY_UNREADABLE_MESSAGE if isinstance(exc, KeyUnreadableError) else str(exc)
        return problem(409, "Conflict", detail, code="llm_key_unreadable")

    @app.exception_handler(EngineError)
    async def _engine(request: Request, exc: EngineError) -> JSONResponse:
        return problem(500, "Internal Server Error", str(exc))

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        # e.g. two concurrent writers racing for the same (job_id, version).
        logger.warning(
            "database integrity error on %s %s", request.method, request.url.path, exc_info=exc
        )
        return problem(409, "Conflict", "the change conflicts with existing data")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Last resort so every error leaves the API as problem+json. The traceback goes to
        # the log; the client never sees the exception text.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return problem(500, "Internal Server Error", "unexpected server error")
