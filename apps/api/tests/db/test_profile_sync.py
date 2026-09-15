from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import profile as repo
from rhapto.engine.types import ProfileError
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.profile.loader import load_profile
from rhapto.services.profile_sync import (
    export_profile_dir,
    import_profile_dir,
    load_profile_from_db,
    replace_profile_in_db,
)


async def test_import_then_load_round_trips(
    session: AsyncSession, user: User, demo_profile_dir: Path
) -> None:
    imported = await import_profile_dir(session, user.id, demo_profile_dir)
    await session.commit()
    loaded = await load_profile_from_db(session, user.id)
    assert loaded == imported
    assert {b.id for b in loaded.blocks} == {
        "acme-data-pm",
        "acme-migration",
        "side-llm-tool",
        "cred-pmp",
    }
    assert loaded.answers["name"] == "Maya Chen"
    assert [t.id for t in loaded.tracks] == ["data-pm", "ai-pm"]
    assert {b.id for b in loaded.bases} == {"data-pm", "ai-pm"}


async def test_export_writes_yaml_equal_to_db(
    session: AsyncSession, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:
    await import_profile_dir(session, user.id, demo_profile_dir)
    await session.commit()
    exported = await export_profile_dir(session, user.id, tmp_path)
    assert load_profile(tmp_path) == exported


async def test_replace_is_destructive(
    session: AsyncSession, user: User, demo_profile_dir: Path
) -> None:
    await import_profile_dir(session, user.id, demo_profile_dir)
    await session.commit()
    profile = await load_profile_from_db(session, user.id)
    smaller = profile.model_copy(
        update={"blocks": profile.blocks[:1], "bases": [], "tracks": profile.tracks[:1]}
    )
    smaller = smaller.model_copy(
        update={
            "bases": [profile.bases[0].model_copy(update={"block_ids": [profile.blocks[0].id]})]
        }
    )
    await replace_profile_in_db(session, user.id, smaller)
    await session.commit()
    assert len(await repo.list_blocks(session, user.id)) == 1


async def test_load_without_blocks_raises(session: AsyncSession, user: User) -> None:
    with pytest.raises(ProfileError, match="no blocks"):
        await load_profile_from_db(session, user.id)


async def test_import_with_unknown_taxonomy_field_raises(
    session: AsyncSession, user: User, tmp_path: Path
) -> None:
    (tmp_path / "blocks.yaml").write_text(
        "blocks:\n  - id: a\n    type: role\n    content: one\n", encoding="utf-8"
    )
    (tmp_path / "tracks.yaml").write_text(
        "tracks:\n  - id: t1\n    name: T\n    resume_base: b\n    field: not-a-real-field\n",
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="not-a-real-field"):
        await import_profile_dir(session, user.id, tmp_path)
    # a failed import must not have written anything
    assert await repo.list_blocks(session, user.id) == []


async def test_upsert_block_updates_in_place(session: AsyncSession, user: User) -> None:
    await repo.upsert_block(session, user.id, Block(id="a", type="role", content="one"))
    await repo.upsert_block(
        session,
        user.id,
        Block(id="a", type="role", content="two", visibility=Visibility(exclude_when=["x"])),
    )
    await session.commit()
    rows = await repo.list_blocks(session, user.id)
    assert len(rows) == 1 and rows[0].content == "two" and rows[0].exclude_when == ["x"]
    assert await repo.delete_block(session, user.id, "a") is True
    assert await repo.delete_block(session, user.id, "a") is False


async def test_profile_rows_are_user_scoped(session: AsyncSession, user: User) -> None:
    from rhapto.db.repositories.users import get_or_create_user

    other = await get_or_create_user(session, "other@example.com")
    await repo.upsert_block(session, user.id, Block(id="a", type="role", content="mine"))
    await repo.upsert_block(session, other.id, Block(id="a", type="role", content="theirs"))
    await session.commit()
    assert [b.content for b in await repo.list_blocks(session, user.id)] == ["mine"]


async def test_order_is_explicit_not_timestamp_based(session: AsyncSession, user: User) -> None:
    await repo.upsert_block(
        session, user.id, Block(id="zeta", type="role", content="z"), position=0
    )
    await repo.upsert_block(
        session, user.id, Block(id="alpha", type="role", content="a"), position=1
    )
    await session.commit()
    assert [b.block_id for b in await repo.list_blocks(session, user.id)] == ["zeta", "alpha"]
    await repo.upsert_block(session, user.id, Block(id="mid", type="role", content="m"))  # appended
    await session.commit()
    assert [b.block_id for b in await repo.list_blocks(session, user.id)] == [
        "zeta",
        "alpha",
        "mid",
    ]
