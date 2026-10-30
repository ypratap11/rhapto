"""Meter every model call billed to the deployment's own key into the `free_spend` ledger.

A wrapper around an `LLMProvider`, applied where a run resolves its provider, so every call a free
account makes is recorded whichever pipeline step made it. It logs the user id and nothing else: no
email, no key, no prompt text.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.config import Settings
from rhapto.db.repositories.free_spend import record_free_spend
from rhapto.engine.providers.llm import (
    LLMProvider,
    MalformedOutputError,
    Message,
    StructuredResult,
    SystemBlock,
    T,
    TokenUsage,
)
from rhapto.services.llm import env_llm_config
from rhapto.services.pricing import conservative_cost
from rhapto.services.trial import free_budget_applies, on_deployment_key

logger = logging.getLogger(__name__)


class MeteredLLM:
    """Delegates to `inner` and writes one ledger row per billed call.

    Each row is written on its own session and committed at once, so a run that fails later keeps
    the record of the calls it already made. A ledger failure is logged and swallowed: the model
    result is already paid for and must still be returned.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        model: str,
        user_id: uuid.UUID,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._inner = inner
        # The pipeline reads this into `packages.llm_model`.
        self.model = model
        self._user_id = user_id
        self._session_factory = session_factory

    async def _record(self, usage: TokenUsage) -> None:
        try:
            async with self._session_factory() as session:
                await record_free_spend(
                    session,
                    user_id=self._user_id,
                    model=self.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_input_tokens,
                    cache_creation_tokens=usage.cache_creation_input_tokens,
                    cost_usd=conservative_cost(self.model, usage),
                )
                await session.commit()
        except Exception as exc:
            # Class name only: the message can carry SQL or bound parameters.
            logger.error(
                "free-spend ledger write failed for user %s: %s",
                self._user_id,
                type(exc).__name__,
            )

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        try:
            result = await self._inner.complete_structured(
                system=system,
                messages=messages,
                output_schema=output_schema,
                max_tokens=max_tokens,
            )
        except MalformedOutputError as exc:
            if exc.usage is not None:
                await self._record(exc.usage)
            raise
        await self._record(result.usage)
        return result


async def meter_if_free(
    llm: LLMProvider,
    session: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> LLMProvider:
    """Wrap `llm` when this user's calls are billed to the deployment's key, else return it as is."""
    if not free_budget_applies(settings) or not await on_deployment_key(session, settings, user_id):
        return llm
    env = env_llm_config(settings)
    model = getattr(llm, "model", None) or (env.model if env is not None else "")
    return MeteredLLM(llm, model=model, user_id=user_id, session_factory=session_factory)
