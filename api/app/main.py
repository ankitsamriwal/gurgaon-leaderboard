from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.payments import router as payments_router
from app.routers.projects import router as projects_router
from app.routers.webhooks import router as webhooks_router


def create_app() -> FastAPI:
    app = FastAPI(title="Gurgaon Leaderboard API")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Normalize every error response to docs/02-api-spec.md's standard
        shape: {"error": {"code": ..., "message": ...}}. Handlers raise
        HTTPException(detail={"error": {...}}) directly; FastAPI's own
        default wraps `detail` under a "detail" key instead, so unwrap it
        here rather than repeating the shape check at every call site.
        """
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code, content={"error": {"code": "ERROR", "message": str(exc.detail)}}
        )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(auth_router)
    app.include_router(payments_router)
    app.include_router(webhooks_router)
    app.include_router(projects_router)
    app.include_router(admin_router)

    if not settings.is_production:
        from app.routers.internal import router as internal_router
        from app.routers.payments import mock_router as payments_mock_router

        app.include_router(internal_router)
        app.include_router(payments_mock_router)

    return app


app = create_app()
