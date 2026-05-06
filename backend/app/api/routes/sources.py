from fastapi import APIRouter

from app.services.source_registry import list_sources

router = APIRouter()


@router.get("/sources")
def get_sources() -> dict[str, list]:
    return {"sources": [s.model_dump() for s in list_sources()]}
