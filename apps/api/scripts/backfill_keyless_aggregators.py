"""One-time backfill: give existing accounts the keyless `aggregators` rows new accounts now get.

WHY THIS EXISTS. `poller.build_specs` builds its work list only from `aggregators` rows that exist and
are enabled, so an account with no rows polls no aggregators. `GET /settings/sources` used to display a
keyless source as enabled anyway, so the account looked configured and fetched from nothing. This was
live: on this instance the owner's account has rows and polls fine, while the second real account had
zero rows and had been polling no aggregators at all.

`services.accounts.ensure_account` now seeds those rows at account creation, which fixes every account
created from that point on. It does nothing for accounts that already exist. That is what this script
is for, and it is the reason it is a script rather than a migration: the fix belongs to accounts, not
to the schema, and a migration cannot be dry-run against production and read before it commits.

WHAT IT DOES. For every user, insert an enabled row for each keyless aggregator source it does not
already have. It calls the same `seed_keyless_aggregators` the account path uses, so there is one
definition of "what a seeded account looks like" and this cannot drift from it.

WHAT IT DOES NOT DO. It never changes a row that already exists, so a source someone deliberately
switched off stays off (`ON CONFLICT DO NOTHING` on `(user_id, source)`). It never touches keyed
sources -- those need credentials and enabling them would only produce failing polls. It writes nothing
at all without `--commit`.

USAGE. Dry run first, always -- it reports exactly what it would insert and exits without writing:

    cd apps/api
    uv run python scripts/backfill_keyless_aggregators.py --database-url postgresql+asyncpg://...

Then, only once the dry-run output is what you expect:

    uv run python scripts/backfill_keyless_aggregators.py --database-url ... --commit

The default `--database-url` is deliberately a LOCAL one and there is no environment-variable
fallback: a production URL has to be typed on the command line, by a human, every time. Per CLAUDE.md,
production is the owner's call and nothing here runs against it unasked.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Aggregator, User
from rhapto.db.repositories.profile import seed_keyless_aggregators
from rhapto.db.session import make_engine, make_session_factory
from rhapto.services.discovery.sources.status import keyless_source_names

#: A local database, on purpose. See the module docstring.
DEFAULT_DATABASE_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto"


@dataclass(frozen=True)
class Plan:
    """What one account is missing."""

    user_id: uuid.UUID
    email: str
    missing: tuple[str, ...]


async def plan_backfill(session: AsyncSession, keyless: tuple[str, ...]) -> list[Plan]:
    """Which accounts are missing which keyless sources. Reads only.

    Two statements for the whole instance rather than one per account: this runs against a live
    database and a per-user loop would be both slower and harder to read in the dry-run output.
    """
    users = list(await session.execute(select(User.id, User.email).order_by(User.created_at)))
    existing: dict[uuid.UUID, set[str]] = {}
    for user_id, source in await session.execute(select(Aggregator.user_id, Aggregator.source)):
        existing.setdefault(user_id, set()).add(source)
    plans = []
    for user_id, email in users:
        missing = tuple(s for s in keyless if s not in existing.get(user_id, set()))
        if missing:
            plans.append(Plan(user_id=user_id, email=email, missing=missing))
    return plans


def redact(email: str) -> str:
    """`a***@example.com`. The output of a production script lands in a terminal, a scrollback and
    possibly a paste; the local part is not needed to tell two accounts apart."""
    local, _, domain = email.partition("@")
    head = local[:1] if local else ""
    return f"{head}***@{domain}" if domain else f"{head}***"


async def run(database_url: str, *, commit: bool) -> int:
    keyless = keyless_source_names()
    engine = make_engine(database_url)
    try:
        async with make_session_factory(engine)() as session:
            plans = await plan_backfill(session, keyless)
            print(f"keyless sources: {', '.join(keyless)}")
            if not plans:
                print("nothing to do: every account already has a row for every keyless source")
                return 0
            print(f"{len(plans)} account(s) would be changed:")
            for plan in plans:
                print(f"  {redact(plan.email)}  +{len(plan.missing)}: {', '.join(plan.missing)}")
            total = sum(len(p.missing) for p in plans)
            if not commit:
                # The whole point of the default. Nothing was written, and the session is discarded
                # without a commit below.
                print(
                    f"\nDRY RUN: {total} row(s) would be inserted. Re-run with --commit to apply."
                )
                return 0
            inserted = 0
            for plan in plans:
                # The same function the account-creation path calls, so this cannot seed a different
                # shape of row from the one new accounts get.
                inserted += await seed_keyless_aggregators(
                    session, plan.user_id, keyless_sources=plan.missing
                )
            await session.commit()
            print(f"\ninserted {inserted} row(s) across {len(plans)} account(s)")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill enabled aggregators rows for keyless sources on existing accounts."
    )
    parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help=f"SQLAlchemy async URL. Defaults to the local dev database ({DEFAULT_DATABASE_URL}).",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually insert. Without this the script reports what it would do and writes nothing.",
    )
    args = parser.parse_args()
    return asyncio.run(run(str(args.database_url), commit=bool(args.commit)))


if __name__ == "__main__":
    raise SystemExit(main())
