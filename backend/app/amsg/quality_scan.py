import fnmatch
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .nmdb import DEFAULT_DTYPE, DEFAULT_TABCHOICE, DEFAULT_YUNITS, fetch_nmdb
from .time_utils import apply_time_offset


def _load_omni_nmdb_inputs(run_dir: Path) -> dict:
    inputs_path = run_dir / "inputs_omni_nmdb.json"
    if not inputs_path.exists():
        raise FileNotFoundError(f"Missing inputs_omni_nmdb.json in {run_dir}")
    return json.loads(inputs_path.read_text(encoding="utf-8"))


def _build_full_index(start_dt: pd.Timestamp, end_dt: pd.Timestamp, freq: str) -> pd.DatetimeIndex:
    freq_delta = pd.Timedelta(freq)
    try:
        return pd.date_range(start=start_dt, end=end_dt, freq=freq, inclusive="left")
    except TypeError:
        return pd.date_range(start=start_dt, end=end_dt - freq_delta, freq=freq)


def _rolling_valid(series: pd.Series, window_points: int) -> pd.Series:
    valid = series.notna().astype(float)
    return valid.rolling(window_points, min_periods=window_points).mean()


def run_quality_scan(
    run_dir: Path,
    sources: list[str],
    window_hours: float,
    min_valid: float,
    min_duration_hours: float,
    profile: str | None = None,
    project_root: Path | None = None,
):
    run_dir = Path(run_dir)
    if profile:
        profile_value = profile.strip().lower()
        if profile_value == "strict":
            min_valid = 0.9
            min_duration_hours = 72.0
        elif profile_value == "relaxed":
            min_valid = 0.8
            min_duration_hours = 48.0
        else:
            raise ValueError("profile must be 'strict' or 'relaxed'")
    inputs = _load_omni_nmdb_inputs(run_dir)
    freq = inputs.get("freq", "2min")
    stations = inputs.get("stations", [])
    if not stations:
        raise RuntimeError("inputs_omni_nmdb.json does not list NMDB stations.")

    source_ids = [f"nmdb_{station}" for station in stations]
    selected_sources = []
    for source_id in source_ids:
        if any(fnmatch.fnmatch(source_id, pattern) for pattern in sources):
            selected_sources.append(source_id)
    if not selected_sources:
        raise RuntimeError("No sources matched the requested patterns.")

    selected_stations = [
        station for station in stations if f"nmdb_{station}" in selected_sources
    ]
    nmdb_cfg = inputs.get("nmdb", {})
    dtype = nmdb_cfg.get("dtype", DEFAULT_DTYPE)
    tabchoice = nmdb_cfg.get("tabchoice", DEFAULT_TABCHOICE)
    yunits = nmdb_cfg.get("yunits", DEFAULT_YUNITS)
    time_offset = nmdb_cfg.get("time_offset", None)

    start_dt = pd.to_datetime(inputs["start"], utc=True, errors="coerce")
    end_dt = pd.to_datetime(inputs["end"], utc=True, errors="coerce")
    if pd.isna(start_dt) or pd.isna(end_dt):
        raise RuntimeError("inputs_omni_nmdb.json has invalid start/end timestamps.")

    cache_dir = (project_root / "data" / "cache" / "nmdb") if project_root else None
    df = fetch_nmdb(
        stations=selected_stations,
        start=start_dt,
        end=end_dt,
        dtype=dtype,
        tabchoice=tabchoice,
        yunits=yunits,
        cache_dir=cache_dir,
    )
    if df.empty or "Time" not in df.columns:
        raise RuntimeError("NMDB response did not contain data.")

    times = pd.to_datetime(df["Time"], utc=True, errors="coerce")
    times = apply_time_offset(times, time_offset)
    times = pd.to_datetime(times, utc=True, errors="coerce")
    df = df.drop(columns=["Time"])

    full_index = _build_full_index(start_dt, end_dt, freq)
    freq_delta = pd.Timedelta(freq)
    window_points = max(1, int(round(pd.Timedelta(hours=window_hours) / freq_delta)))
    min_duration_points = max(
        1, int(round(pd.Timedelta(hours=min_duration_hours) / freq_delta))
    )

    rolling_frames = []
    for station in selected_stations:
        values = pd.to_numeric(df[station], errors="coerce")
        series = pd.Series(values.to_numpy(), index=times)
        series = series[~series.index.duplicated(keep="last")].sort_index()
        series = series.resample(freq).mean()
        series = series.reindex(full_index)
        rolling = _rolling_valid(series, window_points)
        rolling_frames.append(rolling.rename(f"nmdb_{station}"))

    rolling_df = pd.concat(rolling_frames, axis=1)
    mask = (rolling_df >= min_valid).all(axis=1)
    per_ts_median = rolling_df.median(axis=1, skipna=True)

    intervals = []
    current_start = None
    current_len = 0
    last_ts = None

    for ts, ok in mask.items():
        if ok:
            if current_start is None:
                current_start = ts
                current_len = 1
            else:
                current_len += 1
            last_ts = ts
        elif current_start is not None:
            if current_len >= min_duration_points:
                duration_hours = (current_len * freq_delta).total_seconds() / 3600.0
                median_val = float(
                    np.nanmedian(per_ts_median.loc[current_start:last_ts].to_numpy())
                )
                intervals.append(
                    {
                        "start": current_start.isoformat(),
                        "end": last_ts.isoformat(),
                        "duration_hours": duration_hours,
                        "valid_fraction_median": median_val,
                        "sources": "|".join(sorted(selected_sources)),
                    }
                )
            current_start = None
            current_len = 0
            last_ts = None

    if current_start is not None and current_len >= min_duration_points:
        duration_hours = (current_len * freq_delta).total_seconds() / 3600.0
        median_val = float(
            np.nanmedian(per_ts_median.loc[current_start:last_ts].to_numpy())
        )
        intervals.append(
            {
                "start": current_start.isoformat(),
                "end": last_ts.isoformat(),
                "duration_hours": duration_hours,
                "valid_fraction_median": median_val,
                "sources": "|".join(sorted(selected_sources)),
            }
        )

    intervals.sort(
        key=lambda item: (item["duration_hours"], item["valid_fraction_median"]),
        reverse=True,
    )

    output_path = run_dir / "quality_intervals.csv"
    df_out = pd.DataFrame(intervals)
    df_out.to_csv(output_path, index=False)

    print(f"Quality scan intervals: {len(intervals)}")
    if intervals:
        best = intervals[0]
        print(
            f"Top interval: {best['start']} -> {best['end']} "
            f"({best['duration_hours']:.1f}h, median={best['valid_fraction_median']:.3f})"
        )
    print("Saved:", output_path)

    return output_path, intervals
