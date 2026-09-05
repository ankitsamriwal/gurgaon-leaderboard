from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gurgaon_leaderboard"
    redis_url: str = "redis://localhost:6379/0"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    jwt_secret: str = "dev-secret-change-me"

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    turnstile_secret_key: str = ""

    # Comma-separated list. Defaults to the Vite dev server origin so
    # `npm run dev` works against a local API out of the box; production
    # must set this to the real deployed frontend origin(s).
    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
