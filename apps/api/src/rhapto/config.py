from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables and a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rhapto_llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    # Empty means "whatever the chosen provider's default model is" (see engine.providers.registry),
    # so switching RHAPTO_LLM_PROVIDER alone is enough.
    rhapto_llm_model: str = ""
    # Fernet secret for stored provider keys. `Settings` itself still accepts an empty value --
    # `services.secrets.fernet_for` falls back to one derived from rhapto_api_token, and tests for
    # that fallback construct `Settings` directly -- but `get_settings()`, the singleton every real
    # entrypoint uses, refuses to start without it. See `MissingSecretKeyError` below: with one
    # user in production and a second account close behind, a deployment must not run on a key
    # implicitly derived from its API token.
    rhapto_secret_key: str = ""
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


class MissingSecretKeyError(RuntimeError):
    """RHAPTO_SECRET_KEY is unset. Raised by `get_settings()`, not by `Settings` itself, so a
    caller that needs a bare `Settings` for something else (a test, a one-off script reading only
    `database_url`) is not forced to supply a Fernet key it will never use -- only the real
    process entrypoints, which all resolve their settings through `get_settings()`, are stopped
    from starting without one."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if not settings.rhapto_secret_key:
        raise MissingSecretKeyError(
            "RHAPTO_SECRET_KEY is not set. Rhapto refuses to start without it -- generate one "
            'with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())" and set it in your environment or .env file.'
        )
    return settings
