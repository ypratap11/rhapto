"""ArqEnqueuer against a real Redis. Skipped (with a message) when Redis is unreachable."""

import uuid
from collections.abc import AsyncIterator

import pytest
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus

from rhapto.services.enqueue import ArqEnqueuer

ARQ_QUEUE = "arq:queue"


@pytest.fixture
async def arq_pool(test_redis_url: str) -> AsyncIterator[ArqRedis]:
    pool = await create_pool(RedisSettings.from_dsn(test_redis_url))
    try:
        yield pool
    finally:
        await pool.aclose()


async def _cleanup(pool: ArqRedis, job_ids: list[str]) -> None:
    for job_id in job_ids:
        await pool.zrem(ARQ_QUEUE, job_id)
        await pool.delete(f"arq:job:{job_id}", f"arq:result:{job_id}")


async def test_enqueue_puts_a_job_on_the_arq_queue(test_redis_url: str, arq_pool: ArqRedis) -> None:
    enqueuer = ArqEnqueuer(test_redis_url)
    job_id = f"rhapto-test-{uuid.uuid4()}"
    try:
        before = await arq_pool.zcard(ARQ_QUEUE)
        await enqueuer.enqueue("noop", _job_id=job_id, x=1)
        assert await arq_pool.zcard(ARQ_QUEUE) == before + 1

        # No worker is running, so the job stays queued with its arguments intact.
        job = Job(job_id, arq_pool)
        assert await job.status() in {JobStatus.queued, JobStatus.deferred}
        info = await job.info()
        assert info is not None and info.function == "noop" and info.kwargs == {"x": 1}
    finally:
        await enqueuer.close()
        await _cleanup(arq_pool, [job_id])


async def test_enqueue_connects_once_and_close_releases_the_pool(
    test_redis_url: str, arq_pool: ArqRedis
) -> None:
    enqueuer = ArqEnqueuer(test_redis_url)
    job_ids = [f"rhapto-test-{uuid.uuid4()}" for _ in range(2)]
    try:
        await enqueuer.enqueue("noop", _job_id=job_ids[0])
        first_pool = enqueuer._pool
        await enqueuer.enqueue("noop", _job_id=job_ids[1])
        assert first_pool is not None and enqueuer._pool is first_pool
    finally:
        await enqueuer.close()
        await _cleanup(arq_pool, job_ids)
    assert enqueuer._pool is None
