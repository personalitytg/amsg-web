import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def _detect_control_type(payload: dict) -> str:
    if "control_type" in payload:
        return str(payload["control_type"])
    if "btc_shift_days" in payload:
        return "btc"
    if "nmdb_shift_days" in payload:
        return "nmdb"
    if "pageviews_shift_days" in payload:
        return "pageviews"
    if "meteo_shift_days" in payload or "meteo_shift_hours" in payload:
        return "earth"
    if "p90_shift" in payload or "seismic_shift_days" in payload:
        return "seismic"
    return "unknown"


def _extract_counts(summary: dict):
    if not summary:
        return None, None, None
    for key in (
        "events_with_btc_count",
        "events_with_nmdb_count",
        "events_with_pageviews_count",
        "cross_domain_events_count",
    ):
        if key in summary:
            events_count = summary.get(key)
            break
    else:
        events_count = None

    for key in (
        "btc_in_top10_count",
        "nmdb_in_top10_count",
        "pageviews_in_top10_count",
        "cross_domain_in_top10_count",
    ):
        if key in summary:
            top_count = summary.get(key)
            break
    else:
        top_count = None

    best_score = None
    for key in (
        "best_btc_event_score",
        "best_nmdb_event_score",
        "best_pageviews_event_score",
        "best_cross_domain_event_score",
    ):
        if key in summary:
            best_score = summary.get(key)
            break
    return events_count, top_count, best_score


def _load_inputs_params(run_dir: Path):
    candidates = [
        "inputs_omni_btc.json",
        "inputs_omni_nmdb.json",
        "inputs_omni_pageviews.json",
        "inputs_omni_seismic.json",
        "inputs_earth.json",
    ]
    for name in candidates:
        path = run_dir / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}


def _extract_params(control_type: str, inputs_payload: dict):
    if not inputs_payload:
        return {}
    if control_type == "btc":
        btc = inputs_payload.get("btc", {})
        return {
            "transform": btc.get("transform"),
            "time_offset": btc.get("time_offset"),
            "price_col": btc.get("price_col"),
            "time_col": btc.get("time_col"),
        }
    if control_type == "nmdb":
        nmdb = inputs_payload.get("nmdb", {})
        return {
            "dtype": nmdb.get("dtype"),
            "tabchoice": nmdb.get("tabchoice"),
            "yunits": nmdb.get("yunits"),
            "time_offset": nmdb.get("time_offset"),
        }
    if control_type == "pageviews":
        pageviews = inputs_payload.get("pageviews", {})
        return {
            "project": pageviews.get("project"),
            "access": pageviews.get("access"),
            "agent": pageviews.get("agent"),
            "granularity": pageviews.get("granularity"),
            "articles": pageviews.get("articles"),
            "time_offset": pageviews.get("time_offset"),
        }
    if control_type == "seismic":
        seismic = inputs_payload.get("seismic", {})
        return {
            "min_magnitude": inputs_payload.get("min_magnitude"),
            "bbox": inputs_payload.get("bbox"),
            "transform": seismic.get("transform"),
            "zero_as_nan": seismic.get("zero_as_nan"),
            "min_nonzero_fraction": seismic.get("min_nonzero_fraction"),
            "time_offset": seismic.get("time_offset"),
        }
    if control_type == "earth":
        meteo = inputs_payload.get("meteo", {})
        return {
            "sites": inputs_payload.get("sites"),
            "params": inputs_payload.get("params"),
            "latlon": inputs_payload.get("latlon"),
            "time_offset": meteo.get("time_offset"),
        }
    return {}


def _collect_compare_entries(runs_dir: Path):
    entries = []
    for path in runs_dir.rglob("control_compare.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        control_type = _detect_control_type(payload)
        run_id_real = payload.get("run_id_real") or path.parent.name

        real_summary = payload.get("real", {})
        real_events, real_top, real_score = _extract_counts(real_summary)

        shift_runs = payload.get("shift_runs") or []
        if shift_runs:
            shift_run_ids = [item.get("run_id") for item in shift_runs if item.get("run_id")]
            shift_days = [item.get("shift_days") for item in shift_runs]
            shift_hours = [item.get("shift_hours") for item in shift_runs if "shift_hours" in item]
            shift_events = [(_extract_counts(item.get("summary", {}))[0]) for item in shift_runs]
            shift_top = [(_extract_counts(item.get("summary", {}))[1]) for item in shift_runs]
            shift_score = [(_extract_counts(item.get("summary", {}))[2]) for item in shift_runs]
            run_id_shift = ""
        else:
            shift_summary = payload.get("shift", {})
            shift_events, shift_top, shift_score = _extract_counts(shift_summary)
            shift_run_ids = [payload.get("run_id_shift")] if payload.get("run_id_shift") else []
            shift_days = [payload.get("btc_shift_days") or payload.get("nmdb_shift_days") or payload.get("pageviews_shift_days") or payload.get("meteo_shift_days")]
            shift_hours = [payload.get("meteo_shift_hours")] if payload.get("meteo_shift_hours") is not None else []
            run_id_shift = payload.get("run_id_shift", "")

        run_dir_real = runs_dir / run_id_real
        inputs_payload = _load_inputs_params(run_dir_real)
        params = _extract_params(control_type, inputs_payload)

        entries.append(
            {
                "control_type": control_type,
                "run_id_real": run_id_real,
                "run_id_shift": run_id_shift,
                "shift_runs": shift_run_ids,
                "shift_days": shift_days,
                "shift_hours": shift_hours,
                "verdict": payload.get("verdict"),
                "real_events_count": real_events,
                "real_in_top10_count": real_top,
                "real_best_event_score": real_score,
                "shift_events_count": shift_events,
                "shift_in_top10_count": shift_top,
                "shift_best_event_score": shift_score,
                "params": params,
                "source_path": str(path),
            }
        )
    return entries


def _collect_report_entries(runs_dir: Path, compare_real_ids: set[str]):
    entries = []
    for path in runs_dir.rglob("control_report.json"):
        run_id = path.parent.name
        if run_id in compare_real_ids:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        control_type = _detect_control_type(payload)
        entries.append(
            {
                "control_type": control_type,
                "run_id": run_id,
                "source_path": str(path),
            }
        )
    return entries


def write_control_summary(project_root: Path, runs_dir: Path | None = None):
    project_root = Path(project_root)
    runs_dir = Path(runs_dir) if runs_dir else project_root / "runs"
    compare_entries = _collect_compare_entries(runs_dir)
    compare_real_ids = {entry["run_id_real"] for entry in compare_entries}
    report_entries = _collect_report_entries(runs_dir, compare_real_ids)

    summary_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs_dir": str(runs_dir),
        "control_compares": compare_entries,
        "control_reports_only": report_entries,
    }

    out_json = runs_dir / "control_summary.json"
    out_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    out_csv = runs_dir / "control_summary.csv"
    fieldnames = [
        "control_type",
        "run_id_real",
        "run_id_shift",
        "shift_runs",
        "shift_days",
        "shift_hours",
        "verdict",
        "real_events_count",
        "real_in_top10_count",
        "real_best_event_score",
        "shift_events_count",
        "shift_in_top10_count",
        "shift_best_event_score",
        "params",
        "source_path",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in compare_entries:
            row = dict(entry)
            row["shift_runs"] = ",".join([str(value) for value in entry.get("shift_runs", []) if value])
            row["shift_days"] = ",".join(
                [str(value) for value in entry.get("shift_days", []) if value is not None]
            )
            row["shift_hours"] = ",".join(
                [str(value) for value in entry.get("shift_hours", []) if value is not None]
            )
            row["shift_events_count"] = ",".join(
                [str(value) for value in entry.get("shift_events_count", [])]
            ) if isinstance(entry.get("shift_events_count"), list) else entry.get("shift_events_count")
            row["shift_in_top10_count"] = ",".join(
                [str(value) for value in entry.get("shift_in_top10_count", [])]
            ) if isinstance(entry.get("shift_in_top10_count"), list) else entry.get("shift_in_top10_count")
            row["shift_best_event_score"] = ",".join(
                [str(value) for value in entry.get("shift_best_event_score", [])]
            ) if isinstance(entry.get("shift_best_event_score"), list) else entry.get("shift_best_event_score")
            row["params"] = json.dumps(entry.get("params", {}))
            writer.writerow(row)

    return out_json, out_csv
