from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://fnv:fnv@localhost:5432/fnv"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    google_factcheck_api_key: str = ""
    tavily_api_key: str = ""
    allowed_origins: str = "*"
    admin_key: str = ""   # empty = admin/review endpoints disabled
    rate_limit_per_minute: int = 10
    trusted_proxy_hops: int = 1   # proxies in front of the app that append to X-Forwarded-For
    max_concurrent_checks: int = 6
    max_input_chars: int = 5000


@lru_cache
def get_settings() -> Settings:
    return Settings()
