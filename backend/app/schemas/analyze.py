from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeSettings(BaseModel):
    """Knobs exposed in the UI form. Kept narrow on purpose."""

    window_sizes: list[int] = Field(default_factory=lambda: [64, 128, 256])
    step_size: int = 16
    bins: int = 8
    top_p: float = Field(default=0.05, ge=0.001, le=0.5)
    shift_d: int = Field(default=3, ge=0, le=20)
    null_shifts_count: int = Field(default=50, ge=10, le=2000)
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0, description="FDR target")
    holdout_ratio: float = Field(default=0.0, ge=0.0, lt=0.5)
    min_pair_valid_fraction: float = 0.9
    seed: int = 42


class AnalyzeRequest(BaseModel):
    source_ids: list[str] = Field(min_length=1)
    start: date
    end: date
    settings: AnalyzeSettings = Field(default_factory=AnalyzeSettings)
    label: str | None = None


class AnalyzeAccepted(BaseModel):
    job_id: str
    status: Literal["pending", "running"] = "pending"
