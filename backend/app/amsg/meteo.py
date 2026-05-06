import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .hapi import parse_start_end
from .io import SeriesData, format_timestamp
from .pipeline import make_run_dir, run_pipeline

METEO_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
METEO_HOURLY_VARS = ["temperature_2m", "precipitation", "windspeed_10m"]


def _format_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _format_cache_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d")


def _format_coord(value: float) -> str:
    text = f"{value:.2f}"
    text = text.replace("-", "m").replace(".", "p")
    return text


def _cache_path(cache_dir: Path, lat: float, lon: float, start_dt: datetime, end_dt: datetime):
    name = (
        f"{_format_coord(lat)}_{_format_coord(lon)}__"
        f"{_format_cache_stamp(start_dt)}__{_format_cache_stamp(end_dt)}.json"
    )
    return cache_dir / name


def fetch_open_meteo(
    lat: float,
    lon: float,
    start_dt: datetime,
    end_dt: datetime,
    cache_dir: Path,
):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(cache_dir, lat, lon, start_dt, end_dt)

    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        params = {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "start_date": _format_date(start_dt),
            "end_date": _format_date(end_dt - timedelta(days=1)),
            "hourly": ",".join(METEO_HOURLY_VARS),
            "timezone": "UTC",
        }
        url = f"{METEO_BASE_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url) as response:
            text = response.read().decode("utf-8")
        cache_path.write_text(text, encoding="utf-8")
        payload = json.loads(text)

    hourly = payload.get("hourly", {})
    times = pd.to_datetime(hourly.get("time", []), utc=True, errors="coerce")
    if times.isna().all():
        return {}

    series_map = {}
    for var in METEO_HOURLY_VARS:
        values = pd.to_numeric(hourly.get(var, []), errors="coerce")
        values = np.asarray(values, dtype=float)
        if len(values) != len(times):
            continue
        frame = pd.DataFrame({"time": times, "value": values}).dropna(subset=["time"])
        series = pd.Series(frame["value"].to_numpy(dtype=float), index=frame["time"])
        source_id = f"meteo_{var}_{_format_coord(lat)}_{_format_coord(lon)}"
        series_map[source_id] = series

    return series_map


def _align_series(series_map: dict[str, pd.Series]):
    common_index = None
    for series in series_map.values():
        if common_index is None:
            common_index = series.index
        else:
            common_index = common_index.intersection(series.index)
    if common_index is None or common_index.empty:
        return {}
    aligned = {}
    for source_id, series in series_map.items():
        aligned[source_id] = series.reindex(common_index)
    return aligned


def _detrend_series(series: pd.Series):
    window = 24
    min_periods = 12
    baseline = series.rolling(window=window, min_periods=min_periods).median()
    return series - baseline


def run_meteo_demo(
    project_root: Path,
    start: str,
    days: int,
    latlon_pairs: list[tuple[float, float]],
    config_path: Path,
    transform: str | None = None,
    holdout_ratio: float | None = None,
    holdout_mode: str | None = None,
):
    from .config import load_config

    config = load_config(config_path)
    if holdout_ratio is not None:
        config["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        config["holdout_mode"] = holdout_mode
    freq = config.get("freq") or "1h"
    transform = (transform or "identity").strip().lower()

    start_dt, end_dt = parse_start_end(start, days)
    cache_dir = project_root / "data" / "cache" / "meteo"

    series_map = {}
    for lat, lon in latlon_pairs:
        series_map.update(fetch_open_meteo(lat, lon, start_dt, end_dt, cache_dir))

    if not series_map:
        raise RuntimeError("No Open-Meteo data returned.")

    resampled = {}
    for source_id, series in series_map.items():
        base = series.resample(freq).mean()
        if transform == "detrend":
            resampled[source_id] = _detrend_series(base)
        else:
            resampled[source_id] = base
    aligned = _align_series(resampled)
    if not aligned:
        raise RuntimeError("Failed to align Open-Meteo sources.")

    sources = []
    for source_id, series in aligned.items():
        if "temperature_2m" in source_id:
            domain_id = "meteo_temp"
        elif "precipitation" in source_id:
            domain_id = "meteo_precip"
        elif "windspeed_10m" in source_id:
            domain_id = "meteo_wind"
        else:
            domain_id = "meteo_other"

        sources.append(
            SeriesData(
                source_id=source_id,
                domain_id=domain_id,
                timestamps=series.index.to_numpy(),
                values=series.to_numpy(dtype=float),
                quality=None,
                path=None,
            )
        )

    run_dir = make_run_dir(project_root / "runs")
    results, events = run_pipeline(sources, config, run_dir, return_events=True)

    inputs_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": METEO_BASE_URL,
        "start": format_timestamp(start_dt),
        "end": format_timestamp(end_dt),
        "days": days,
        "freq": freq,
        "latlon": latlon_pairs,
        "hourly": METEO_HOURLY_VARS,
        "transform": transform,
    }
    if holdout_ratio is not None:
        inputs_payload["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        inputs_payload["holdout_mode"] = holdout_mode
    inputs_path = run_dir / "inputs_meteo.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    time_range = f"{format_timestamp(start_dt)} -> {format_timestamp(end_dt)}"

    print("Meteo demo run:", run_dir)
    print(f"Time range: {time_range}")
    if stats:
        print(
            f"Points: {stats.get('total_points')} | Windows: {stats.get('total_windows')} | Candidates: {stats.get('total_candidates')} | Events: {stats.get('total_events')}"
        )

    cross_domain_events = [evt for evt in events if evt.cross_domain_edges_count > 0]
    same_domain_events = [evt for evt in events if evt.cross_domain_edges_count == 0]
    cross_domain_events.sort(key=lambda evt: evt.event_score, reverse=True)
    same_domain_events.sort(key=lambda evt: evt.event_score, reverse=True)

    print("Top cross-domain EVENTS:")
    for item in cross_domain_events[:10]:
        print(
            f"  {item.event_id} {format_timestamp(item.event_start)} -> {format_timestamp(item.event_end)} score={item.event_score:.3f} orphan={item.orphan_score:.1f} nms={item.best_nms:.3f} p_value={item.best_p_value:.3f}"
        )

    print("Top same-domain EVENTS:")
    for item in same_domain_events[:10]:
        print(
            f"  {item.event_id} {format_timestamp(item.event_start)} -> {format_timestamp(item.event_end)} score={item.event_score:.3f} orphan={item.orphan_score:.1f} nms={item.best_nms:.3f} p_value={item.best_p_value:.3f}"
        )

    return run_dir
