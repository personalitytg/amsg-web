from typing import Any

from pydantic import BaseModel


class SeriesPoint(BaseModel):
    t: str  # ISO timestamp
    v: float | None


class SeriesPayload(BaseModel):
    source_id: str
    domain: str
    label: str
    points: list[SeriesPoint]


class EventEdge(BaseModel):
    a: str
    b: str
    nms: float
    p_value: float
    novelty: int


class AnomalyEvent(BaseModel):
    event_id: str
    start: str
    end: str
    best_p_value: float
    q_value: float | None
    best_nms: float
    edge_novelty_sum: float
    edges_count: int
    sources: list[str]
    domains: list[str]
    cross_domain_edges_count: int
    top_edges: list[EventEdge]
    is_holdout: bool


class HeatmapCell(BaseModel):
    a: str
    b: str
    score: float


class PValueBucket(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class AnalysisSummary(BaseModel):
    total_events: int
    significant_events: int
    p_value_min: float | None
    p_value_max: float | None
    sources_count: int
    duration_seconds: float


class AnalysisResult(BaseModel):
    job_id: str
    summary: AnalysisSummary
    series: list[SeriesPayload]
    events: list[AnomalyEvent]
    heatmap: list[HeatmapCell]
    p_value_histogram: list[PValueBucket]
    config_echo: dict[str, Any]
