import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .hapi import fetch_data, parse_start_end
from .io import SeriesData, format_timestamp
from .pipeline import make_run_dir, run_pipeline

OMNI_BASE_URL = "https://cdaweb.gsfc.nasa.gov/hapi"
OMNI_DATASET_ID = "OMNI_HRO_1MIN"
OMNI_PARAMETERS = ["Time", "BZ_GSM", "flow_speed", "proton_density", "SYM_H"]
DEFAULT_CHUNK_DAYS = 7


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


def build_omni_sources(
    cache_dir: Path,
    start: str,
    days: int,
    freq: str,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    base_url: str = OMNI_BASE_URL,
    dataset_id: str = OMNI_DATASET_ID,
):
    start_dt, end_dt = parse_start_end(start, days)
    df = fetch_data(
        base_url,
        dataset_id,
        start_dt,
        end_dt,
        OMNI_PARAMETERS,
        cache_dir,
        chunk_days=chunk_days,
    )

    if df.empty:
        raise RuntimeError("No OMNI data returned from HAPI.")

    time_col = OMNI_PARAMETERS[0]
    if time_col not in df.columns:
        raise RuntimeError("OMNI data missing Time column.")

    required_cols = ["BZ_GSM", "flow_speed", "proton_density", "SYM_H"]
    for col in required_cols:
        if col not in df.columns:
            raise RuntimeError(f"OMNI data missing column '{col}'.")

    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df = df.dropna(subset=[time_col])

    series_map = {
        "omni_bz_gsm": df.set_index(time_col)["BZ_GSM"].resample(freq).mean(),
        "omni_flow_speed": df.set_index(time_col)["flow_speed"].resample(freq).mean(),
        "omni_proton_density": df.set_index(time_col)["proton_density"].resample(freq).mean(),
        "omni_sym_h": df.set_index(time_col)["SYM_H"].resample(freq).mean(),
    }

    aligned = _align_series(series_map)
    if not aligned:
        raise RuntimeError("Failed to align OMNI sources.")

    sources = [
        SeriesData(
            source_id="omni_bz_gsm",
            domain_id="omni_imf",
            timestamps=aligned["omni_bz_gsm"].index.to_numpy(),
            values=aligned["omni_bz_gsm"].to_numpy(dtype=float),
            quality=None,
            path=None,
        ),
        SeriesData(
            source_id="omni_flow_speed",
            domain_id="omni_plasma",
            timestamps=aligned["omni_flow_speed"].index.to_numpy(),
            values=aligned["omni_flow_speed"].to_numpy(dtype=float),
            quality=None,
            path=None,
        ),
        SeriesData(
            source_id="omni_proton_density",
            domain_id="omni_plasma",
            timestamps=aligned["omni_proton_density"].index.to_numpy(),
            values=aligned["omni_proton_density"].to_numpy(dtype=float),
            quality=None,
            path=None,
        ),
        SeriesData(
            source_id="omni_sym_h",
            domain_id="omni_geomag",
            timestamps=aligned["omni_sym_h"].index.to_numpy(),
            values=aligned["omni_sym_h"].to_numpy(dtype=float),
            quality=None,
            path=None,
        ),
    ]

    return sources, start_dt, end_dt


def run_omni_demo(
    project_root: Path,
    start: str,
    days: int,
    config_path: Path,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
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

    cache_dir = project_root / "data" / "cache" / "hapi"
    sources, start_dt, end_dt = build_omni_sources(
        cache_dir,
        start,
        days,
        freq,
        chunk_days=chunk_days,
    )

    run_dir = make_run_dir(project_root / "runs")
    results, events = run_pipeline(sources, config, run_dir, return_events=True)

    inputs_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": OMNI_BASE_URL,
        "dataset_id": OMNI_DATASET_ID,
        "start": format_timestamp(start_dt),
        "end": format_timestamp(end_dt),
        "days": days,
        "chunk_days": chunk_days,
        "freq": freq,
        "parameters": OMNI_PARAMETERS,
        "sources": [
            {
                "source_id": "omni_bz_gsm",
                "domain_id": "omni_imf",
                "parameter": "BZ_GSM",
            },
            {
                "source_id": "omni_flow_speed",
                "domain_id": "omni_plasma",
                "parameter": "flow_speed",
            },
            {
                "source_id": "omni_proton_density",
                "domain_id": "omni_plasma",
                "parameter": "proton_density",
            },
            {
                "source_id": "omni_sym_h",
                "domain_id": "omni_geomag",
                "parameter": "SYM_H",
            },
        ],
    }
    if holdout_ratio is not None:
        inputs_payload["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        inputs_payload["holdout_mode"] = holdout_mode
    inputs_path = run_dir / "inputs_omni.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    time_range = f"{format_timestamp(start_dt)} -> {format_timestamp(end_dt)}"

    print("OMNI demo run:", run_dir)
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
