"""The one-row-per-user `llm_settings` table and the stored-config read path."""

import base64
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.config import Settings
from rhapto.db.models import LlmSettingsRow, User
from rhapto.db.repositories.llm_settings import (
    delete_llm_settings,
    get_llm_settings,
    upsert_llm_settings,
)
from rhapto.services.llm import stored_llm_config
from rhapto.services.secrets import encrypt

SECRET = base64.urlsafe_b64encode(b"s" * 32).decode()


def _settings() -> Settings:
    return Settings(_env_file=None, rhapto_secret_key=SECRET)


async def test_get_returns_none_before_anything_is_stored(
    session: AsyncSession, user: User
) -> None:
    assert await get_llm_settings(session, user.id) is None


async def test_upsert_twice_updates_the_single_row(session: AsyncSession, user: User) -> None:
    first = await upsert_llm_settings(
        session, user.id, provider="anthropic", model="claude-sonnet-5", api_key_encrypted="enc-1"
    )
    await session.commit()
    second = await upsert_llm_settings(
        session, user.id, provider="openai", model="gpt-5", api_key_encrypted="enc-2"
    )
    await session.commit()
    assert second.id == first.id
    rows = (await session.scalars(select(LlmSettingsRow))).all()
    assert len(rows) == 1
    assert rows[0].provider == "openai" and rows[0].model == "gpt-5"
    assert rows[0].api_key_encrypted == "enc-2"
    assert rows[0].created_at is not None and rows[0].updated_at is not None


async def test_delete_returns_true_then_false(session: AsyncSession, user: User) -> None:
    await upsert_llm_settings(
        session, user.id, provider="gemini", model="gemini-2.5-pro", api_key_encrypted="enc"
    )
    await session.commit()
    assert await delete_llm_settings(session, user.id) is True
    await session.commit()
    assert await get_llm_settings(session, user.id) is None
    assert await delete_llm_settings(session, user.id) is False


async def test_user_id_is_unique(session: AsyncSession, user: User) -> None:
    session.add(
        LlmSettingsRow(
            user_id=user.id, provider="anthropic", model="claude-sonnet-5", api_key_encrypted="a"
        )
    )
    session.add(
        LlmSettingsRow(user_id=user.id, provider="openai", model="gpt-5", api_key_encrypted="b")
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()  # leave the session usable for the truncating teardown


async def test_stored_llm_config_decrypts_the_stored_key(session: AsyncSession, user: User) -> None:
    settings = _settings()
    await upsert_llm_settings(
        session,
        user.id,
        provider="openai",
        model="gpt-5-mini",
        api_key_encrypted=encrypt(settings, "sk-test-stored"),
    )
    await session.commit()
    config = await stored_llm_config(session, settings, user.id)
    assert config is not None
    assert config.provider == "openai" and config.model == "gpt-5-mini"
    assert config.api_key == "sk-test-stored" and config.source == "settings"


async def test_stored_llm_config_is_none_without_a_row(session: AsyncSession, user: User) -> None:
    assert await stored_llm_config(session, _settings(), uuid.uuid4()) is None
    assert await stored_llm_config(session, _settings(), user.id) is None
