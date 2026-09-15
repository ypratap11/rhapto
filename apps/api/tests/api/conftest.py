from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.app import create_app
from rhapto.api.deps import AppState, LlmFactory
from rhapto.config import Settings
from rhapto.db.repositories.users import get_or_create_user
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.providers.registry import build_llm
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.enqueue import InlineEnqueuer
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.services.jobtext import JobTextError
from rhapto.services.profile_sync import import_profile_dir
from rhapto.services.storage import PackageStorage
from rhapto.worker.tasks import TASKS as TASK_REGISTRY

TOKEN = "test-token"


class ScriptableLLM(FakeLLMProvider):
    """FakeLLMProvider whose queue can be extended after construction."""

    def __init__(self) -> None:
        super().__init__(responses=[])

    def script(self, *responses: BaseModel | dict[str, Any]) -> None:
        self._queue.extend(responses)


@pytest.fixture
def fake_llm() -> ScriptableLLM:
    return ScriptableLLM()


class RecordingResolver:
    """Stands in for `services.llm.resolve_llm` in the worker ctx and records who it resolved for."""

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm
        self.calls: list[uuid.UUID] = []

    async def __call__(
        self, session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LLMProvider:
        self.calls.append(user_id)
        return self.llm


@pytest.fixture
def llm_resolver(fake_llm: ScriptableLLM) -> RecordingResolver:
    return RecordingResolver(fake_llm)


@pytest.fixture
def llm_factory() -> LlmFactory:
    """The adapter builder the `POST /settings/llm/test` endpoint uses; overridden in tests that
    must not reach a real provider."""
    return build_llm


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def storage(tmp_path: Path) -> PackageStorage:
    return PackageStorage(tmp_path / "packages")


@pytest.fixture
def fetched_text() -> dict[str, str]:
    return {}


@pytest.fixture
def fake_fetch(fetched_text: dict[str, str]) -> Callable[[str], Awaitable[str]]:
    async def fetch(url: str) -> str:
        if "text" not in fetched_text:
            raise JobTextError("fetch failed with HTTP 404")
        return fetched_text["text"]

    return fetch


@pytest.fixture
def env_llm_key(request: pytest.FixtureRequest) -> str:
    """The provider key the environment offers. Override it (or parametrize indirectly) with "" to
    exercise the paths where no LLM is configured anywhere."""
    return str(getattr(request, "param", "test"))


@pytest.fixture
def api_settings(tmp_path: Path, env_llm_key: str) -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key=env_llm_key,
        rhapto_api_token=TOKEN,
        rhapto_user_email="test@example.com",
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
    )


@pytest.fixture
def worker_ctx(
    session_factory: async_sessionmaker[AsyncSession],
    llm_resolver: RecordingResolver,
    event_bus: InMemoryEventBus,
    storage: PackageStorage,
    api_settings: Settings,
) -> dict[str, Any]:
    return {
        "session_factory": session_factory,
        "llm_resolver": llm_resolver,
        "embedder": FakeEmbeddingProvider(dimensions=384),
        "event_bus": event_bus,
        "storage": storage,
        "soffice_binary": api_settings.rhapto_soffice_binary,
        "discovery_http": FakeDiscoveryHttp({}),
    }


@pytest.fixture
def enqueuer(worker_ctx: dict[str, Any]) -> InlineEnqueuer:
    return InlineEnqueuer(TASK_REGISTRY, worker_ctx)


@pytest.fixture
async def app(
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    enqueuer: InlineEnqueuer,
    event_bus: InMemoryEventBus,
    storage: PackageStorage,
    fake_fetch: Callable[[str], Awaitable[str]],
    llm_factory: LlmFactory,
) -> AsyncIterator[FastAPI]:
    application = create_app(
        api_settings,
        session_factory=session_factory,
        enqueuer=enqueuer,
        event_bus=event_bus,
        storage=storage,
        fetch_text=fake_fetch,
        llm_factory=llm_factory,
        discovery_http=FakeDiscoveryHttp({}),
    )
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as c:
        yield c


@pytest.fixture
async def anon_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def user_id(app: FastAPI) -> uuid.UUID:
    state: AppState = app.state.rhapto
    assert state.user_id is not None
    return state.user_id


@pytest.fixture
async def imported_profile(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, demo_profile_dir: Path
) -> None:
    async with session_factory() as session:
        await get_or_create_user(session, "test@example.com")
        await import_profile_dir(session, user_id, demo_profile_dir)
        await session.commit()
