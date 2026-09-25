"""Canonical error envelope (TRD v4.1 §14).

{"error":{"code":"FORBIDDEN","message":"Access denied"}}
Codes: UNAUTHORIZED, FORBIDDEN, NOT_FOUND, VALIDATION_ERROR, CONFLICT,
RATE_LIMITED, INTERNAL_ERROR. Never leak stack traces, SQL, paths or secrets.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATUS_TO_CODE = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
}

SAFE_MESSAGES = {
    "UNAUTHORIZED": "Authentication required or invalid",
    "FORBIDDEN": "Access denied",
    "NOT_FOUND": "Resource not found",
    "VALIDATION_ERROR": "Invalid request",
    "CONFLICT": "State conflict; reconcile and retry",
    "RATE_LIMITED": "Too many requests; retry later",
    "INTERNAL_ERROR": "Something went wrong",
}


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None) -> None:
        self.status = status
        self.code = code
        self.message = message or SAFE_MESSAGES.get(code, "Request failed")
        super().__init__(self.message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_TO_CODE.get(exc.status_code, "INTERNAL_ERROR")
        return error_response(exc.status_code, code, SAFE_MESSAGES.get(code, "Request failed"))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Safe field/state details only — never internals.
        fields = [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "issue": e.get("msg", "invalid")}
            for e in exc.errors()
        ][:20]
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request",
                               "fields": fields}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Technical detail only in protected (server-side) logs.
        return error_response(500, "INTERNAL_ERROR", SAFE_MESSAGES["INTERNAL_ERROR"])
