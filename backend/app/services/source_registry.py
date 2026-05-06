"""Curated list of sources exposed by the web UI.

`status` is what the frontend uses to enable/disable the option:
- `available` — wired to a connector and runnable from the UI
- `coming_soon` — present in amsg pipeline but not yet adapted to the web flow
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.sources import SourceMeta as BaseSourceMeta
from app.schemas.sources import SourceParam


class SourceMeta(BaseSourceMeta):
    status: Literal["available", "coming_soon"] = "available"


class SourceListEnvelope(BaseModel):
    sources: list[SourceMeta]


SOURCES: list[SourceMeta] = [
    SourceMeta(
        id="demo",
        label="Synthetic demo",
        domain="synthetic",
        description="Three synthetic series with a shared hidden pattern. Offline, ~1s.",
        cadence="1s",
        requires_internet=False,
        status="available",
    ),
    SourceMeta(
        id="omni",
        label="NASA OMNI (1-min)",
        domain="space_weather",
        description="Solar wind plasma + IMF (BZ_GSM, flow_speed, proton_density, SYM-H) from CDAWeb HAPI.",
        cadence="1min",
        requires_internet=True,
        status="available",
    ),
    SourceMeta(
        id="swpc",
        label="NOAA SWPC",
        domain="space_weather",
        description="Solar wind magnetometer (Bz, Bt) and GOES X-ray flux. 7-day window.",
        cadence="1min",
        requires_internet=True,
        status="available",
    ),
    SourceMeta(
        id="nmdb",
        label="NMDB neutron monitors",
        domain="cosmic_ray",
        description="Neutron monitor counts from NMDB NEST (OULU, JUNG).",
        cadence="10min",
        requires_internet=True,
        status="coming_soon",
        extra_params=[
            SourceParam(name="stations", label="Stations", description="Comma-separated NMDB station codes", default="OULU,JUNG"),
        ],
    ),
    SourceMeta(
        id="geomag",
        label="USGS geomagnetic",
        domain="geomagnetic",
        description="Geomagnetic H/Z from USGS observatories (BOU, FRD).",
        cadence="1min",
        requires_internet=True,
        status="coming_soon",
    ),
    SourceMeta(
        id="usgs_hydro",
        label="USGS hydrology",
        domain="hydrology",
        description="USGS NWIS instantaneous values: streamflow, gauge height.",
        cadence="15min",
        requires_internet=True,
        status="coming_soon",
    ),
    SourceMeta(
        id="meteo",
        label="Open-Meteo archive",
        domain="weather",
        description="Hourly temperature / precipitation / wind from Open-Meteo.",
        cadence="1h",
        requires_internet=True,
        status="coming_soon",
    ),
    SourceMeta(
        id="pageviews",
        label="Wikimedia pageviews",
        domain="human_activity",
        description="Daily article pageviews (forward-filled to hourly).",
        cadence="1h",
        requires_internet=True,
        status="coming_soon",
    ),
]


def list_sources() -> list[SourceMeta]:
    return SOURCES


def get_source(source_id: str) -> SourceMeta | None:
    for s in SOURCES:
        if s.id == source_id:
            return s
    return None


def is_available(source_id: str) -> bool:
    s = get_source(source_id)
    return s is not None and s.status == "available"
