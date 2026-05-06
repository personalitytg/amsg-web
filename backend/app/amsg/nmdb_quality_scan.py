from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .nmdb import DEFAULT_DTYPE, DEFAULT_TABCHOICE, DEFAULT_YUNITS, fetch_nmdb, parse_start_end


def _format_stamp(value: pd.Timestamp) -> str:
    if isinstance(value, pd.Timestamp):
        ts = value
    else:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
    if ts is None or pd.isna(ts):
        raise ValueError("Invalid timestamp for formatting.")
    return ts.tz_convert(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _infer_freq_minutes(times: pd.DatetimeIndex) -> int:
    diffs = times.to_series().diff().dropna()
    diffs = diffs[diffs > pd.Timedelta(0)]
    if diffs.empty:
        return 1
    minutes = np.median(diffs.dt.total_seconds()) / 60.0
    if not np.isfinite(minutes) or minutes <= 0:
        return 1
    return max(1, int(round(minutes)))


def _extract_intervals(
    rolling: pd.Series,
    min_valid: float,
    min_duration_points: int,
    window_points: int,
    freq_delta: pd.Timedelta,
    scope: str,
    stations: list[str],
):
    intervals = []
    mask = rolling >= min_valid
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
                segment_start = current_start - (window_points - 1) * freq_delta
                if segment_start < rolling.index[0]:
                    segment_start = rolling.index[0]
                duration_points = current_len + window_points - 1
                duration_hours = duration_points * freq_delta.total_seconds() / 3600.0
                median_val = float(
                    np.nanmedian(rolling.loc[current_start:last_ts].to_numpy())
                )
                intervals.append(
                    {
                        "scope": scope,
                        "start": segment_start.isoformat(),
                        "end": last_ts.isoformat(),
                        "duration_hours": duration_hours,
                        "valid_fraction_median": median_val,
                        "stations": "|".join(stations),
                    }
                )
            current_start = None
            current_len = 0
            last_ts = None

    if current_start is not None and current_len >= min_duration_points:
        segment_start = current_start - (window_points - 1) * freq_delta
        if segment_start < rolling.index[0]:
            segment_start = rolling.index[0]
        duration_points = current_len + window_points - 1
        duration_hours = duration_points * freq_delta.total_seconds() / 3600.0
        median_val = float(np.nanmedian(rolling.loc[current_start:last_ts].to_numpy()))
        intervals.append(
            {
                "scope": scope,
                "start": segment_start.isoformat(),
                "end": last_ts.isoformat(),
                "duration_hours": duration_hours,
                "valid_fraction_median": median_val,
                "stations": "|".join(stations),
            }
        )
    return intervals


def run_nmdb_quality_scan_raw(
    project_root: Path,
    stations: list[str],
    start: str,
    days: int,
    window_hours: float,
    min_valid: float,
    min_duration_hours: float,
    top_k: int | None = None,
    dtype: str = DEFAULT_DTYPE,
    tabchoice: str = DEFAULT_TABCHOICE,
    yunits: int = DEFAULT_YUNITS,
):
    start_dt, end_dt = parse_start_end(start, days)
    cache_dir = project_root / "data" / "cache" / "nmdb"
    df = fetch_nmdb(
        stations=stations,
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
    times = times.dropna()
    times = times.sort_values()
    freq_minutes = _infer_freq_minutes(pd.DatetimeIndex(times))
    freq = f"{freq_minutes}min"
    freq_delta = pd.Timedelta(freq)

    try:
        full_index = pd.date_range(start=start_dt, end=end_dt, freq=freq, inclusive="left")
    except TypeError:
        full_index = pd.date_range(start=start_dt, end=end_dt - freq_delta, freq=freq)

    window_points = max(
        1, int(round(pd.Timedelta(hours=window_hours) / freq_delta))
    )
    min_duration_points = max(
        1, int(round(pd.Timedelta(hours=min_duration_hours) / freq_delta))
    )

    frame = pd.DataFrame(index=full_index)
    for station in stations:
        values = pd.to_numeric(df[station], errors="coerce")
        series = pd.Series(values.to_numpy(), index=times)
        series = series[~series.index.duplicated(keep="last")].sort_index()
        series = series.reindex(full_index)
        frame[station] = series

    intervals = []
    for station in stations:
        rolling = frame[station].notna().astype(float).rolling(
            window_points, min_periods=window_points
        ).mean()
        intervals.extend(
            _extract_intervals(
                rolling,
                min_valid,
                min_duration_points,
                window_points,
                freq_delta,
                scope=station,
                stations=[station],
            )
        )

    all_valid = frame.notna().all(axis=1).astype(float)
    rolling_all = all_valid.rolling(window_points, min_periods=window_points).mean()
    intervals.extend(
        _extract_intervals(
            rolling_all,
            min_valid,
            min_duration_points,
            window_points,
            freq_delta,
            scope="all",
            stations=stations,
        )
    )

    intervals.sort(
        key=lambda item: (item["duration_hours"], item["valid_fraction_median"]),
        reverse=True,
    )
    if top_k is not None and top_k > 0:
        intervals = intervals[: int(top_k)]

    stations_joined = "-".join(stations)
    output_name = (
        f"nmdb_quality_{stations_joined}_{_format_stamp(start_dt)}__{_format_stamp(end_dt)}.csv"
    )
    output_path = project_root / "data" / "derived" / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(intervals).to_csv(output_path, index=False)

    print(
        f"NMDB quality scan: stations={stations_joined}, freq={freq}, "
        f"intervals={len(intervals)}"
    )
    print("Saved:", output_path)
    return output_path, intervals
