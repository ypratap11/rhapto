from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.schemas import TaxonomySuggestionOut
from rhapto.db.repositories import documents as documents_repo
from rhapto.models.source_document import SourceDocument
from rhapto.models.taxonomy import TaxonomyFile
from rhapto.services.taxonomy import normalise, roles_by_name, taxonomy

router = APIRouter(prefix="/taxonomy")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: The picker shows these as one-tap chips above the field list; more than a handful is noise.
MAX_SUGGESTIONS = 6


@router.get("", response_model=TaxonomyFile)
async def get_taxonomy(user_id: UserDep) -> TaxonomyFile:
    """The whole field -> role tree. Static data, but behind auth like every other route."""
    return taxonomy()


@router.get("/suggestions", response_model=list[TaxonomySuggestionOut])
async def suggestions(user_id: UserDep, session: SessionDep) -> list[TaxonomySuggestionOut]:
    """Roles whose name appears in one of the uploaded resume's entry titles.

    Matching is deliberately blunt -- normalised containment in either direction -- because entry
    titles carry seniority and team ("Senior Technical Program Manager, Platform"). Anything
    cleverer would need the LLM, and this has to answer while the picker is opening.
    """
    row = await documents_repo.get_document(session, user_id)
    if row is None:
        return []
    document = SourceDocument.model_validate(row.parsed_json)
    lookup = roles_by_name()  # longest role name first, so the specific match wins
    out: list[TaxonomySuggestionOut] = []
    seen: set[tuple[str, str]] = set()
    for paragraph in document.paragraphs:
        if paragraph.role != "entry_title":
            continue
        title = normalise(paragraph.text)
        if not title:
            continue
        for role_name, (field, role) in lookup.items():
            if role_name not in title and title not in role_name:
                continue
            key = (field.id, role.id)
            if key not in seen:
                seen.add(key)
                out.append(
                    TaxonomySuggestionOut(
                        field_id=field.id,
                        field_name=field.name,
                        role_id=role.id,
                        role_name=role.name,
                        matched_title=paragraph.text,
                    )
                )
            break  # one role per title
        if len(out) >= MAX_SUGGESTIONS:
            break
    return out
