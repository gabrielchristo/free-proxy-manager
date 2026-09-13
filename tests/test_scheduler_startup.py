from unittest.mock import AsyncMock, patch

import pytest

from app.config import get_settings
from app.jobs.scheduler import JobScheduler


@pytest.mark.asyncio
async def test_initial_cycle_skips_collector_when_disabled():
    settings = get_settings().model_copy(update={"collector_run_on_startup": False})
    scheduler = JobScheduler()
    scheduler.settings = settings
    scheduler.collector_job = AsyncMock()
    scheduler.checker_job = AsyncMock()
    scheduler.checker_job.refill_queue = AsyncMock(return_value=0)

    await scheduler._run_initial_cycle()

    scheduler.collector_job.run.assert_not_called()
    scheduler.checker_job.refill_queue.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_cycle_runs_collector_by_default():
    settings = get_settings().model_copy(update={"collector_run_on_startup": True})
    scheduler = JobScheduler()
    scheduler.settings = settings
    scheduler.collector_job = AsyncMock()
    scheduler.checker_job = AsyncMock()
    scheduler.checker_job.refill_queue = AsyncMock(return_value=0)

    await scheduler._run_initial_cycle()

    scheduler.collector_job.run.assert_awaited_once()
    scheduler.checker_job.refill_queue.assert_awaited_once()
