import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .hapi import fetch_data, parse_start_end
from .io import SeriesData, format_timestamp
from .nmdb import DEFAULT_DTYPE, DEFAULT_TABCHOICE, DEFAULT_YUNITS, fetch_nmdb
from .omni import OMNI_BASE_URL, OMNI_DATASET_ID, OMNI_PARAMETERS
from .pipeline import make_run_dir, run_pipeline
from .time_utils import parse_time_offset

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


def build_omni_nmdb_sources(
    cache_dir_hapi: Path,
    cache_dir_nmdb: Path,
    start: str,
    days: int,
    stations: list[str],
    freq: str,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    dtype: str = DEFAULT_DTYPE,
    tabchoice: str = DEFAULT_TABCHOICE,
    yunits: int = DEFAULT_YUNITS,
    nmdb_time_offset: str | None = None,
    base_url: str = OMNI_BASE_URL,
    dataset_id: str = OMNI_DATASET_ID,
):
    start_dt, end_dt = parse_start_end(start, days)

    df_omni = fetch_data(
        base_url,
        dataset_id,
        start_dt,
        end_dt,
        OMNI_PARAMETERS,
        cache_dir_hapi,
        chunk_days=chunk_days,
    )
    if df_omni.empty:
        raise RuntimeError("No OMNI data returned from HAPI.")

    time_col = OMNI_PARAMETERS[0]
    df_omni[time_col] = pd.to_datetime(df_omni[time_col], utc=True, errors="coerce")
    df_omni = df_omni.dropna(subset=[time_col])

    required_cols = ["BZ_GSM", "flow_speed", "proton_density", "SYM_H"]
    for col in required_cols:
        if col not in df_omni.columns:
            raise RuntimeError(f"OMNI data missing column '{col}'.")

    omni_map = {
        "omni_bz_gsm": df_omni.set_index(time_col)["BZ_GSM"].resample(freq).mean(),
        "omni_flow_speed": df_omni.set_index(time_col)["flow_speed"].resample(freq).mean(),
        "omni_proton_density": df_omni.set_index(time_col)["proton_density"].resample(freq).mean(),
        "omni_sym_h": df_omni.set_index(time_col)["SYM_H"].resample(freq).mean(),
    }

    df_nmdb = fetch_nmdb(
        stations=stations,
        start=start_dt,
        end=end_dt,
        dtype=dtype,
        tabchoice=tabchoice,
        yunits=yunits,
        cache_dir=cache_dir_nmdb,
    )
    if df_nmdb.empty or "Time" not in df_nmdb.columns:
        raise RuntimeError("No NMDB data returned.")

    df_nmdb["Time"] = pd.to_datetime(df_nmdb["Time"], utc=True, errors="coerce")
    df_nmdb = df_nmdb.dropna(subset=["Time"])
    if nmdb_time_offset:
        delta = parse_time_offset(nmdb_time_offset)
        if delta != pd.Timedelta(0):
            df_nmdb["Time"] = df_nmdb["Time"] + delta

    nmdb_map = {}
    for station in [col for col in df_nmdb.columns if col != "Time"]:
        series = df_nmdb.set_index("Time")[station].resample(freq).mean()
        nmdb_map[f"nmdb_{station}"] = series

    series_map = {}
    series_map.update(omni_map)
    series_map.update(nmdb_map)

    aligned = _align_series(series_map)
    if not aligned:
        raise RuntimeError("Failed to align OMNI and NMDB sources.")

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

    for station in nmdb_map:
        sources.append(
            SeriesData(
                source_id=station,
                domain_id="nmdb_cosmicray",
                timestamps=aligned[station].index.to_numpy(),
                values=aligned[station].to_numpy(dtype=float),
                quality=None,
                path=None,
            )
        )

    return sources, start_dt, end_dt


def run_omni_nmdb_demo(
    project_root: Path,
    start: str,
    days: int,
    stations: list[str],
    config_path: Path,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    dtype: str = DEFAULT_DTYPE,
    tabchoice: str = DEFAULT_TABCHOICE,
    yunits: int = DEFAULT_YUNITS,
    nmdb_time_offset: str | None = None,
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

    cache_dir_hapi = project_root / "data" / "cache" / "hapi"
    cache_dir_nmdb = project_root / "data" / "cache" / "nmdb"

    sources, start_dt, end_dt = build_omni_nmdb_sources(
        cache_dir_hapi,
        cache_dir_nmdb,
        start,
        days,
        stations,
        freq,
        chunk_days=chunk_days,
        dtype=dtype,
        tabchoice=tabchoice,
        yunits=yunits,
        nmdb_time_offset=nmdb_time_offset,
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
        "stations": stations,
        "nmdb": {
            "dtype": dtype,
            "tabchoice": tabchoice,
            "yunits": yunits,
            "time_offset": nmdb_time_offset or "0",
        },
    }
    if holdout_ratio is not None:
        inputs_payload["holdout_ratio"] = float(holdout_ratio)
    if holdout_mode is not None:
        inputs_payload["holdout_mode"] = holdout_mode
    inputs_path = run_dir / "inputs_omni_nmdb.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    time_range = f"{format_timestamp(start_dt)} -> {format_timestamp(end_dt)}"

    print("OMNI+NMDB demo run:", run_dir)
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


def _best_nmdb_edge(results):
    for item in results:
        if item.anchor_source_id.startswith("nmdb_") or item.other_source_id.startswith("nmdb_"):
            return item
    return None


def _nmdb_metrics(events, results):
    events_with_nmdb = [
        evt for evt in events if any(src.startswith("nmdb_") for src in evt.sources_involved)
    ]
    top_events = sorted(events, key=lambda evt: evt.event_score, reverse=True)[:10]
    nmdb_in_top10 = [
        evt for evt in top_events if any(src.startswith("nmdb_") for src in evt.sources_involved)
    ]
    best_event = max(events_with_nmdb, key=lambda evt: evt.event_score, default=None)
    best_edge = _best_nmdb_edge(results)
    return {
        "events_with_nmdb_count": len(events_with_nmdb),
        "nmdb_in_top10_count": len(nmdb_in_top10),
        "best_nmdb_event": best_event,
        "best_nmdb_edge": best_edge,
    }


def _write_control_report(run_dir: Path, metrics: dict, shift_days: int):
    best_event = metrics["best_nmdb_event"]
    best_edge = metrics["best_nmdb_edge"]
    payload = {
        "run_id": run_dir.name,
        "nmdb_shift_days": shift_days,
        "events_with_nmdb_count": metrics["events_with_nmdb_count"],
        "nmdb_in_top10_count": metrics["nmdb_in_top10_count"],
        "best_nmdb_event": None,
        "best_nmdb_edge": None,
    }
    if best_event is not None:
        payload["best_nmdb_event"] = {
            "event_id": best_event.event_id,
            "event_start": format_timestamp(best_event.event_start),
            "event_end": format_timestamp(best_event.event_end),
            "event_score": best_event.event_score,
            "best_nms": best_event.best_nms,
            "best_p_value": best_event.best_p_value,
            "edge_novelty_sum": best_event.edge_novelty_sum,
            "orphan_score": best_event.orphan_score,
        }
    if best_edge is not None:
        payload["best_nmdb_edge"] = {
            "anchor_source_id": best_edge.anchor_source_id,
            "other_source_id": best_edge.other_source_id,
            "window_size": best_edge.window_size,
            "nms": best_edge.nms,
            "p_value": best_edge.p_value,
            "best_shift": best_edge.best_shift,
            "pair_valid_fraction": best_edge.pair_valid_fraction,
            "anchor_valid_fraction": best_edge.anchor_valid_fraction,
            "other_valid_fraction": best_edge.other_valid_fraction,
        }
    report_path = run_dir / "control_report.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def _print_run_summary(run_dir: Path, metrics: dict, total_events: int):
    print(f"Run: {run_dir}")
    print(f"  total_events: {total_events}")
    print(f"  events_with_nmdb_count: {metrics['events_with_nmdb_count']}")
    print(f"  nmdb_in_top10_count: {metrics['nmdb_in_top10_count']}")
    best_event = metrics["best_nmdb_event"]
    if best_event is not None:
        print(
            "  best_nmdb_event:",
            f"{best_event.event_id} {format_timestamp(best_event.event_start)} -> {format_timestamp(best_event.event_end)}",
            f"score={best_event.event_score:.3f} nms={best_event.best_nms:.3f} p_value={best_event.best_p_value:.3f}",
            f"edge_novelty_sum={best_event.edge_novelty_sum:.1f} orphan={best_event.orphan_score:.1f}",
        )
    else:
        print("  best_nmdb_event: none")
    best_edge = metrics["best_nmdb_edge"]
    if best_edge is not None:
        pair = f"{best_edge.anchor_source_id} vs {best_edge.other_source_id}"
        print(
            "  best_nmdb_edge:",
            f"{pair} window={best_edge.window_size}",
            f"nms={best_edge.nms:.3f} p_value={best_edge.p_value:.3f} shift={best_edge.best_shift}",
            f"pair_valid_fraction={best_edge.pair_valid_fraction:.3f}",
        )
    else:
        print("  best_nmdb_edge: none")


def _summarize_for_compare(metrics: dict):
    best_event = metrics["best_nmdb_event"]
    best_edge = metrics["best_nmdb_edge"]
    return {
        "events_with_nmdb_count": metrics["events_with_nmdb_count"],
        "nmdb_in_top10_count": metrics["nmdb_in_top10_count"],
        "best_nmdb_event_score": best_event.event_score if best_event is not None else 0.0,
        "best_nmdb_edge_nms": best_edge.nms if best_edge is not None else 0.0,
        "best_nmdb_edge_p_value": best_edge.p_value if best_edge is not None else 1.0,
    }


def _compare_verdict(real_summary: dict, shift_summary: dict):
    real_events = real_summary["events_with_nmdb_count"]
    real_top = real_summary["nmdb_in_top10_count"]
    shift_events = shift_summary["events_with_nmdb_count"]
    shift_top = shift_summary["nmdb_in_top10_count"]

    if real_events == 0:
        return "OK: NMDB almost never participates"

    drop_events = shift_events <= real_events // 2
    drop_top = shift_top <= real_top // 2
    if drop_events and drop_top:
        return "OK: NMDB participation drops under shift"
    return "SUSPECT: NMDB participates similarly under shift"


def run_omni_nmdb_control(
    project_root: Path,
    start: str,
    days: int,
    stations: list[str],
    config_path: Path,
    nmdb_shift_days: int = 13,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    dtype: str = DEFAULT_DTYPE,
    tabchoice: str = DEFAULT_TABCHOICE,
    yunits: int = DEFAULT_YUNITS,
):
    from .config import load_config

    config = load_config(config_path)
    freq = config.get("freq") or "1min"

    cache_dir_hapi = project_root / "data" / "cache" / "hapi"
    cache_dir_nmdb = project_root / "data" / "cache" / "nmdb"

    def _run_single(time_offset: str | None, shift_days: int):
        sources, start_dt, end_dt = build_omni_nmdb_sources(
            cache_dir_hapi,
            cache_dir_nmdb,
            start,
            days,
            stations,
            freq,
            chunk_days=chunk_days,
            dtype=dtype,
            tabchoice=tabchoice,
            yunits=yunits,
            nmdb_time_offset=time_offset,
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
            "stations": stations,
            "nmdb": {
                "dtype": dtype,
                "tabchoice": tabchoice,
                "yunits": yunits,
                "time_offset": time_offset or "0",
            },
        }
        inputs_path = run_dir / "inputs_omni_nmdb.json"
        inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

        metrics = _nmdb_metrics(events, results)
        _write_control_report(run_dir, metrics, shift_days)
        _print_run_summary(run_dir, metrics, total_events=len(events))
        return run_dir, metrics

    print("OMNI+NMDB control (REAL):")
    run_dir_real, metrics_real = _run_single(None, 0)

    shift_offset = f"+{int(nmdb_shift_days)}d"
    print("OMNI+NMDB control (SHIFT):")
    run_dir_shift, metrics_shift = _run_single(shift_offset, int(nmdb_shift_days))

    summary_real = _summarize_for_compare(metrics_real)
    summary_shift = _summarize_for_compare(metrics_shift)
    verdict = _compare_verdict(summary_real, summary_shift)
    compare_payload = {
        "control_type": "nmdb",
        "run_id_real": run_dir_real.name,
        "run_id_shift": run_dir_shift.name,
        "nmdb_shift_days": int(nmdb_shift_days),
        "real": summary_real,
        "shift": summary_shift,
        "delta": {
            "events_with_nmdb_count": summary_real["events_with_nmdb_count"]
            - summary_shift["events_with_nmdb_count"],
            "nmdb_in_top10_count": summary_real["nmdb_in_top10_count"]
            - summary_shift["nmdb_in_top10_count"],
        },
        "verdict": verdict,
    }
    compare_path = run_dir_real / "control_compare.json"
    compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")

    print("Compare REAL vs SHIFT:")
    print(
        "  delta events_with_nmdb_count:",
        compare_payload["delta"]["events_with_nmdb_count"],
    )
    print(
        "  delta nmdb_in_top10_count:",
        compare_payload["delta"]["nmdb_in_top10_count"],
    )
    if verdict.startswith("SUSPECT"):
        print("WARNING:", verdict)
    else:
        print(verdict)

    return run_dir_real, run_dir_shift
