from fastapi import FastAPI

from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Gurgaon Leaderboard API")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    if not settings.is_production:
        from app.routers.internal import router as internal_router

        app.include_router(internal_router)

    return app


app = create_app()
