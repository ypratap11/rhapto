"""The one place that turns a composed package into a stored package row plus its DOCX file.

Both the worker's `tailor_job` and the API's `PATCH /packages/{id}` go through here, so the
version assignment, the commit-before-file-IO ordering and the `docx_path` back-fill cannot
drift apart between the two call sites.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, Package
from rhapto.db.repositories import packages as package_repo
from rhapto.models.package import ApplicationPackage
from rhapto.services.storage import PackageStorage


async def persist_package(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    job: Job,
    package: ApplicationPackage,
    selection_block_ids: list[str],
    parent_package_id: uuid.UUID | None,
    storage: PackageStorage,
    docx: bytes,
) -> Package:
    """Create the next version of `job`'s package and write its DOCX.

    The row is committed before any file is touched, so no transaction is held open across
    blocking file IO, and `docx_path` is back-filled in a second commit. An empty `docx`
    (the renderer refused the resume) leaves `docx_path` NULL, which `has_docx: false`
    reports faithfully.
    """
    version = await package_repo.next_version(session, job.id)
    row = await package_repo.create_package(
        session,
        user_id,
        job.id,
        package.model_copy(update={"version": version}),
        selection_block_ids=list(selection_block_ids),
        parent_package_id=parent_package_id,
        docx_path=None,
        pdf_path=None,
    )
    await session.commit()

    if docx:
        path = await asyncio.to_thread(storage.write_docx, str(row.id), docx)
        row.docx_path = str(path)
        await session.commit()
    return row
