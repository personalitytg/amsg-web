import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .io import SeriesData, format_timestamp
from .omni import DEFAULT_CHUNK_DAYS, OMNI_BASE_URL, OMNI_DATASET_ID, OMNI_PARAMETERS, build_omni_sources
from .pageviews import (
    fetch_pageviews_series,
    pageviews_source_id,
    apply_pageviews_time_offset,
    resample_pageviews_series,
)
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


def build_omni_pageviews_sources(
    cache_dir: Path,
    start: str,
    days: int,
    freq: str,
    articles: list[str],
    project: str,
    access: str,
    agent: str,
    granularity: str,
    pageviews_time_offset: str | None,
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

    pageviews_map = {}
    for article in articles:
        series = fetch_pageviews_series(
            project,
            access,
            agent,
            article,
            granularity,
            start_dt,
            end_dt,
            cache_dir.parent / "pageviews",
        )
        if series is None:
            continue
        source_id = pageviews_source_id(article)
        pageviews_map[source_id] = resample_pageviews_series(series, freq, granularity)
        domain_map[source_id] = "human_activity"

    if not pageviews_map:
        raise RuntimeError("No pageviews data returned.")

    pageviews_map = apply_pageviews_time_offset(pageviews_map, pageviews_time_offset)
    series_map.update(pageviews_map)

    aligned = _align_series(series_map)
    if not aligned:
        raise RuntimeError("Failed to align OMNI and pageviews sources.")

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


def _best_pageviews_edge(results):
    for item in results:
        if item.anchor_source_id.startswith("wiki_") or item.other_source_id.startswith("wiki_"):
            return item
    return None


def _pageviews_metrics(events, results):
    events_with_pageviews = [
        evt for evt in events if any(src.startswith("wiki_") for src in evt.sources_involved)
    ]
    top_events = sorted(events, key=lambda evt: evt.event_score, reverse=True)[:10]
    pageviews_in_top10 = [
        evt for evt in top_events if any(src.startswith("wiki_") for src in evt.sources_involved)
    ]
    best_event = max(events_with_pageviews, key=lambda evt: evt.event_score, default=None)
    best_edge = _best_pageviews_edge(results)
    return {
        "events_with_pageviews_count": len(events_with_pageviews),
        "pageviews_in_top10_count": len(pageviews_in_top10),
        "best_pageviews_event": best_event,
        "best_pageviews_edge": best_edge,
    }


def _write_control_report(run_dir: Path, metrics: dict, shift_days: int):
    best_event = metrics["best_pageviews_event"]
    best_edge = metrics["best_pageviews_edge"]
    payload = {
        "run_id": run_dir.name,
        "pageviews_shift_days": shift_days,
        "events_with_pageviews_count": metrics["events_with_pageviews_count"],
        "pageviews_in_top10_count": metrics["pageviews_in_top10_count"],
        "best_pageviews_event": None,
        "best_pageviews_edge": None,
    }
    if best_event is not None:
        payload["best_pageviews_event"] = {
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
        payload["best_pageviews_edge"] = {
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
    print(f"  events_with_pageviews_count: {metrics['events_with_pageviews_count']}")
    print(f"  pageviews_in_top10_count: {metrics['pageviews_in_top10_count']}")
    best_event = metrics["best_pageviews_event"]
    if best_event is not None:
        print(
            "  best_pageviews_event:",
            f"{best_event.event_id} {format_timestamp(best_event.event_start)} -> {format_timestamp(best_event.event_end)}",
            f"score={best_event.event_score:.3f} nms={best_event.best_nms:.3f} p_value={best_event.best_p_value:.3f}",
            f"edge_novelty_sum={best_event.edge_novelty_sum:.1f} orphan={best_event.orphan_score:.1f}",
        )
    else:
        print("  best_pageviews_event: none")
    best_edge = metrics["best_pageviews_edge"]
    if best_edge is not None:
        pair = f"{best_edge.anchor_source_id} vs {best_edge.other_source_id}"
        print(
            "  best_pageviews_edge:",
            f"{pair} window={best_edge.window_size}",
            f"nms={best_edge.nms:.3f} p_value={best_edge.p_value:.3f} shift={best_edge.best_shift}",
            f"pair_valid_fraction={best_edge.pair_valid_fraction:.3f}",
        )
    else:
        print("  best_pageviews_edge: none")


def _summarize_for_compare(metrics: dict):
    best_event = metrics["best_pageviews_event"]
    best_edge = metrics["best_pageviews_edge"]
    return {
        "events_with_pageviews_count": metrics["events_with_pageviews_count"],
        "pageviews_in_top10_count": metrics["pageviews_in_top10_count"],
        "best_pageviews_event_score": best_event.event_score if best_event is not None else 0.0,
        "best_pageviews_edge_nms": best_edge.nms if best_edge is not None else 0.0,
        "best_pageviews_edge_p_value": best_edge.p_value if best_edge is not None else 1.0,
    }


def _compare_verdict(real_summary: dict, shift_summary: dict):
    real_events = real_summary["events_with_pageviews_count"]
    real_top = real_summary["pageviews_in_top10_count"]
    shift_events = shift_summary["events_with_pageviews_count"]
    shift_top = shift_summary["pageviews_in_top10_count"]

    if real_events == 0:
        return "OK: pageviews almost never participates"

    drop_events = shift_events <= real_events // 2
    drop_top = shift_top <= real_top // 2
    if drop_events and drop_top:
        return "OK: pageviews participation drops under shift"
    return "SUSPECT: pageviews participates similarly under shift"


def run_omni_pageviews_control(
    project_root: Path,
    start: str,
    days: int,
    articles: list[str],
    config_path: Path,
    project: str = "en.wikipedia",
    access: str = "all-access",
    agent: str = "all-agents",
    granularity: str = "hourly",
    pageviews_shift_list: list[int] | None = None,
    pageviews_shift_days: int = 13,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
):
    from .config import load_config

    config = load_config(config_path)
    freq = config.get("freq") or "1h"

    cache_dir = project_root / "data" / "cache" / "hapi"

    def _run_single(time_offset: str | None, shift_days: int):
        sources, start_dt, end_dt = build_omni_pageviews_sources(
            cache_dir,
            start,
            days,
            freq,
            articles,
            project,
            access,
            agent,
            granularity,
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
            "pageviews": {
                "project": project,
                "access": access,
                "agent": agent,
                "granularity": granularity,
                "articles": articles,
                "time_offset": time_offset or "0",
                "domain_id": "human_activity",
            },
        }
        inputs_path = run_dir / "inputs_omni_pageviews.json"
        inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

        metrics = _pageviews_metrics(events, results)
        _write_control_report(run_dir, metrics, shift_days)
        _print_run_summary(run_dir, metrics, total_events=len(events))
        return run_dir, metrics

    print("OMNI+Pageviews control (REAL):")
    run_dir_real, metrics_real = _run_single(None, 0)

    shift_specs = []
    if pageviews_shift_list:
        for days_value in pageviews_shift_list:
            shift_specs.append(int(days_value))
    else:
        shift_specs.append(int(pageviews_shift_days))

    shift_runs = []
    print("OMNI+Pageviews control (SHIFT):")
    for days_value in shift_specs:
        shift_offset = f"+{int(days_value)}d"
        run_dir_shift, metrics_shift = _run_single(shift_offset, int(days_value))
        shift_runs.append(
            {
                "run_dir": run_dir_shift,
                "metrics": metrics_shift,
                "shift_days": int(days_value),
            }
        )

    summary_real = _summarize_for_compare(metrics_real)
    shift_summaries = []
    for item in shift_runs:
        shift_summaries.append(
            {
                "run_id": item["run_dir"].name,
                "shift_days": item["shift_days"],
                "summary": _summarize_for_compare(item["metrics"]),
            }
        )

    if len(shift_summaries) == 1:
        summary_shift = shift_summaries[0]["summary"]
        verdict = _compare_verdict(summary_real, summary_shift)
        compare_payload = {
            "control_type": "pageviews",
            "run_id_real": run_dir_real.name,
            "run_id_shift": shift_summaries[0]["run_id"],
            "pageviews_shift_days": shift_summaries[0]["shift_days"],
            "real": summary_real,
            "shift": summary_shift,
            "delta": {
                "events_with_pageviews_count": summary_real["events_with_pageviews_count"]
                - summary_shift["events_with_pageviews_count"],
                "pageviews_in_top10_count": summary_real["pageviews_in_top10_count"]
                - summary_shift["pageviews_in_top10_count"],
            },
            "verdict": verdict,
        }
    else:
        real_events = summary_real["events_with_pageviews_count"]
        real_top = summary_real["pageviews_in_top10_count"]
        if real_events == 0:
            verdict = "OK: pageviews almost never participates"
        else:
            def _drops(summary):
                return summary["events_with_pageviews_count"] <= real_events // 2 and (
                    summary["pageviews_in_top10_count"] <= real_top // 2
                )

            all_drop = all(_drops(item["summary"]) for item in shift_summaries)
            verdict = (
                "OK: pageviews participation drops under shift"
                if all_drop
                else "SUSPECT: pageviews participates similarly under shift"
            )
        compare_payload = {
            "control_type": "pageviews",
            "run_id_real": run_dir_real.name,
            "real": summary_real,
            "shift_runs": shift_summaries,
            "verdict": verdict,
        }
    compare_path = run_dir_real / "control_compare.json"
    compare_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")

    print("Compare REAL vs SHIFT:")
    if "delta" in compare_payload:
        print(
            "  delta events_with_pageviews_count:",
            compare_payload["delta"]["events_with_pageviews_count"],
        )
        print(
            "  delta pageviews_in_top10_count:",
            compare_payload["delta"]["pageviews_in_top10_count"],
        )
    if verdict.startswith("SUSPECT"):
        print("WARNING:", verdict)
    else:
        print(verdict)

    return run_dir_real, [item["run_dir"] for item in shift_runs]
