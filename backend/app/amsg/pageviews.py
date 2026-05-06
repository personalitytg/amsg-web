import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .hapi import parse_start_end
from .io import SeriesData, format_timestamp
from .pipeline import make_run_dir, run_pipeline
from .time_utils import parse_time_offset

PAGEVIEWS_BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


def _format_time_param(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H")


def _format_cache_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H")


def _sanitize_token(value: str) -> str:
    text = str(value).strip().lower().replace(" ", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def pageviews_source_id(article: str) -> str:
    return f"wiki_{_sanitize_token(article)}"


def resample_pageviews_series(series: pd.Series, freq: str, granularity: str):
    resampled = series.resample(freq).mean()
    if granularity in {"daily", "monthly"} and resampled.isna().any():
        resampled = resampled.ffill()
    return resampled


def _cache_path(
    cache_dir: Path,
    project: str,
    article: str,
    start_dt: datetime,
    end_dt: datetime,
    granularity: str,
):
    project_key = _sanitize_token(project)
    article_key = _sanitize_token(article)
    name = (
        f"{project_key}__{article_key}__"
        f"{_format_cache_stamp(start_dt)}__{_format_cache_stamp(end_dt)}__{granularity}.json"
    )
    return cache_dir / name


def fetch_pageviews_series(
    project: str,
    access: str,
    agent: str,
    article: str,
    granularity: str,
    start_dt: datetime,
    end_dt: datetime,
    cache_dir: Path,
):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    granularity = str(granularity).lower()

    end_param_dt = end_dt
    if granularity == "hourly":
        end_param_dt = end_dt - timedelta(hours=1)
        if end_param_dt < start_dt:
            end_param_dt = end_dt

    cache_path = _cache_path(cache_dir, project, article, start_dt, end_param_dt, granularity)
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        project_path = urllib.parse.quote(str(project), safe="")
        access_path = urllib.parse.quote(str(access), safe="")
        agent_path = urllib.parse.quote(str(agent), safe="")
        article_path = urllib.parse.quote(str(article), safe="")
        start_param = _format_time_param(start_dt)
        end_param = _format_time_param(end_param_dt)
        url = (
            f"{PAGEVIEWS_BASE_URL}/{project_path}/{access_path}/"
            f"{agent_path}/{article_path}/{granularity}/{start_param}/{end_param}"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AMSG/0.1 (pageviews ingest)"},
        )
        with urllib.request.urlopen(req) as response:
            text = response.read().decode("utf-8")
        cache_path.write_text(text, encoding="utf-8")
        payload = json.loads(text)

    items = payload.get("items", [])
    times = []
    values = []
    for item in items:
        ts_raw = item.get("timestamp")
        if not ts_raw:
            continue
        ts = pd.to_datetime(str(ts_raw), format="%Y%m%d%H", utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        views_raw = item.get("views")
        try:
            views = float(views_raw)
        except Exception:
            views = float("nan")
        times.append(ts)
        values.append(views)

    if not times:
        return None

    frame = pd.DataFrame({"time": times, "value": values}).sort_values("time")
    frame = frame.drop_duplicates(subset=["time"], keep="last")
    return pd.Series(frame["value"].to_numpy(dtype=float), index=frame["time"])


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


def run_pageviews_demo(
    project_root: Path,
    start: str,
    days: int,
    articles: list[str],
    config_path: Path,
    project: str = "en.wikipedia",
    access: str = "all-access",
    agent: str = "all-agents",
    granularity: str = "hourly",
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

    start_dt, end_dt = parse_start_end(start, days)
    cache_dir = project_root / "data" / "cache" / "pageviews"

    series_map = {}
    for article in articles:
        series = fetch_pageviews_series(
            project,
            access,
            agent,
            article,
            granularity,
            start_dt,
            end_dt,
            cache_dir,
        )
        if series is None:
            continue
        source_id = pageviews_source_id(article)
        series_map[source_id] = series

    if not series_map:
        raise RuntimeError("No pageviews data returned.")

    resampled = {}
    for source_id, series in series_map.items():
        resampled[source_id] = resample_pageviews_series(series, freq, granularity)

    aligned = _align_series(resampled)
    if not aligned:
        raise RuntimeError("Failed to align pageviews sources.")

    sources = []
    for source_id, series in aligned.items():
        sources.append(
            SeriesData(
                source_id=source_id,
                domain_id="human_activity",
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
        "base_url": PAGEVIEWS_BASE_URL,
        "project": project,
        "access": access,
        "agent": agent,
        "granularity": granularity,
        "start": format_timestamp(start_dt),
        "end": format_timestamp(end_dt),
        "days": days,
        "freq": freq,
        "articles": articles,
    }
    if holdout_ratio is not None:
        inputs_payload["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        inputs_payload["holdout_mode"] = holdout_mode
    inputs_path = run_dir / "inputs_pageviews.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    time_range = f"{format_timestamp(start_dt)} -> {format_timestamp(end_dt)}"

    print("Pageviews demo run:", run_dir)
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


def apply_pageviews_time_offset(series_map: dict[str, pd.Series], time_offset: str | None):
    if not time_offset:
        return series_map
    delta = parse_time_offset(time_offset)
    if delta == pd.Timedelta(0):
        return series_map
    updated = {}
    for source_id, series in series_map.items():
        shifted = series.copy()
        shifted.index = shifted.index + delta
        updated[source_id] = shifted
    return updated
