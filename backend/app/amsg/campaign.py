from datetime import timezone
import json
from pathlib import Path

import pandas as pd

from .events_overlap import compute_overlaps
from .geomag import run_geomag_demo
from .hapi import fetch_data
from .holdout_catalog import build_holdout_catalog
from .omni import OMNI_BASE_URL, OMNI_DATASET_ID, OMNI_PARAMETERS
from .omni_nmdb import run_omni_nmdb_demo


def _parse_time(value: str):
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"Could not parse time '{value}'")
    return ts


def _format_time(value):
    return value.astimezone(timezone.utc).isoformat()


def _iter_windows(start: str, end: str, window_days: int, step_days: int):
    start_dt = _parse_time(start)
    end_dt = _parse_time(end)
    if end_dt <= start_dt:
        raise ValueError("end must be after start")
    window_delta = pd.Timedelta(days=int(window_days))
    step_delta = pd.Timedelta(days=int(step_days))
    current = start_dt
    while current + window_delta <= end_dt:
        yield current, current + window_delta
        current += step_delta


def _count_overlap(rows, ratio_threshold: float = 0.5):
    if not rows:
        return 0
    return sum(1 for row in rows if float(row.get("overlap_ratio", 0.0)) > ratio_threshold)


def _read_manifest_stats(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        stats = manifest.get("stats", {})
        if isinstance(stats, dict):
            return stats
    except Exception:
        return {}
    return {}


def _status_from_stats(stats: dict) -> str:
    total_points = int(stats.get("total_points", 0) or 0)
    total_windows = int(stats.get("total_windows", 0) or 0)
    if total_points <= 0 or total_windows <= 0:
        return "empty"
    return "ok"


def _preflight_omni_available(project_root: Path, start_ts, end_ts) -> tuple[bool, str]:
    cache_dir_hapi = project_root / "data" / "cache" / "hapi"
    check_params = [OMNI_PARAMETERS[0], "BZ_GSM"]
    try:
        frame = fetch_data(
            OMNI_BASE_URL,
            OMNI_DATASET_ID,
            start_ts.to_pydatetime(),
            end_ts.to_pydatetime(),
            check_params,
            cache_dir_hapi,
            chunk_days=7,
        )
    except Exception as exc:
        return False, f"OMNI preflight error: {exc}"
    if frame.empty:
        return False, "OMNI preflight: no data in interval"
    return True, ""


def _make_summary_row(
    window_start_str: str,
    window_end_str: str,
    stack: str,
    run_id: str = "",
    holdout_count_q05: int = 0,
    top_holdout_event_id: str = "",
    overlap_count: int | str = "",
    status: str = "ok",
    error_message: str = "",
    total_events: int | None = None,
    total_points: int | None = None,
):
    return {
        "window_start": window_start_str,
        "window_end": window_end_str,
        "stack": stack,
        "run_id": run_id,
        "holdout_count_q05": int(holdout_count_q05),
        "top_holdout_event_id": top_holdout_event_id,
        "overlap_count": overlap_count,
        "status": status,
        "error_message": error_message,
        "total_events": total_events if total_events is not None else "",
        "total_points": total_points if total_points is not None else "",
    }


def run_campaign(
    project_root: Path,
    start: str,
    end: str,
    window_days: int,
    step_days: int,
    stacks: list[str],
    omni_nmdb_config: Path | None = None,
    geomag_config: Path | None = None,
    nmdb_stations: list[str] | None = None,
    geomag_stations: list[str] | None = None,
    geomag_elements: list[str] | None = None,
    holdout_ratio: float | None = None,
    holdout_mode: str | None = None,
    q_threshold: float = 0.05,
    overlap_window_hours: float = 6.0,
):
    project_root = Path(project_root)
    runs_dir = project_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    stacks = [stack.strip().lower() for stack in stacks]
    if not stacks:
        raise ValueError("stacks must not be empty")

    omni_nmdb_config = omni_nmdb_config or (
        project_root / "configs" / "omni_nmdb_30day.yaml"
    )
    geomag_config = geomag_config or (project_root / "configs" / "geomag_30day.yaml")
    nmdb_stations = nmdb_stations or ["OULU", "JUNG"]
    geomag_stations = geomag_stations or ["BOU", "FRD"]
    geomag_elements = geomag_elements or ["H", "Z"]

    summary_rows = []

    for window_start, window_end in _iter_windows(start, end, window_days, step_days):
        window_start_str = _format_time(window_start)
        window_end_str = _format_time(window_end)
        window_days_int = int(window_days)

        run_dirs = {}
        row_indexes = {}

        if "omni_nmdb" in stacks:
            preflight_ok, preflight_message = _preflight_omni_available(
                project_root, window_start, window_end
            )
            if not preflight_ok:
                summary_rows.append(
                    _make_summary_row(
                        window_start_str,
                        window_end_str,
                        "omni_nmdb",
                        status="empty",
                        error_message=preflight_message,
                        total_events=0,
                        total_points=0,
                    )
                )
                print(
                    f"OMNI+NMDB window {window_start_str} -> {window_end_str} skipped: {preflight_message}"
                )
            else:
                try:
                    run_dir = run_omni_nmdb_demo(
                        project_root,
                        window_start_str,
                        window_days_int,
                        nmdb_stations,
                        omni_nmdb_config,
                        holdout_ratio=holdout_ratio,
                        holdout_mode=holdout_mode,
                    )
                except Exception as exc:
                    message = str(exc)
                    print(
                        f"OMNI+NMDB window {window_start_str} -> {window_end_str} failed: {message}"
                    )
                    summary_rows.append(
                        _make_summary_row(
                            window_start_str,
                            window_end_str,
                            "omni_nmdb",
                            status="error",
                            error_message=message,
                        )
                    )
                    run_dir = None
                if run_dir is not None:
                    try:
                        _catalog_path, catalog = build_holdout_catalog(run_dir, q_threshold)
                    except Exception as exc:
                        print(f"Holdout catalog failed for {run_dir.name}: {exc}")
                        catalog = pd.DataFrame()
                    top_event_id = ""
                    if not catalog.empty:
                        top_event_id = str(catalog.iloc[0]["event_id"])
                    stats = _read_manifest_stats(run_dir)
                    status = _status_from_stats(stats)
                    row = _make_summary_row(
                        window_start_str,
                        window_end_str,
                        "omni_nmdb",
                        run_id=run_dir.name,
                        holdout_count_q05=len(catalog),
                        top_holdout_event_id=top_event_id,
                        status=status,
                        total_events=int(stats.get("total_events", 0) or 0),
                        total_points=int(stats.get("total_points", 0) or 0),
                    )
                    summary_rows.append(row)
                    row_indexes["omni_nmdb"] = len(summary_rows) - 1
                    run_dirs["omni_nmdb"] = run_dir

        if "geomag" in stacks:
            try:
                run_dir = run_geomag_demo(
                    project_root,
                    window_start_str,
                    window_days_int,
                    geomag_stations,
                    geomag_elements,
                    geomag_config,
                    holdout_ratio=holdout_ratio,
                    holdout_mode=holdout_mode,
                )
            except Exception as exc:
                message = str(exc)
                print(f"Geomag window {window_start_str} -> {window_end_str} failed: {message}")
                summary_rows.append(
                    _make_summary_row(
                        window_start_str,
                        window_end_str,
                        "geomag",
                        status="error",
                        error_message=message,
                    )
                )
                run_dir = None
            if run_dir is not None:
                try:
                    _catalog_path, catalog = build_holdout_catalog(run_dir, q_threshold)
                except Exception as exc:
                    print(f"Holdout catalog failed for {run_dir.name}: {exc}")
                    catalog = pd.DataFrame()
                top_event_id = ""
                if not catalog.empty:
                    top_event_id = str(catalog.iloc[0]["event_id"])
                stats = _read_manifest_stats(run_dir)
                status = _status_from_stats(stats)
                summary_rows.append(
                    _make_summary_row(
                        window_start_str,
                        window_end_str,
                        "geomag",
                        run_id=run_dir.name,
                        holdout_count_q05=len(catalog),
                        top_holdout_event_id=top_event_id,
                        status=status,
                        total_events=int(stats.get("total_events", 0) or 0),
                        total_points=int(stats.get("total_points", 0) or 0),
                    )
                )
                row_indexes["geomag"] = len(summary_rows) - 1
                run_dirs["geomag"] = run_dir

        if "omni_nmdb" in run_dirs and "geomag" in run_dirs:
            overlap_count = 0
            if (
                row_indexes.get("omni_nmdb") is not None
                and summary_rows[row_indexes["omni_nmdb"]]["status"] == "ok"
                and row_indexes.get("geomag") is not None
                and summary_rows[row_indexes["geomag"]]["status"] == "ok"
            ):
                _overlap_path, rows = compute_overlaps(
                    run_dirs["omni_nmdb"], run_dirs["geomag"], overlap_window_hours
                )
                overlap_count = _count_overlap(rows, ratio_threshold=0.5)
                print(
                    f"Overlap {run_dirs['omni_nmdb'].name} vs {run_dirs['geomag'].name}: "
                    f"{overlap_count} (ratio>0.5)"
                )
            if row_indexes.get("omni_nmdb") is not None:
                summary_rows[row_indexes["omni_nmdb"]]["overlap_count"] = int(overlap_count)
            if row_indexes.get("geomag") is not None:
                summary_rows[row_indexes["geomag"]]["overlap_count"] = int(overlap_count)

    summary_path = runs_dir / "campaign_summary.csv"
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(summary_path, index=False)
    print("Campaign summary:", summary_path)
    return summary_path
