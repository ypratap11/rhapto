"""Encrypted per-source credentials.

The `Fernet` is a parameter, not an import: `db` is forbidden from importing `config` and
`services` (see .importlinter), so the API and worker pass `services.secrets.fernet_for(settings)`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, cast

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import SourceCredentialRow


async def get_credentials(
    session: AsyncSession, fernet: Fernet, user_id: uuid.UUID, source: str
) -> dict[str, str]:
    """The stored values, or `{}` when there is no row or it cannot be read.

    An unreadable row means the deployment's secret changed; returning `{}` makes the source
    report "check the API key", which is the action the user can actually take.
    """
    row = await session.scalar(
        select(SourceCredentialRow).where(
            SourceCredentialRow.user_id == user_id, SourceCredentialRow.source == source
        )
    )
    if row is None:
        return {}
    try:
        data = json.loads(fernet.decrypt(row.credentials_encrypted.encode()).decode())
    except (InvalidToken, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


async def put_credentials(
    session: AsyncSession,
    fernet: Fernet,
    user_id: uuid.UUID,
    source: str,
    values: dict[str, str],
) -> None:
    """Merge `values` into the stored object: an omitted field keeps what is already there."""
    merged = {**await get_credentials(session, fernet, user_id, source), **values}
    merged = {k: v for k, v in merged.items() if v}
    token = fernet.encrypt(json.dumps(merged, sort_keys=True).encode()).decode()
    row = await session.scalar(
        select(SourceCredentialRow).where(
            SourceCredentialRow.user_id == user_id, SourceCredentialRow.source == source
        )
    )
    if row is None:
        session.add(
            SourceCredentialRow(user_id=user_id, source=source, credentials_encrypted=token)
        )
    else:
        row.credentials_encrypted = token
    await session.flush()


async def delete_credentials(session: AsyncSession, user_id: uuid.UUID, source: str) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(SourceCredentialRow).where(
                SourceCredentialRow.user_id == user_id, SourceCredentialRow.source == source
            )
        ),
    )
    return bool(result.rowcount)


async def credentialled_sources(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """Which sources have a stored row at all (what the Settings UI shows as "key set")."""
    return set(
        await session.scalars(
            select(SourceCredentialRow.source).where(SourceCredentialRow.user_id == user_id)
        )
    )
