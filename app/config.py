from functools import lru_cache
from pydantic import BaseSettings
  # kalau masih pakai pydantic <2, tetap bisa dari pydantic
# kalau pydantic v2: from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # JWT
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    JWT_ACCESS_EXPIRES_MIN: int = 60
    JWT_REFRESH_EXPIRES_MIN: int = 1440

    # Admin BasicAuth
    ADMIN_BASIC_USER: str
    ADMIN_BASIC_PASS: str

    # WhatsApp Gateway
    WA_GATEWAY_URL: str
    WA_TOKEN: str

    # Timezone
    TIMEZONE: str = "Asia/Jakarta"

    # Auth Config
    USE_JWT: bool = True
    DEFAULT_RESELLER_ID: str = "00000000-0000-0000-0000-000000000000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
