import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .hapi import parse_start_end
from .io import SeriesData, format_timestamp
from .meteo import METEO_HOURLY_VARS, fetch_open_meteo
from .pipeline import make_run_dir, run_pipeline
from .time_utils import parse_time_offset
from .usgs import fetch_usgs_iv, usgs_domain_for_source


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


def _is_cross_domain_event(event):
    domains = event.domains_involved
    return any(domain.startswith("hydro_") for domain in domains) and any(
        domain.startswith("meteo_") for domain in domains
    )


def _cross_domain_metrics(events):
    cross_events = [evt for evt in events if _is_cross_domain_event(evt)]
    top_events = sorted(events, key=lambda evt: evt.event_score, reverse=True)[:10]
    cross_top = [evt for evt in top_events if _is_cross_domain_event(evt)]
    best_event = max(cross_events, key=lambda evt: evt.event_score, default=None)
    return {
        "cross_domain_events_count": len(cross_events),
        "cross_domain_in_top10_count": len(cross_top),
        "best_cross_domain_event": best_event,
    }


def _write_control_report(run_dir: Path, metrics: dict, shift_days: int, shift_hours: int | None):
    best_event = metrics["best_cross_domain_event"]
    payload = {
        "run_id": run_dir.name,
        "meteo_shift_days": shift_days,
        "meteo_shift_hours": shift_hours,
        "cross_domain_events_count": metrics["cross_domain_events_count"],
        "cross_domain_in_top10_count": metrics["cross_domain_in_top10_count"],
        "best_cross_domain_event": None,
    }
    if best_event is not None:
        payload["best_cross_domain_event"] = {
            "event_id": best_event.event_id,
            "event_start": format_timestamp(best_event.event_start),
            "event_end": format_timestamp(best_event.event_end),
            "event_score": best_event.event_score,
            "best_nms": best_event.best_nms,
            "best_p_value": best_event.best_p_value,
            "edge_novelty_sum": best_event.edge_novelty_sum,
            "orphan_score": best_event.orphan_score,
        }
    report_path = run_dir / "control_report.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def _summarize_for_compare(metrics: dict):
    best_event = metrics["best_cross_domain_event"]
    return {
        "cross_domain_events_count": metrics["cross_domain_events_count"],
        "cross_domain_in_top10_count": metrics["cross_domain_in_top10_count"],
        "best_cross_domain_event_score": best_event.event_score if best_event is not None else 0.0,
    }


def _compare_verdict(real_summary: dict, shift_summary: dict):
    real_events = real_summary["cross_domain_events_count"]
    real_top = real_summary["cross_domain_in_top10_count"]
    shift_events = shift_summary["cross_domain_events_count"]
    shift_top = shift_summary["cross_domain_in_top10_count"]
    if real_events == 0:
        return "OK: no cross-domain events in REAL"
    drop_events = shift_events <= real_events // 2
    drop_top = shift_top <= real_top // 2
    if drop_events and drop_top:
        return "OK: cross-domain participation drops under shift"
    return "SUSPECT: cross-domain participation persists under shift"


def run_earth_demo(
    project_root: Path,
    start: str,
    days: int,
    sites: list[str],
    params: list[str],
    latlon_pairs: list[tuple[float, float]],
    config_path: Path,
    meteo_shift_days: int = 13,
    meteo_shift_hours: int | None = None,
):
    from .config import load_config

    config = load_config(config_path)
    freq = config.get("freq") or "1h"

    cache_dir_usgs = project_root / "data" / "cache" / "usgs"
    cache_dir_meteo = project_root / "data" / "cache" / "meteo"

    start_dt, end_dt = parse_start_end(start, days)

    def _build_sources(meteo_offset: str | None):
        usgs_map = fetch_usgs_iv(sites, params, start_dt, end_dt, cache_dir_usgs)
        if not usgs_map:
            raise RuntimeError("No USGS data returned.")
        meteo_map = {}
        for lat, lon in latlon_pairs:
            meteo_map.update(fetch_open_meteo(lat, lon, start_dt, end_dt, cache_dir_meteo))
        if not meteo_map:
            raise RuntimeError("No Open-Meteo data returned.")

        if meteo_offset:
            delta = parse_time_offset(meteo_offset)
            if delta != pd.Timedelta(0):
                for key in list(meteo_map.keys()):
                    meteo_map[key] = meteo_map[key].copy()
                    meteo_map[key].index = meteo_map[key].index + delta

        series_map = {}
        for source_id, series in usgs_map.items():
            series_map[source_id] = series.resample(freq).mean()
        for source_id, series in meteo_map.items():
            series_map[source_id] = series.resample(freq).mean()

        aligned = _align_series(series_map)
        if not aligned:
            raise RuntimeError("Failed to align USGS and Open-Meteo sources.")

        sources = []
        for source_id, series in aligned.items():
            if source_id.startswith("usgs_"):
                domain_id = usgs_domain_for_source(source_id)
            elif "temperature_2m" in source_id:
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
        return sources

    def _run_single(meteo_offset: str | None, shift_days: int, shift_hours: int | None):
        sources = _build_sources(meteo_offset)
        run_dir = make_run_dir(project_root / "runs")
        results, events = run_pipeline(sources, config, run_dir, return_events=True)

        inputs_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start": format_timestamp(start_dt),
            "end": format_timestamp(end_dt),
            "days": days,
            "freq": freq,
            "sites": sites,
            "params": params,
            "latlon": latlon_pairs,
            "meteo": {
                "hourly": METEO_HOURLY_VARS,
                "time_offset": meteo_offset or "0",
            },
        }
        inputs_path = run_dir / "inputs_earth.json"
        inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

        metrics = _cross_domain_metrics(events)
        _write_control_report(run_dir, metrics, shift_days, shift_hours)
        return run_dir, metrics

    print("Earth demo (REAL):")
    run_dir_real, metrics_real = _run_single(None, 0, 0)

    if meteo_shift_hours is not None:
        shift_offset = f"+{int(meteo_shift_hours)}h"
        shift_days = 0
        shift_hours = int(meteo_shift_hours)
    else:
        shift_offset = f"+{int(meteo_shift_days)}d"
        shift_days = int(meteo_shift_days)
        shift_hours = None

    print("Earth demo (SHIFT):")
    run_dir_shift, metrics_shift = _run_single(shift_offset, shift_days, shift_hours)

    summary_real = _summarize_for_compare(metrics_real)
    summary_shift = _summarize_for_compare(metrics_shift)
    verdict = _compare_verdict(summary_real, summary_shift)
    compare_payload = {
        "control_type": "earth",
        "run_id_real": run_dir_real.name,
        "run_id_shift": run_dir_shift.name,
        "meteo_shift_days": shift_days,
        "meteo_shift_hours": shift_hours,
        "real": summary_real,
        "shift": summary_shift,
        "delta": {
            "cross_domain_events_count": summary_real["cross_domain_events_count"]
            - summary_shift["cross_domain_events_count"],
            "cross_domain_in_top10_count": summary_real["cross_domain_in_top10_count"]
            - summary_shift["cross_domain_in_top10_count"],
        },
        "verdict": verdict,
    }
    compare_path = run_dir_real / "control_compare.json"
    compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")

    print("Compare REAL vs SHIFT:")
    print(
        "  delta cross_domain_events_count:",
        compare_payload["delta"]["cross_domain_events_count"],
    )
    print(
        "  delta cross_domain_in_top10_count:",
        compare_payload["delta"]["cross_domain_in_top10_count"],
    )
    if verdict.startswith("SUSPECT"):
        print("WARNING:", verdict)
    else:
        print(verdict)

    return run_dir_real, run_dir_shift
