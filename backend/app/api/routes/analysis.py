from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.core.jobs import JobStatus, get_job_manager

router = APIRouter()


@router.get("/analysis/{job_id}")
def get_analysis(job_id: str) -> JSONResponse:
    job = get_job_manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = job.to_public()
    if job.status == JobStatus.SUCCEEDED:
        payload["result"] = job.result
    return JSONResponse(payload)


@router.get("/analysis/{job_id}/progress")
async def stream_progress(job_id: str) -> EventSourceResponse:
    job = get_job_manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    manager = get_job_manager()

    async def _gen():
        async for evt in manager.stream_progress(job):
            yield {
                "event": "progress",
                "data": {
                    "stage": evt.stage,
                    "percent": evt.percent,
                    "message": evt.message,
                    "status": job.status.value,
                },
            }
        yield {
            "event": "done",
            "data": {"status": job.status.value, "error": job.error},
        }

    return EventSourceResponse(_gen())
