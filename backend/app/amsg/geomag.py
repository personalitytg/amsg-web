import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .hapi import parse_start_end
from .io import SeriesData, format_timestamp
from .pipeline import make_run_dir, run_pipeline

GEOMAG_BASE_URL = "https://geomag.usgs.gov/ws/data/"


def _format_time_param(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_cache_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _cache_path(
    cache_dir: Path,
    station: str,
    elements: list[str],
    start_dt: datetime,
    end_dt: datetime,
):
    station_key = station.upper()
    elements_key = "-".join(elements)
    name = (
        f"{station_key}__{elements_key}__"
        f"{_format_cache_stamp(start_dt)}__{_format_cache_stamp(end_dt)}.json"
    )
    return cache_dir / name


def _fetch_geomag_station_once(
    station: str,
    elements: list[str],
    start_dt: datetime,
    end_dt: datetime,
    cache_dir: Path,
    sampling_period: int,
):
    cache_path = _cache_path(cache_dir, station, elements, start_dt, end_dt)

    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        params = {
            "id": station,
            "starttime": _format_time_param(start_dt),
            "endtime": _format_time_param(end_dt),
            "elements": ",".join(elements),
            "sampling_period": str(int(sampling_period)),
            "format": "json",
        }
        url = f"{GEOMAG_BASE_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url) as response:
            text = response.read().decode("utf-8")
        cache_path.write_text(text, encoding="utf-8")
        payload = json.loads(text)

    times = pd.to_datetime(payload.get("times", []), utc=True, errors="coerce")
    if times is None or pd.isna(times).all():
        return {}
    times = pd.Series(times)

    series_map = {}
    for entry in payload.get("values", []):
        element = entry.get("id")
        if not element:
            continue
        values = pd.to_numeric(entry.get("values", []), errors="coerce")
        values = pd.Series(values)
        count = min(len(times), len(values))
        if count == 0:
            continue
        frame = pd.DataFrame(
            {"time": times.iloc[:count], "value": values.iloc[:count]}
        ).dropna(subset=["time"])
        if frame.empty:
            continue
        frame = frame.sort_values("time")
        frame = frame.drop_duplicates(subset=["time"], keep="last")
        series = pd.Series(frame["value"].to_numpy(dtype=float), index=frame["time"])
        source_id = f"geomag_{station}_{str(element).upper()}"
        series_map[source_id] = series

    return series_map


def fetch_geomag_station(
    station: str,
    elements: list[str],
    start_dt: datetime,
    end_dt: datetime,
    cache_dir: Path,
    sampling_period: int = 60,
    chunk_days: int = 30,
):
    station = str(station).upper()
    elements = [str(elem).upper() for elem in elements]
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if chunk_days and (end_dt - start_dt).days > chunk_days:
        series_lists = {}
        current = start_dt
        while current < end_dt:
            chunk_end = min(current + timedelta(days=chunk_days), end_dt)
            chunk_map = _fetch_geomag_station_once(
                station, elements, current, chunk_end, cache_dir, sampling_period
            )
            for key, series in chunk_map.items():
                series_lists.setdefault(key, []).append(series)
            current = chunk_end
        merged = {}
        for key, series_list in series_lists.items():
            combined = pd.concat(series_list).sort_index()
            combined = combined[~combined.index.duplicated(keep="last")]
            merged[key] = combined
        return merged

    return _fetch_geomag_station_once(
        station, elements, start_dt, end_dt, cache_dir, sampling_period
    )


def geomag_domain_for_element(element: str) -> str:
    element = str(element).upper()
    if element == "H":
        return "geomag_H"
    if element == "D":
        return "geomag_D"
    if element == "Z":
        return "geomag_Z"
    if element == "F":
        return "geomag_F"
    return "geomag_other"


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


def run_geomag_demo(
    project_root: Path,
    start: str,
    days: int,
    stations: list[str],
    elements: list[str],
    config_path: Path,
    sampling_period: int = 60,
    holdout_ratio: float | None = None,
    holdout_mode: str | None = None,
):
    from .config import load_config

    config = load_config(config_path)
    if holdout_ratio is not None:
        config["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        config["holdout_mode"] = holdout_mode
    freq = config.get("freq") or "1min"

    start_dt, end_dt = parse_start_end(start, days)
    cache_dir = project_root / "data" / "cache" / "geomag"

    series_map = {}
    for station in stations:
        series_map.update(
            fetch_geomag_station(
                station, elements, start_dt, end_dt, cache_dir, sampling_period=sampling_period
            )
        )

    if not series_map:
        raise RuntimeError("No geomag data returned.")

    resampled = {}
    for source_id, series in series_map.items():
        resampled[source_id] = series.resample(freq).mean()

    aligned = _align_series(resampled)
    if not aligned:
        raise RuntimeError("Failed to align geomag sources.")

    sources = []
    for source_id, series in aligned.items():
        element = source_id.split("_")[-1]
        domain_id = geomag_domain_for_element(element)
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
        "base_url": GEOMAG_BASE_URL,
        "start": format_timestamp(start_dt),
        "end": format_timestamp(end_dt),
        "days": days,
        "freq": freq,
        "stations": [str(station).upper() for station in stations],
        "elements": [str(elem).upper() for elem in elements],
        "sampling_period": sampling_period,
    }
    if holdout_ratio is not None:
        inputs_payload["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        inputs_payload["holdout_mode"] = holdout_mode
    inputs_path = run_dir / "inputs_geomag.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    time_range = f"{format_timestamp(start_dt)} -> {format_timestamp(end_dt)}"

    print("Geomag demo run:", run_dir)
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
