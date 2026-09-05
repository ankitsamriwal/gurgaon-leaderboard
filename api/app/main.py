from fastapi import FastAPI

from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Gurgaon Leaderboard API")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
