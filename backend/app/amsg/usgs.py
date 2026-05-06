import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .hapi import parse_start_end
from .io import SeriesData, format_timestamp
from .pipeline import make_run_dir, run_pipeline
from .transforms import apply_transform

USGS_BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"


def _format_time_param(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_cache_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_time(value):
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Could not parse time '{value}'")
    return parsed.to_pydatetime()


def _cache_path(cache_dir: Path, sites: list[str], params: list[str], start_dt: datetime, end_dt: datetime):
    sites_key = "-".join(sites)
    params_key = "-".join(params)
    name = f"{sites_key}__{params_key}__{_format_cache_stamp(start_dt)}__{_format_cache_stamp(end_dt)}.json"
    return cache_dir / name


def fetch_usgs_iv(
    sites: list[str],
    params: list[str],
    start,
    end,
    cache_dir: Path,
):
    sites = [str(site) for site in sites]
    params = [str(param) for param in params]
    start_dt = _parse_time(start) if not isinstance(start, datetime) else start
    end_dt = _parse_time(end) if not isinstance(end, datetime) else end

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(cache_dir, sites, params, start_dt, end_dt)

    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        query = {
            "format": "json",
            "sites": ",".join(sites),
            "parameterCd": ",".join(params),
            "startDT": _format_time_param(start_dt),
            "endDT": _format_time_param(end_dt),
        }
        url = f"{USGS_BASE_URL}?{urllib.parse.urlencode(query)}"
        with urllib.request.urlopen(url) as response:
            text = response.read().decode("utf-8")
        cache_path.write_text(text, encoding="utf-8")
        payload = json.loads(text)

    series_map = {}
    time_series = payload.get("value", {}).get("timeSeries", [])
    for entry in time_series:
        site_codes = entry.get("sourceInfo", {}).get("siteCode", [])
        site_id = site_codes[0].get("value") if site_codes else None
        var_codes = entry.get("variable", {}).get("variableCode", [])
        param_code = var_codes[0].get("value") if var_codes else None
        if not site_id or not param_code:
            continue

        values_block = entry.get("values", [])
        if not values_block:
            continue
        points = values_block[0].get("value", [])
        if not points:
            continue

        times = []
        values = []
        for point in points:
            ts = pd.to_datetime(point.get("dateTime"), utc=True, errors="coerce")
            if pd.isna(ts):
                continue
            value_raw = point.get("value")
            try:
                value = float(value_raw)
            except Exception:
                value = float("nan")
            times.append(ts)
            values.append(value)

        if not times:
            continue

        frame = pd.DataFrame({"time": times, "value": values})
        frame = frame.sort_values("time")
        frame = frame.drop_duplicates(subset=["time"], keep="last")
        series = pd.Series(frame["value"].to_numpy(dtype=float), index=frame["time"])

        source_id = f"usgs_{param_code}_{site_id}"
        series_map[source_id] = series

    return series_map


def usgs_domain_for_source(source_id: str) -> str:
    if source_id.startswith("usgs_00060_"):
        return "hydro_flow"
    if source_id.startswith("usgs_00065_"):
        return "hydro_level"
    return "hydro_other"


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


def _apply_transform(series: pd.Series, transform: str | None):
    values = apply_transform(series.to_numpy(dtype=float), transform)
    return pd.Series(values, index=series.index)


def _detrend_series(series: pd.Series):
    window = 96
    min_periods = 48
    baseline = series.rolling(window=window, min_periods=min_periods).median()
    return series - baseline


def run_usgs_demo(
    project_root: Path,
    start: str,
    days: int,
    sites: list[str],
    params: list[str],
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
    freq = config.get("freq") or "15min"
    transform = (transform or "identity").strip().lower()

    start_dt, end_dt = parse_start_end(start, days)

    cache_dir = project_root / "data" / "cache" / "usgs"
    series_map = fetch_usgs_iv(sites, params, start_dt, end_dt, cache_dir)
    if not series_map:
        raise RuntimeError("No USGS data returned.")

    resampled = {}
    for source_id, series in series_map.items():
        if transform == "detrend":
            base = series.resample(freq).mean()
            resampled[source_id] = _detrend_series(base)
        else:
            transformed = _apply_transform(series, transform)
            resampled[source_id] = transformed.resample(freq).mean()

    aligned = _align_series(resampled)
    if not aligned:
        raise RuntimeError("Failed to align USGS sources.")

    sources = []
    for source_id, series in aligned.items():
        domain_id = usgs_domain_for_source(source_id)

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
        "base_url": USGS_BASE_URL,
        "start": format_timestamp(start_dt),
        "end": format_timestamp(end_dt),
        "days": days,
        "freq": freq,
        "sites": sites,
        "params": params,
        "transform": transform,
    }
    if holdout_ratio is not None:
        inputs_payload["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        inputs_payload["holdout_mode"] = holdout_mode
    inputs_path = run_dir / "inputs_usgs.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    time_range = f"{format_timestamp(start_dt)} -> {format_timestamp(end_dt)}"

    print("USGS demo run:", run_dir)
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
