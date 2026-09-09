from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables and a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    rhapto_llm_model: str = "claude-sonnet-5"
    rhapto_embedding_model: str = "BAAI/bge-small-en-v1.5"
    rhapto_soffice_binary: str = "soffice"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
