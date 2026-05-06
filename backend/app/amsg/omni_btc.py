import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .btc_csv import load_btc_csv
from .io import SeriesData, format_timestamp
from .omni import DEFAULT_CHUNK_DAYS, OMNI_BASE_URL, OMNI_DATASET_ID, OMNI_PARAMETERS, build_omni_sources
from .pipeline import make_run_dir, run_pipeline


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


def build_omni_btc_sources(
    cache_dir: Path,
    start: str,
    days: int,
    freq: str,
    btc_csv: Path,
    btc_time_col: str,
    btc_price_col: str,
    btc_volume_col: str | None,
    btc_transform: str | None,
    btc_time_offset: str | None,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
):
    omni_sources, start_dt, end_dt = build_omni_sources(
        cache_dir,
        start,
        days,
        freq,
        chunk_days=chunk_days,
    )

    series_map = {}
    domain_map = {}
    for source in omni_sources:
        times = pd.to_datetime(source.timestamps, utc=True, errors="coerce")
        series_map[source.source_id] = pd.Series(source.values, index=times).sort_index()
        domain_map[source.source_id] = source.domain_id

    btc_series = load_btc_csv(
        btc_csv,
        time_col=btc_time_col,
        price_col=btc_price_col,
        volume_col=btc_volume_col,
        transform=btc_transform,
        time_offset=btc_time_offset,
    ).sort_index()

    if start_dt and end_dt:
        start_ts = pd.to_datetime(start_dt, utc=True, errors="coerce")
        end_ts = pd.to_datetime(end_dt, utc=True, errors="coerce")
        if not pd.isna(start_ts) and not pd.isna(end_ts):
            btc_series = btc_series.loc[start_ts:end_ts]

    btc_series = btc_series.resample(freq).mean()
    series_map["btc_usd"] = btc_series
    domain_map["btc_usd"] = "finance"

    aligned = _align_series(series_map)
    if not aligned:
        raise RuntimeError("Failed to align OMNI and BTC sources.")

    sources = []
    for source_id, series in aligned.items():
        sources.append(
            SeriesData(
                source_id=source_id,
                domain_id=domain_map[source_id],
                timestamps=series.index.to_numpy(),
                values=series.to_numpy(dtype=float),
                quality=None,
                path=None,
            )
        )

    return sources, start_dt, end_dt


def _best_btc_edge(results):
    for item in results:
        if item.anchor_source_id == "btc_usd" or item.other_source_id == "btc_usd":
            return item
    return None


def _btc_metrics(events, results):
    events_with_btc = [evt for evt in events if "btc_usd" in evt.sources_involved]
    top_events = sorted(events, key=lambda evt: evt.event_score, reverse=True)[:10]
    btc_in_top10 = [evt for evt in top_events if "btc_usd" in evt.sources_involved]
    best_event = max(events_with_btc, key=lambda evt: evt.event_score, default=None)
    best_edge = _best_btc_edge(results)
    return {
        "events_with_btc_count": len(events_with_btc),
        "btc_in_top10_count": len(btc_in_top10),
        "best_btc_event": best_event,
        "best_btc_edge": best_edge,
    }


def _write_control_report(run_dir: Path, metrics: dict, shift_days: int):
    best_event = metrics["best_btc_event"]
    best_edge = metrics["best_btc_edge"]
    payload = {
        "run_id": run_dir.name,
        "btc_shift_days": shift_days,
        "events_with_btc_count": metrics["events_with_btc_count"],
        "btc_in_top10_count": metrics["btc_in_top10_count"],
        "best_btc_event": None,
        "best_btc_edge": None,
    }
    if best_event is not None:
        payload["best_btc_event"] = {
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
        payload["best_btc_edge"] = {
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
    print(f"  events_with_btc_count: {metrics['events_with_btc_count']}")
    print(f"  btc_in_top10_count: {metrics['btc_in_top10_count']}")
    best_event = metrics["best_btc_event"]
    if best_event is not None:
        print(
            "  best_btc_event:",
            f"{best_event.event_id} {format_timestamp(best_event.event_start)} -> {format_timestamp(best_event.event_end)}",
            f"score={best_event.event_score:.3f} nms={best_event.best_nms:.3f} p_value={best_event.best_p_value:.3f}",
            f"edge_novelty_sum={best_event.edge_novelty_sum:.1f} orphan={best_event.orphan_score:.1f}",
        )
    else:
        print("  best_btc_event: none")
    best_edge = metrics["best_btc_edge"]
    if best_edge is not None:
        pair = f"{best_edge.anchor_source_id} vs {best_edge.other_source_id}"
        print(
            "  best_btc_edge:",
            f"{pair} window={best_edge.window_size}",
            f"nms={best_edge.nms:.3f} p_value={best_edge.p_value:.3f} shift={best_edge.best_shift}",
            f"pair_valid_fraction={best_edge.pair_valid_fraction:.3f}",
        )
    else:
        print("  best_btc_edge: none")


def _summarize_for_compare(metrics: dict):
    best_event = metrics["best_btc_event"]
    best_edge = metrics["best_btc_edge"]
    return {
        "events_with_btc_count": metrics["events_with_btc_count"],
        "btc_in_top10_count": metrics["btc_in_top10_count"],
        "best_btc_event_score": best_event.event_score if best_event is not None else 0.0,
        "best_btc_edge_nms": best_edge.nms if best_edge is not None else 0.0,
        "best_btc_edge_p_value": best_edge.p_value if best_edge is not None else 1.0,
    }


def _compare_verdict(real_summary: dict, shift_summary: dict):
    suspect = (
        real_summary["events_with_btc_count"] > 0
        and shift_summary["events_with_btc_count"] > 0
        and abs(real_summary["events_with_btc_count"] - shift_summary["events_with_btc_count"]) <= 1
        and abs(real_summary["btc_in_top10_count"] - shift_summary["btc_in_top10_count"]) <= 1
    )
    if suspect:
        return "SUSPECT: BTC participates similarly under shift"
    if real_summary["events_with_btc_count"] == 0 and shift_summary["events_with_btc_count"] == 0:
        return "OK: BTC almost never participates"
    return "OK: BTC participation changes under shift"


def run_omni_btc_control(
    project_root: Path,
    start: str,
    days: int,
    btc_csv: Path,
    config_path: Path,
    btc_time_col: str = "time",
    btc_price_col: str = "close",
    btc_volume_col: str | None = None,
    btc_transform: str | None = "log_return",
    btc_shift_days: int = 13,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    freq: str | None = None,
    top_p: float | None = None,
    window_sizes: list[int] | None = None,
    null_shifts_count: int | None = None,
):
    from .config import load_config

    config = load_config(config_path)
    if freq:
        config["freq"] = freq
    if top_p is not None:
        config["top_p"] = float(top_p)
    if window_sizes:
        config["window_sizes"] = [int(value) for value in window_sizes]
    if null_shifts_count is not None:
        config["null_shifts_count"] = int(null_shifts_count)

    freq = config.get("freq") or "1min"
    cache_dir = project_root / "data" / "cache" / "hapi"

    def _run_single(time_offset: str | None, shift_days: int):
        sources, start_dt, end_dt = build_omni_btc_sources(
            cache_dir,
            start,
            days,
            freq,
            btc_csv,
            btc_time_col,
            btc_price_col,
            btc_volume_col,
            btc_transform,
            time_offset,
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
            "btc": {
                "path": str(Path(btc_csv).resolve()),
                "time_col": btc_time_col,
                "price_col": btc_price_col,
                "volume_col": btc_volume_col,
                "transform": btc_transform,
                "time_offset": time_offset or "0",
                "domain_id": "finance",
                "source_id": "btc_usd",
            },
        }
        inputs_path = run_dir / "inputs_omni_btc.json"
        inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

        metrics = _btc_metrics(events, results)
        _write_control_report(run_dir, metrics, shift_days)
        _print_run_summary(run_dir, metrics, total_events=len(events))
        return run_dir, metrics

    print("OMNI+BTC control (REAL):")
    run_dir_real, metrics_real = _run_single(None, 0)

    shift_offset = f"+{int(btc_shift_days)}d"
    print("OMNI+BTC control (SHIFT):")
    run_dir_shift, metrics_shift = _run_single(shift_offset, int(btc_shift_days))

    summary_real = _summarize_for_compare(metrics_real)
    summary_shift = _summarize_for_compare(metrics_shift)
    verdict = _compare_verdict(summary_real, summary_shift)
    compare_payload = {
        "control_type": "btc",
        "run_id_real": run_dir_real.name,
        "run_id_shift": run_dir_shift.name,
        "btc_shift_days": int(btc_shift_days),
        "real": summary_real,
        "shift": summary_shift,
        "delta": {
            "events_with_btc_count": summary_real["events_with_btc_count"]
            - summary_shift["events_with_btc_count"],
            "btc_in_top10_count": summary_real["btc_in_top10_count"]
            - summary_shift["btc_in_top10_count"],
        },
        "verdict": verdict,
    }
    compare_path = run_dir_real / "control_compare.json"
    compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")

    print("Compare REAL vs SHIFT:")
    print(
        "  delta events_with_btc_count:",
        compare_payload["delta"]["events_with_btc_count"],
    )
    print(
        "  delta btc_in_top10_count:",
        compare_payload["delta"]["btc_in_top10_count"],
    )
    if verdict.startswith("SUSPECT"):
        print("WARNING:", verdict)
    else:
        print(verdict)

    return run_dir_real, run_dir_shift
