from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables and a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    rhapto_llm_model: str = "claude-sonnet-5"
    rhapto_embedding_model: str = "BAAI/bge-small-en-v1.5"
    rhapto_soffice_binary: str = "soffice"
    database_url: str = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto"
    rhapto_test_database_url: str = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
    redis_url: str = "redis://localhost:6379/0"
    rhapto_api_token: str = ""
    rhapto_user_email: str = "user@example.com"
    rhapto_packages_dir: Path = Path("data/packages")
    rhapto_web_origin: str = "http://localhost:3000"
    rhapto_poll_interval_hours: int = 6
    rhapto_discovery_user_agent: str = "rhapto-discovery/0.3"
    rhapto_discovery_base_override: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
