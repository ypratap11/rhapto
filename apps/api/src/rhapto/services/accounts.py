"""Bringing an account into existence, in one place.

Creating the `users` row is not by itself enough to give someone a working account: the poller builds
its work list only from `aggregators` rows that exist and are enabled, so an account with no rows
fetches from nothing. That was live -- this instance's second real account had zero rows and had been
polling no aggregators at all, while Settings showed four keyless sources switched on.

`ensure_account` is the one function every account-creation path calls, so seeding cannot be forgotten
by one of them. It is the layer that may import both `db.repositories` and
`services.discovery.sources`, which is why it lives here rather than in the repository.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories.profile import seed_keyless_aggregators
from rhapto.db.repositories.users import get_or_create_user
from rhapto.services.discovery.sources.status import keyless_source_names


async def ensure_account(session: AsyncSession, email: str) -> User:
    """The user row for `email`, created and seeded if it did not exist. Does not commit.

    Both halves are idempotent -- `get_or_create_user` uses `ON CONFLICT DO NOTHING` on `users.email`
    and `seed_keyless_aggregators` on `(user_id, source)` -- so calling this on every sign-in is safe,
    which matters because that is exactly what the access-mode dependency does. Re-running it never
    re-enables a source the user has since switched off: the row already exists, so nothing is written.

    The caller commits. Every existing call site already did, and the seed has to land in the same
    transaction as the account row: a committed account with no sources is the state this function
    exists to prevent.

    Seeding only helps accounts created from here on. An account that predates it needs the one-time
    backfill in `scripts/backfill_keyless_aggregators.py`.
    """
    user = await get_or_create_user(session, email)
    await seed_keyless_aggregators(session, user.id, keyless_sources=keyless_source_names())
    return user
