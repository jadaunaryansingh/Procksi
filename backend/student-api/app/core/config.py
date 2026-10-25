from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, field_validator


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15   # short-lived — refresh token handles sessions
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    FRONTEND_URL: str = "http://localhost:3000"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Strip all query parameters to avoid conflicts with connect_args
        if "?" in v:
            v = v.split("?")[0]
        return v

    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = ""
    MAIL_PORT: int = 587
    MAIL_SERVER: str = ""
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    OPENAI_API_KEY: str = ""
    NVIDIA_API_KEY: str = ""
    AI_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    AI_MODEL: str = "meta/llama-3.1-8b-instruct"
    EMBEDDING_MODEL: str = "nvidia/nv-embedqa-e5-v5"

    REPOSITORY_ANALYSIS_API_URL: str = "http://65.0.167.190:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

