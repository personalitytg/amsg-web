from pydantic import BaseModel


class SourceParam(BaseModel):
    name: str
    label: str
    description: str
    default: str | int | float | bool | None = None


class SourceMeta(BaseModel):
    id: str
    label: str
    domain: str
    description: str
    cadence: str
    requires_internet: bool
    extra_params: list[SourceParam] = []


class SourceListResponse(BaseModel):
    sources: list[SourceMeta]
