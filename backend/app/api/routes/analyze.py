import asyncio

from fastapi import APIRouter, HTTPException

from app.core.jobs import get_job_manager
from app.schemas.analyze import AnalyzeAccepted, AnalyzeRequest
from app.services.pipeline_runner import run_analysis
from app.services.source_registry import is_available

router = APIRouter()

# Hold strong refs to background tasks so the event loop does not GC them mid-flight.
_running: set[asyncio.Task] = set()


@router.post("/analyze", response_model=AnalyzeAccepted, status_code=202)
async def analyze(req: AnalyzeRequest) -> AnalyzeAccepted:
    invalid = [sid for sid in req.source_ids if not is_available(sid)]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Sources not available in web flow: {', '.join(invalid)}",
        )
    if req.end <= req.start:
        raise HTTPException(status_code=400, detail="end must be after start")

    manager = get_job_manager()
    job = manager.create()

    async def _runner(handle):
        return await run_analysis(handle, req)

    task = asyncio.create_task(manager.run(job, _runner))
    _running.add(task)
    task.add_done_callback(_running.discard)

    return AnalyzeAccepted(job_id=job.id, status="pending")
