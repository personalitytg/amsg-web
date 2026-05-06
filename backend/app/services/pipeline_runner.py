"""Bridge between AnalyzeRequest and the vendored amsg pipeline.

We do not modify amsg here. Instead we:

1. Build SeriesData lists per source (via amsg's `build_*_sources` helpers
   when they exist, otherwise the source is rejected upstream by the registry).
2. Run `amsg.pipeline.run_pipeline` in a worker thread.
3. Reshape the manifest + events.csv + top_candidates.csv into our schema.

Progress reporting is coarse: fetch -> pipeline -> aggregate -> done.
"""

from __future__ import annotations

import asyncio
import csv
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.amsg.config import DEFAULT_CONFIG
from app.amsg.io import SeriesData
from app.amsg.pipeline import make_run_dir, run_pipeline
from app.core.config import get_settings
from app.core.jobs import JobHandle
from app.schemas.analyze import AnalyzeRequest
from app.schemas.results import (
    AnalysisResult,
    AnalysisSummary,
    AnomalyEvent,
    EventEdge,
    HeatmapCell,
    PValueBucket,
    SeriesPayload,
    SeriesPoint,
)
from app.services.source_registry import is_available


MAX_POINTS_PER_SERIES = 4000  # downsample for the wire payload


def _build_config(req: AnalyzeRequest) -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    s = req.settings
    cfg.update(
        {
            "window_sizes": s.window_sizes,
            "step_size": s.step_size,
            "bins": s.bins,
            "top_p": s.top_p,
            "shift_d": s.shift_d,
            "null_shifts_count": s.null_shifts_count,
            "min_pair_valid_fraction": s.min_pair_valid_fraction,
            "holdout_ratio": s.holdout_ratio,
            "holdout_mode": "time" if s.holdout_ratio > 0 else None,
            "seed": s.seed,
        }
    )
    return cfg


def _build_demo_series() -> list[SeriesData]:
    from app.amsg.demo import generate_demo_series

    sources, _ = generate_demo_series()
    return sources


def _build_omni_series(start: date, days: int, cache_dir: Path) -> list[SeriesData]:
    from app.amsg.omni import build_omni_sources

    start_str = start.isoformat()
    sources, _, _ = build_omni_sources(cache_dir / "hapi", start_str, days, freq="1min")
    return sources


def _build_swpc_series(days: int, cache_dir: Path) -> list[SeriesData]:
    from app.amsg.swpc import build_swpc_sources

    return build_swpc_sources(cache_dir / "swpc", days, freq="1min", include_kp=False)


def _build_series_for_source(source_id: str, start: date, end: date, cache_dir: Path) -> list[SeriesData]:
    """Dispatch to amsg connectors. Each branch isolates network calls."""
    days = max(1, (end - start).days)

    if source_id == "demo":
        return _build_demo_series()
    if source_id == "omni":
        return _build_omni_series(start, days, cache_dir)
    if source_id == "swpc":
        return _build_swpc_series(days, cache_dir)

    raise ValueError(f"Source '{source_id}' is not yet wired into the web flow.")


def _downsample(timestamps: np.ndarray, values: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    if len(timestamps) <= max_points:
        return timestamps, values
    idx = np.linspace(0, len(timestamps) - 1, max_points).astype(int)
    return timestamps[idx], values[idx]


def _format_timestamp(t: Any) -> str:
    try:
        ts = pd.Timestamp(t)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert("UTC").isoformat()
    except Exception:
        return str(t)


def _series_to_payload(series_list: list[SeriesData]) -> list[SeriesPayload]:
    payloads: list[SeriesPayload] = []
    for s in series_list:
        ts, vals = _downsample(s.timestamps, s.values, MAX_POINTS_PER_SERIES)
        points: list[SeriesPoint] = []
        for t, v in zip(ts, vals, strict=False):
            v_clean: float | None
            try:
                fv = float(v)
                v_clean = None if np.isnan(fv) else fv
            except (TypeError, ValueError):
                v_clean = None
            points.append(SeriesPoint(t=_format_timestamp(t), v=v_clean))
        payloads.append(
            SeriesPayload(
                source_id=s.source_id,
                domain=s.domain_id,
                label=s.source_id,
                points=points,
            )
        )
    return payloads


def _read_run_artifacts(run_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    manifest_path = run_dir / "manifest.json"
    events_path = run_dir / "events.csv"
    candidates_path = run_dir / "top_candidates.csv"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    events = list(csv.DictReader(events_path.open(encoding="utf-8"))) if events_path.exists() else []
    candidates = list(csv.DictReader(candidates_path.open(encoding="utf-8"))) if candidates_path.exists() else []
    return events, candidates, manifest


def _to_event_edges(top_edges_raw: str) -> list[EventEdge]:
    """Parse the 'edge_a-edge_b:novelty/nms/p' format used by amsg.events.csv."""
    if not top_edges_raw:
        return []
    edges: list[EventEdge] = []
    for chunk in top_edges_raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            pair, metrics = chunk.split(":", 1)
            a, b = pair.split("-", 1)
            novelty_s, nms_s, p_s = metrics.split("/")
            edges.append(
                EventEdge(
                    a=a.strip(),
                    b=b.strip(),
                    nms=float(nms_s),
                    p_value=float(p_s),
                    novelty=int(float(novelty_s)),
                )
            )
        except Exception:
            continue
    return edges


def _build_heatmap(candidates: list[dict[str, Any]]) -> list[HeatmapCell]:
    pairs: dict[tuple[str, str], list[float]] = {}
    for row in candidates:
        a = row.get("anchor_source_id") or ""
        b = row.get("other_source_id") or ""
        nms_s = row.get("nms")
        if not a or not b or nms_s in (None, ""):
            continue
        key = tuple(sorted([a, b]))
        try:
            pairs.setdefault(key, []).append(float(nms_s))
        except ValueError:
            continue
    return [
        HeatmapCell(a=a, b=b, score=float(np.median(vals)))
        for (a, b), vals in pairs.items()
    ]


def _build_pvalue_histogram(events: list[dict[str, Any]]) -> list[PValueBucket]:
    pvals: list[float] = []
    for row in events:
        v = row.get("best_p_value")
        try:
            if v is not None and v != "":
                pvals.append(float(v))
        except ValueError:
            continue
    if not pvals:
        return []
    bins = np.linspace(0.0, 1.0, 21)
    counts, edges = np.histogram(pvals, bins=bins)
    return [
        PValueBucket(bin_start=float(edges[i]), bin_end=float(edges[i + 1]), count=int(counts[i]))
        for i in range(len(counts))
    ]


def _events_to_payload(events: list[dict[str, Any]], alpha: float) -> tuple[list[AnomalyEvent], int]:
    payload: list[AnomalyEvent] = []
    significant = 0
    for row in events:
        try:
            best_p = float(row.get("best_p_value") or 1.0)
            q_raw = row.get("q_value")
            q = float(q_raw) if q_raw not in (None, "", "None") else None
            best_nms = float(row.get("best_nms") or 0.0)
            edge_novelty_sum = float(row.get("edge_novelty_sum") or 0.0)
            edges_count = int(float(row.get("edges_count") or 0))
            sources = (row.get("sources_involved") or "").split("|")
            domains = (row.get("domains_involved") or "").split("|")
            cross = int(float(row.get("cross_domain_edges_count") or 0))
            top_edges = _to_event_edges(row.get("top_edges") or "")
            is_holdout = (row.get("is_holdout") or "").lower() in ("true", "1", "yes")
        except (TypeError, ValueError):
            continue

        if (q is not None and q <= alpha) or (q is None and best_p <= alpha):
            significant += 1

        payload.append(
            AnomalyEvent(
                event_id=row.get("event_id", ""),
                start=row.get("event_start", ""),
                end=row.get("event_end", ""),
                best_p_value=best_p,
                q_value=q,
                best_nms=best_nms,
                edge_novelty_sum=edge_novelty_sum,
                edges_count=edges_count,
                sources=[s for s in sources if s],
                domains=[d for d in domains if d],
                cross_domain_edges_count=cross,
                top_edges=top_edges,
                is_holdout=is_holdout,
            )
        )
    return payload, significant


async def run_analysis(handle: JobHandle, req: AnalyzeRequest) -> dict[str, Any]:
    settings = get_settings()
    settings.ensure_dirs()
    started = time.time()

    invalid = [sid for sid in req.source_ids if not is_available(sid)]
    if invalid:
        raise ValueError(f"Sources not available in web flow: {', '.join(invalid)}")

    await handle.report("fetch", 5.0, "Loading data sources")

    series_list: list[SeriesData] = []
    failed_sources: list[str] = []
    for src_id in req.source_ids:
        try:
            series_list.extend(
                await asyncio.to_thread(_build_series_for_source, src_id, req.start, req.end, settings.cache_dir)
            )
        except Exception as exc:  # noqa: BLE001
            failed_sources.append(f"{src_id}: {type(exc).__name__}: {exc}")

    if not series_list:
        details = ("Failures: " + "; ".join(failed_sources)) if failed_sources else ""
        raise RuntimeError(f"No usable data sources. {details}")

    await handle.report("pipeline", 35.0, f"Running pipeline on {len(series_list)} series")

    cfg = _build_config(req)
    run_dir = make_run_dir(settings.runs_dir)
    await asyncio.to_thread(run_pipeline, series_list, cfg, run_dir, False)

    await handle.report("aggregate", 80.0, "Aggregating results")

    events_raw, candidates_raw, _manifest = _read_run_artifacts(run_dir)
    events_payload, significant = _events_to_payload(events_raw, req.settings.alpha)
    series_payload = _series_to_payload(series_list)
    heatmap = _build_heatmap(candidates_raw)
    pval_hist = _build_pvalue_histogram(events_raw)

    pvals = [e.best_p_value for e in events_payload]
    summary = AnalysisSummary(
        total_events=len(events_payload),
        significant_events=significant,
        p_value_min=(min(pvals) if pvals else None),
        p_value_max=(max(pvals) if pvals else None),
        sources_count=len({s.source_id for s in series_list}),
        duration_seconds=time.time() - started,
    )

    result = AnalysisResult(
        job_id=handle.id,
        summary=summary,
        series=series_payload,
        events=events_payload,
        heatmap=heatmap,
        p_value_histogram=pval_hist,
        config_echo={"settings": req.settings.model_dump(), "failed_sources": failed_sources},
    )
    return result.model_dump(mode="json")
