"""
Centralised application configuration.

All settings are read from environment variables (or a local .env file),
so the same image runs unchanged in development, CI, and production.
Never hardcode credentials or environment-specific values elsewhere.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    PROJECT_NAME: str = "VARUNA AI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"  # development | staging | production
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS (comma-separated list of allowed frontend origins) ---
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- Database (PostgreSQL + PostGIS) ---
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "varuna"
    POSTGRES_PASSWORD: str = "varuna"
    POSTGRES_DB: str = "varuna_ai"

    # --- Model artifacts ---
    # Directory where trained model weights/artifacts are stored and loaded from.
    # The ai_models package resolves its own paths relative to the repo root via
    # Path(__file__).parents[N]; this setting is informational and used in
    # the /predictions/model-info response.
    MODEL_ARTIFACT_DIR: str = "../ai_models/saved_models"


    # --- External data source credentials (Phase 2) ---
    # MOSDAC and NASA Earthdata require registered accounts; keys live in .env only.
    MOSDAC_API_USER: str | None = None
    MOSDAC_API_PASSWORD: str | None = None
    NASA_EARTHDATA_TOKEN: str | None = None

    # --- Application database ---
    # Full SQLAlchemy URL. Empty -> local SQLite file (backend/varuna.db), so the
    # app runs with zero setup; set e.g. "postgresql+psycopg://..." (or
    # USE_POSTGRES=true to build it from POSTGRES_*) in docker / production.
    DATABASE_URL: str = ""
    USE_POSTGRES: bool = False

    # --- What-if assistant (Claude) ---
    # "auto": Claude when a key is set, otherwise the free offline rule-based assistant.
    # "offline": always offline. "claude": always Claude (503 without a key).
    CHAT_PROVIDER: str = "auto"
    ANTHROPIC_API_KEY: str | None = None
    CHAT_MODEL: str = "claude-opus-5"
    # Chat is interactive: "medium" keeps tool-using answers responsive; raise to "high" for depth.
    CHAT_EFFORT: str = "medium"

    # --- Real-time alerting ---
    ALERTS_ENABLED: bool = True
    ALERT_SCAN_INTERVAL_MIN: int = 15
    ALERT_DEFAULT_MIN_LEVEL: str = "high"        # moderate | high | severe
    ALERT_COOLDOWN_MIN: int = 180
    ALERT_VALIDITY_HOURS: int = 24
    # Public URL of this backend, used for "Acknowledge" links inside messages.
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    DASHBOARD_URL: str = "http://localhost:5173"
    SECRET_KEY: str = "change-me-in-production"

    # Telegram Bot API (free): create a bot with @BotFather.
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_DEFAULT_CHAT_ID: str | None = None   # a control-room group, broadcast every alert

    # E-mail over SMTP (e.g. Gmail + App Password: smtp.gmail.com:587).
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_USE_TLS: bool = True

    # Twilio SMS + WhatsApp (free trial credit / WhatsApp sandbox).
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_SMS_FROM: str | None = None            # e.g. +15017122661
    TWILIO_WHATSAPP_FROM: str | None = None       # e.g. whatsapp:+14155238886 (sandbox)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.USE_POSTGRES:
            return self.postgres_url
        return f"sqlite:///{BACKEND_DIR / 'varuna.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
