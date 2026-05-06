from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .time_utils import apply_time_offset
from .transforms import apply_transform

def _format_timestamp(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        return pd.Timestamp(value).isoformat()
    return str(value)


@dataclass
class SeriesData:
    source_id: str
    domain_id: str
    timestamps: np.ndarray
    values: np.ndarray
    quality: np.ndarray | None
    path: Path | None = None

    def start_time(self):
        return _format_timestamp(self.timestamps[0]) if len(self.timestamps) else ""

    def end_time(self):
        return _format_timestamp(self.timestamps[-1]) if len(self.timestamps) else ""


def _parse_timestamps(series: pd.Series):
    if np.issubdtype(series.dtype, np.number):
        return series.to_numpy()
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().all():
        return series.astype(str).to_numpy()
    return parsed.to_numpy()


def load_series(spec: dict):
    fmt = spec["format"]
    path = Path(spec["path"])
    if fmt == "csv":
        df = pd.read_csv(path)
    elif fmt in {"parquet", "pq"}:
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported format '{fmt}' for {path}")

    ts_col = spec["timestamp_col"]
    val_col = spec["value_col"]
    quality_col = spec.get("quality_col")

    if ts_col not in df.columns:
        raise ValueError(f"Missing timestamp column '{ts_col}' in {path}")
    if val_col not in df.columns:
        raise ValueError(f"Missing value column '{val_col}' in {path}")

    timestamps_raw = df[ts_col]
    timestamps = _parse_timestamps(timestamps_raw)

    values = pd.to_numeric(df[val_col], errors="coerce").to_numpy(dtype=float)
    quality = None
    if quality_col and quality_col in df.columns:
        quality = pd.to_numeric(df[quality_col], errors="coerce").to_numpy(dtype=float)

    time_offset = spec.get("time_offset")
    if time_offset:
        timestamps = apply_time_offset(timestamps, time_offset)

    if np.issubdtype(timestamps.dtype, np.datetime64) or np.issubdtype(
        timestamps.dtype, np.number
    ):
        order = np.argsort(timestamps)
        timestamps = timestamps[order]
        values = values[order]
        if quality is not None:
            quality = quality[order]

    values = apply_transform(values, spec.get("transform"))

    return SeriesData(
        source_id=spec["source_id"],
        domain_id=spec["domain_id"],
        timestamps=timestamps,
        values=values,
        quality=quality,
        path=path,
    )


def format_timestamp(value):
    return _format_timestamp(value)
