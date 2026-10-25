from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Panel Dashboard API"
    # Required, with no default: the other three services already fail startup when
    # SECRET_KEY is absent. A default here meant a deployment that forgot the variable
    # signed session and password-reset JWTs with a value published in this file.
    secret_key: str = Field(..., validation_alias="SECRET_KEY")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    assigned_round: str = "Mid-Term Evaluation - Round 1"
    evaluation_timer_seconds: int = 30 * 60

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    report_dir: str = Field(default="reports", validation_alias="REPORT_DIR")
    http_timeout: float = Field(default=120.0, validation_alias="HTTP_TIMEOUT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_key: str | None = Field(
        default=None,
        validation_alias="SUPABASE_KEY",
        description="Supabase anon (public) key — safe for browsers with RLS.",
    )
    supabase_service_key: str | None = Field(
        default=None,
        validation_alias="SUPABASE_SERVICE_KEY",
        description="Service role key — server only, bypasses RLS.",
    )

    # Shared secret used by the admin portal to call sync endpoints.
    # Set to a long random string in both portals' .env files.
    admin_api_key: str = Field(
        ...,
        validation_alias="ADMIN_API_KEY",
        description="Shared API key for admin-portal → panel-portal sync calls.",
    )

    # Set SEED_DEMO_DATA=true in .env to seed fake teams/slots for local dev.
    # In production this should be false — data comes from the admin portal.
    seed_demo_data: bool = Field(default=False, validation_alias="SEED_DEMO_DATA")

    mail_username: str = Field(default="", validation_alias="MAIL_USERNAME")
    mail_password: str = Field(default="", validation_alias="MAIL_PASSWORD")
    mail_from: str = Field(default="", validation_alias="MAIL_FROM")
    mail_port: int = Field(default=587, validation_alias="MAIL_PORT")
    mail_server: str = Field(default="", validation_alias="MAIL_SERVER")

    @property
    def report_path(self) -> Path:
        return Path(self.report_dir)

    @field_validator("database_url")
    @classmethod
    def _reject_sqlite(cls, value: str | None) -> str | None:
        if not value:
            return value
        if value.startswith("sqlite"):
            raise ValueError("SQLite is disabled. Use Supabase Postgres DATABASE_URL.")
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

settings = Settings()
