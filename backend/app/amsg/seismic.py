import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .hapi import fetch_data, parse_start_end
from .io import SeriesData, format_timestamp
from .pipeline import make_run_dir, run_pipeline
from .time_utils import parse_time_offset

USGS_QUAKE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
OMNI_BASE_URL = "https://cdaweb.gsfc.nasa.gov/hapi"
OMNI_DATASET_ID = "OMNI_HRO_1MIN"
OMNI_PARAMETERS = ["Time", "BZ_GSM", "flow_speed", "proton_density", "SYM_H"]


def _format_time_param(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_cache_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _format_bbox(bbox):
    if not bbox:
        return "global"
    return f"{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}"


def _cache_path(cache_dir: Path, start_dt: datetime, end_dt: datetime, min_magnitude: float, bbox):
    name = (
        f"m{min_magnitude:.1f}__{_format_bbox(bbox)}__"
        f"{_format_cache_stamp(start_dt)}__{_format_cache_stamp(end_dt)}.json"
    )
    return cache_dir / name


def fetch_earthquake_events(
    start_dt: datetime,
    end_dt: datetime,
    min_magnitude: float,
    cache_dir: Path,
    bbox: tuple[float, float, float, float] | None = None,
):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(cache_dir, start_dt, end_dt, min_magnitude, bbox)

    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        params = {
            "format": "geojson",
            "starttime": _format_time_param(start_dt),
            "endtime": _format_time_param(end_dt),
            "minmagnitude": f"{min_magnitude:.1f}",
        }
        if bbox:
            params.update(
                {
                    "minlatitude": bbox[0],
                    "maxlatitude": bbox[1],
                    "minlongitude": bbox[2],
                    "maxlongitude": bbox[3],
                }
            )
        url = f"{USGS_QUAKE_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url) as response:
            text = response.read().decode("utf-8")
        cache_path.write_text(text, encoding="utf-8")
        payload = json.loads(text)

    rows = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        time_ms = props.get("time")
        if time_ms is None:
            continue
        ts = pd.to_datetime(time_ms, unit="ms", utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        mag_raw = props.get("mag")
        try:
            mag = float(mag_raw)
        except Exception:
            mag = float("nan")
        rows.append({"time": ts, "mag": mag})

    if not rows:
        return pd.DataFrame(columns=["time", "mag"])

    frame = pd.DataFrame(rows)
    frame = frame.sort_values("time")
    return frame


def build_seismic_series(events: pd.DataFrame, freq: str):
    if events.empty:
        return {}
    events = events.dropna(subset=["time"])
    if events.empty:
        return {}

    events = events.set_index("time")
    count = events["mag"].resample(freq).count().astype(float)
    mag_values = events["mag"].to_numpy(dtype=float)
    energy = np.where(np.isfinite(mag_values), 10 ** (1.5 * mag_values), np.nan)
    events["energy"] = energy
    energy_sum = events["energy"].resample(freq).sum(min_count=1).fillna(0.0)

    return {
        "seismic_count": count,
        "seismic_energy": energy_sum,
    }


def _apply_seismic_transform(series_map: dict[str, pd.Series], transform: str | None):
    transform = (transform or "identity").strip().lower()
    if transform == "identity":
        return series_map
    if transform == "log1p":
        updated = {}
        for key, series in series_map.items():
            values = series.to_numpy(dtype=float)
            updated[key] = pd.Series(np.log1p(values), index=series.index)
        return updated
    raise ValueError(f"Unsupported seismic transform '{transform}'.")


def _apply_zero_policy(
    series_map: dict[str, pd.Series],
    zero_as_nan: bool,
    min_nonzero_fraction: float | None,
    window_points: int,
):
    if not zero_as_nan and not min_nonzero_fraction:
        return series_map
    updated = {}
    for key, series in series_map.items():
        values = series.to_numpy(dtype=float)
        series_out = pd.Series(values, index=series.index)
        if min_nonzero_fraction is not None and window_points > 1:
            nonzero = pd.Series(values != 0, index=series.index).rolling(
                window=window_points, min_periods=max(1, window_points // 2)
            ).mean()
            series_out = series_out.where(nonzero >= min_nonzero_fraction)
        if zero_as_nan:
            series_out = series_out.mask(series_out == 0)
        updated[key] = series_out
    return updated


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


def run_seismic_demo(
    project_root: Path,
    start: str,
    days: int,
    config_path: Path,
    min_magnitude: float = 2.5,
    bbox: tuple[float, float, float, float] | None = None,
    transform: str | None = None,
    zero_as_nan: bool = False,
    min_nonzero_fraction: float | None = None,
):
    from .config import load_config

    config = load_config(config_path)
    freq = config.get("freq") or "1h"

    start_dt, end_dt = parse_start_end(start, days)
    cache_dir = project_root / "data" / "cache" / "seismic"

    events = fetch_earthquake_events(start_dt, end_dt, min_magnitude, cache_dir, bbox=bbox)
    series_map = build_seismic_series(events, freq)
    series_map = _apply_seismic_transform(series_map, transform)
    window_points = max(config.get("window_sizes", [1]))
    series_map = _apply_zero_policy(
        series_map,
        zero_as_nan=zero_as_nan,
        min_nonzero_fraction=min_nonzero_fraction,
        window_points=window_points,
    )
    if not series_map:
        raise RuntimeError("No seismic series built from USGS data.")

    aligned = _align_series(series_map)
    if not aligned:
        raise RuntimeError("Failed to align seismic series.")

    sources = []
    for source_id, series in aligned.items():
        sources.append(
            SeriesData(
                source_id=source_id,
                domain_id="seismic",
                timestamps=series.index.to_numpy(),
                values=series.to_numpy(dtype=float),
                quality=None,
                path=None,
            )
        )

    run_dir = make_run_dir(project_root / "runs")
    results, events_out = run_pipeline(sources, config, run_dir, return_events=True)

    inputs_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": USGS_QUAKE_URL,
        "start": format_timestamp(start_dt),
        "end": format_timestamp(end_dt),
        "days": days,
        "freq": freq,
        "min_magnitude": min_magnitude,
        "bbox": bbox,
        "transform": (transform or "identity").strip().lower(),
        "zero_as_nan": bool(zero_as_nan),
        "min_nonzero_fraction": min_nonzero_fraction,
    }
    inputs_path = run_dir / "inputs_seismic.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    time_range = f"{format_timestamp(start_dt)} -> {format_timestamp(end_dt)}"

    print("Seismic demo run:", run_dir)
    print(f"Time range: {time_range}")
    if stats:
        print(
            f"Points: {stats.get('total_points')} | Windows: {stats.get('total_windows')} | Candidates: {stats.get('total_candidates')} | Events: {stats.get('total_events')}"
        )

    cross_domain_events = [evt for evt in events_out if evt.cross_domain_edges_count > 0]
    same_domain_events = [evt for evt in events_out if evt.cross_domain_edges_count == 0]
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


def _is_cross_domain_event(event):
    return "seismic" in event.domains_involved and any(
        domain.startswith("omni_") for domain in event.domains_involved
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
        "seismic_shift_days": shift_days,
        "seismic_shift_hours": shift_hours,
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


def run_omni_seismic_control(
    project_root: Path,
    start: str,
    days: int,
    config_path: Path,
    min_magnitude: float = 2.5,
    bbox: tuple[float, float, float, float] | None = None,
    seismic_shift_days: int = 13,
    seismic_shift_hours: int | None = None,
    seismic_shift_list: list[int] | None = None,
    repeat: int = 1,
    seismic_transform: str | None = None,
    seismic_zero_as_nan: bool = False,
    seismic_min_nonzero_fraction: float | None = None,
):
    from .config import load_config

    config = load_config(config_path)
    freq = config.get("freq") or "1h"

    start_dt, end_dt = parse_start_end(start, days)
    cache_dir_hapi = project_root / "data" / "cache" / "hapi"
    cache_dir_seismic = project_root / "data" / "cache" / "seismic"

    def _build_sources(seismic_offset: str | None):
        df_omni = fetch_data(
            OMNI_BASE_URL,
            OMNI_DATASET_ID,
            start_dt,
            end_dt,
            OMNI_PARAMETERS,
            cache_dir_hapi,
            chunk_days=7,
        )
        if df_omni.empty:
            raise RuntimeError("No OMNI data returned from HAPI.")
        time_col = OMNI_PARAMETERS[0]
        df_omni[time_col] = pd.to_datetime(df_omni[time_col], utc=True, errors="coerce")
        df_omni = df_omni.dropna(subset=[time_col])

        omni_map = {
            "omni_bz_gsm": df_omni.set_index(time_col)["BZ_GSM"].resample(freq).mean(),
            "omni_flow_speed": df_omni.set_index(time_col)["flow_speed"].resample(freq).mean(),
            "omni_proton_density": df_omni.set_index(time_col)["proton_density"].resample(freq).mean(),
            "omni_sym_h": df_omni.set_index(time_col)["SYM_H"].resample(freq).mean(),
        }

        events = fetch_earthquake_events(start_dt, end_dt, min_magnitude, cache_dir_seismic, bbox=bbox)
        series_map = build_seismic_series(events, freq)
        series_map = _apply_seismic_transform(series_map, seismic_transform)
        window_points = max(config.get("window_sizes", [1]))
        series_map = _apply_zero_policy(
            series_map,
            zero_as_nan=seismic_zero_as_nan,
            min_nonzero_fraction=seismic_min_nonzero_fraction,
            window_points=window_points,
        )
        if not series_map:
            raise RuntimeError("No seismic series built from USGS data.")

        if seismic_offset:
            delta = parse_time_offset(seismic_offset)
            if delta != pd.Timedelta(0):
                for key in list(series_map.keys()):
                    series_map[key] = series_map[key].copy()
                    series_map[key].index = series_map[key].index + delta

        series_map.update(omni_map)

        aligned = _align_series(series_map)
        if not aligned:
            raise RuntimeError("Failed to align OMNI and seismic sources.")

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
            SeriesData(
                source_id="seismic_count",
                domain_id="seismic",
                timestamps=aligned["seismic_count"].index.to_numpy(),
                values=aligned["seismic_count"].to_numpy(dtype=float),
                quality=None,
                path=None,
            ),
            SeriesData(
                source_id="seismic_energy",
                domain_id="seismic",
                timestamps=aligned["seismic_energy"].index.to_numpy(),
                values=aligned["seismic_energy"].to_numpy(dtype=float),
                quality=None,
                path=None,
            ),
        ]
        return sources

    def _run_single(seismic_offset: str | None, shift_days: int, shift_hours: int | None):
        sources = _build_sources(seismic_offset)
        run_dir = make_run_dir(project_root / "runs")
        results, events = run_pipeline(sources, config, run_dir, return_events=True)

        inputs_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start": format_timestamp(start_dt),
            "end": format_timestamp(end_dt),
            "days": days,
            "freq": freq,
            "min_magnitude": min_magnitude,
            "bbox": bbox,
            "seismic": {
                "time_offset": seismic_offset or "0",
                "transform": (seismic_transform or "identity").strip().lower(),
                "zero_as_nan": bool(seismic_zero_as_nan),
                "min_nonzero_fraction": seismic_min_nonzero_fraction,
            },
        }
        inputs_path = run_dir / "inputs_omni_seismic.json"
        inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

        metrics = _cross_domain_metrics(events)
        _write_control_report(run_dir, metrics, shift_days, shift_hours)
        return run_dir, metrics

    print("OMNI+Seismic control (REAL):")
    run_dir_real, metrics_real = _run_single(None, 0, 0)

    shift_specs = []
    if seismic_shift_list:
        for days in seismic_shift_list:
            shift_specs.append(
                {
                    "offset": f"+{int(days)}d",
                    "shift_days": int(days),
                    "shift_hours": None,
                }
            )
    else:
        repeat = max(1, int(repeat))
        if seismic_shift_hours is not None:
            base = int(seismic_shift_hours)
            for idx in range(1, repeat + 1):
                shift_specs.append(
                    {
                        "offset": f"+{base * idx}h",
                        "shift_days": 0,
                        "shift_hours": base * idx,
                    }
                )
        else:
            base = int(seismic_shift_days)
            for idx in range(1, repeat + 1):
                shift_specs.append(
                    {
                        "offset": f"+{base * idx}d",
                        "shift_days": base * idx,
                        "shift_hours": None,
                    }
                )

    shift_runs = []
    print("OMNI+Seismic control (SHIFT):")
    for spec in shift_specs:
        run_dir_shift, metrics_shift = _run_single(
            spec["offset"], spec["shift_days"], spec["shift_hours"]
        )
        shift_runs.append({"run_dir": run_dir_shift, "metrics": metrics_shift, "spec": spec})

    summary_real = _summarize_for_compare(metrics_real)
    shift_summaries = []
    overlap_flags = []
    for item in shift_runs:
        summary = _summarize_for_compare(item["metrics"])
        overlap_ratio = None
        overlap_over_50 = False
        real_event = metrics_real["best_cross_domain_event"]
        shift_event = item["metrics"]["best_cross_domain_event"]
        if real_event is not None and shift_event is not None:
            real_start = pd.to_datetime(real_event.event_start, utc=True, errors="coerce")
            real_end = pd.to_datetime(real_event.event_end, utc=True, errors="coerce")
            shift_start = pd.to_datetime(shift_event.event_start, utc=True, errors="coerce")
            shift_end = pd.to_datetime(shift_event.event_end, utc=True, errors="coerce")
            if (
                not pd.isna(real_start)
                and not pd.isna(real_end)
                and not pd.isna(shift_start)
                and not pd.isna(shift_end)
            ):
                overlap = max(pd.Timedelta(0), min(real_end, shift_end) - max(real_start, shift_start))
                duration = real_end - real_start
                if duration > pd.Timedelta(0):
                    overlap_ratio = overlap / duration
                    overlap_over_50 = overlap_ratio > 0.5
        overlap_flags.append(overlap_over_50)
        shift_summaries.append(
            {
                "run_id": item["run_dir"].name,
                "shift_days": item["spec"]["shift_days"],
                "shift_hours": item["spec"]["shift_hours"],
                "summary": summary,
                "overlap_ratio": float(overlap_ratio) if overlap_ratio is not None else None,
                "overlap_over_50": overlap_over_50,
            }
        )

    shift_counts = [entry["summary"]["cross_domain_events_count"] for entry in shift_summaries]
    shift_scores = [entry["summary"]["best_cross_domain_event_score"] for entry in shift_summaries]
    p90_count = float(np.quantile(shift_counts, 0.9)) if shift_counts else 0.0
    p90_score = float(np.quantile(shift_scores, 0.9)) if shift_scores else 0.0
    above90 = (summary_real["cross_domain_events_count"] > p90_count) or (
        summary_real["best_cross_domain_event_score"] > p90_score
    )
    overlap_suspect = any(overlap_flags)
    if summary_real["cross_domain_events_count"] == 0:
        verdict = "OK: no cross-domain events in REAL"
    elif above90 and not overlap_suspect:
        verdict = "OK: REAL exceeds shift baseline"
    elif overlap_suspect:
        verdict = "SUSPECT: top-event overlaps with shifted runs"
    else:
        verdict = "SUSPECT: REAL not above shift baseline"

    compare_payload = {
        "control_type": "seismic",
        "run_id_real": run_dir_real.name,
        "real": summary_real,
        "shift_runs": shift_summaries,
        "p90_shift": {
            "cross_domain_events_count": p90_count,
            "best_cross_domain_event_score": p90_score,
        },
        "verdict": verdict,
    }
    compare_path = run_dir_real / "control_compare.json"
    compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")

    print("Compare REAL vs SHIFT:")
    print("  p90 cross_domain_events_count:", p90_count)
    print("  p90 best_cross_domain_event_score:", p90_score)
    if verdict.startswith("SUSPECT"):
        print("WARNING:", verdict)
    else:
        print(verdict)

    return run_dir_real, [entry["run_dir"] for entry in shift_runs]
