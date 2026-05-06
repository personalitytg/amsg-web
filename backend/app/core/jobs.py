"""In-process job manager for long-running analyses.

For a portfolio project this is intentionally simple: a thread pool plus an
in-memory dict with TTL eviction. For production swap with Redis + RQ/Celery.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class JobProgress:
    stage: str
    percent: float
    message: str = ""


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.PENDING
    progress: JobProgress = field(default_factory=lambda: JobProgress("queued", 0.0))
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _events: asyncio.Queue[JobProgress] = field(default_factory=asyncio.Queue)

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "progress": {
                "stage": self.progress.stage,
                "percent": self.progress.percent,
                "message": self.progress.message,
            },
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


JobRunner = Callable[["JobHandle"], Awaitable[dict[str, Any]]]


class JobHandle:
    """Passed to runners so they can report progress without touching the manager."""

    def __init__(self, job: Job) -> None:
        self._job = job

    @property
    def id(self) -> str:
        return self._job.id

    async def report(self, stage: str, percent: float, message: str = "") -> None:
        self._job.progress = JobProgress(stage=stage, percent=percent, message=message)
        await self._job._events.put(self._job.progress)


class JobManager:
    def __init__(self, ttl_seconds: int = 3600, max_concurrent: int = 2) -> None:
        self._jobs: dict[str, Job] = {}
        self._ttl = ttl_seconds
        self._sem = asyncio.Semaphore(max_concurrent)

    def create(self) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id)
        self._jobs[job_id] = job
        self._evict_expired()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def run(self, job: Job, runner: JobRunner) -> None:
        async with self._sem:
            job.status = JobStatus.RUNNING
            handle = JobHandle(job)
            try:
                result = await runner(handle)
                job.result = result
                job.status = JobStatus.SUCCEEDED
                await handle.report("done", 100.0, "Analysis completed")
            except Exception as exc:  # noqa: BLE001 - we want to surface the message
                job.error = f"{type(exc).__name__}: {exc}"
                job.status = JobStatus.FAILED
                await handle.report("error", 100.0, job.error)
            finally:
                job.finished_at = time.time()
                # close the queue with a sentinel so SSE consumers can exit
                await job._events.put(JobProgress("__end__", 100.0, ""))

    async def stream_progress(self, job: Job) -> AsyncIterator[JobProgress]:
        # emit current state first
        yield job.progress
        while True:
            event = await job._events.get()
            if event.stage == "__end__":
                return
            yield event

    def _evict_expired(self) -> None:
        cutoff = time.time() - self._ttl
        expired = [
            jid for jid, job in self._jobs.items()
            if job.finished_at is not None and job.finished_at < cutoff
        ]
        for jid in expired:
            self._jobs.pop(jid, None)


_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        from .config import get_settings
        s = get_settings()
        _manager = JobManager(ttl_seconds=s.job_ttl_seconds, max_concurrent=s.max_concurrent_jobs)
    return _manager
