import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .config import load_config
from .events_overlap import compute_overlaps
from .geomag import run_geomag_demo
from .holdout_catalog import build_holdout_catalog
from .omni_nmdb import run_omni_nmdb_demo


EVENT_EVIDENCE_FIELDS = [
    "event_key",
    "source_run_id",
    "event_id",
    "holdout_q05",
    "overlap_geomag_holdout",
    "overlap_nmdb_quality",
    "shift_drop",
    "manual_review",
    "status",
]


def _safe_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        if isinstance(value, str) and not value.strip():
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_str(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _manual_priority(value: str) -> int:
    text = _safe_str(value, default="unknown").lower()
    if text == "keep":
        return 2
    if text in {"reject", "rejected"}:
        return 0
    return 1


def _count_overlap_ratio(rows: list[dict], threshold: float = 0.5) -> int:
    if not rows:
        return 0
    count = 0
    for row in rows:
        try:
            ratio = float(row.get("overlap_ratio", 0.0))
        except (TypeError, ValueError):
            ratio = 0.0
        if ratio > threshold:
            count += 1
    return count


def _read_event_interval(runs_dir: Path, run_id: str, event_id: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    events_path = runs_dir / run_id / "events.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Missing events.csv for run {run_id}: {events_path}")
    events = pd.read_csv(events_path)
    if "event_id" not in events.columns:
        raise RuntimeError(f"events.csv missing event_id column: {events_path}")
    selected = events[events["event_id"].astype(str) == str(event_id)]
    if selected.empty:
        raise RuntimeError(f"Event {event_id} not found in {events_path}")
    row = selected.iloc[0]
    start = pd.to_datetime(row.get("event_start"), utc=True, errors="coerce")
    end = pd.to_datetime(row.get("event_end"), utc=True, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        raise RuntimeError(f"Could not parse event interval for {run_id}:{event_id}")
    return start, end


def _window_start_days(start: pd.Timestamp, end: pd.Timestamp, pad_days: int) -> tuple[str, int]:
    begin = start - pd.Timedelta(days=int(pad_days))
    finish = end + pd.Timedelta(days=int(pad_days))
    duration = finish - begin
    days = max(1, int(math.ceil(duration.total_seconds() / 86400.0)))
    return begin.isoformat(), days


def _write_variant_config(base_config_path: Path, output_path: Path, strict_top_p: float | None):
    config = load_config(base_config_path)
    if strict_top_p is not None:
        config["top_p"] = float(strict_top_p)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return output_path


def _status_after_cycle(
    old_status: str,
    old_shift_drop: str,
    manual_review: str,
    holdout_q05: int,
    overlap_geomag_holdout: int,
    overlap_nmdb_quality: int,
    shift_drop: str,
):
    old_status = _safe_str(old_status, default="candidate").lower()
    old_shift_drop = _safe_str(old_shift_drop, default="unknown").lower()
    manual_review = _safe_str(manual_review, default="unknown").lower()
    shift_drop = _safe_str(shift_drop, default="unknown").lower()

    if manual_review == "reject":
        return "rejected", "manual_review=reject"

    if (
        holdout_q05 > 0
        and overlap_geomag_holdout > 0
        and overlap_nmdb_quality > 0
        and shift_drop == "yes"
        and manual_review == "keep"
    ):
        return "replicated", "all evidence-gate conditions met"

    if shift_drop == "no" and old_status == "candidate" and old_shift_drop == "no":
        return "rejected", "two consecutive cycles with no_drop"

    return "candidate", "insufficient evidence for replication"


def run_candidate_conversion(
    project_root: Path,
    event_evidence_path: Path | None = None,
    conversion_report_path: Path | None = None,
    omni_nmdb_config: Path | None = None,
    geomag_config: Path | None = None,
    strict_top_p: float = 0.005,
    pad_days: int = 14,
    holdout_ratio: float = 0.3,
    holdout_mode: str = "time",
    shifts: list[int] | None = None,
    nmdb_stations: list[str] | None = None,
    geomag_stations: list[str] | None = None,
    geomag_elements: list[str] | None = None,
    q_threshold: float = 0.05,
    overlap_window_hours: float = 6.0,
):
    project_root = Path(project_root)
    runs_dir = project_root / "runs"
    event_evidence_path = (
        Path(event_evidence_path) if event_evidence_path else runs_dir / "event_evidence.csv"
    )
    conversion_report_path = (
        Path(conversion_report_path)
        if conversion_report_path
        else runs_dir / "conversion_report.csv"
    )
    omni_nmdb_config = (
        Path(omni_nmdb_config)
        if omni_nmdb_config
        else project_root / "configs" / "omni_nmdb_90day_discovery_10min.yaml"
    )
    geomag_config = (
        Path(geomag_config)
        if geomag_config
        else project_root / "configs" / "geomag_90day_discovery.yaml"
    )
    shifts = shifts or [7, 13, 19]
    nmdb_stations = nmdb_stations or ["OULU", "JUNG"]
    geomag_stations = geomag_stations or ["BOU", "FRD"]
    geomag_elements = geomag_elements or ["H", "Z"]

    if not event_evidence_path.exists():
        raise FileNotFoundError(f"Missing event evidence file: {event_evidence_path}")

    rows = []
    with event_evidence_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    candidates = [row for row in rows if _safe_str(row.get("status")).lower() == "candidate"]
    candidates.sort(
        key=lambda row: (
            -_safe_int(row.get("holdout_q05")),
            -_safe_int(row.get("overlap_nmdb_quality")),
            -_manual_priority(_safe_str(row.get("manual_review"), default="unknown")),
            _safe_str(row.get("event_key")),
        )
    )

    candidate_before = len(candidates)
    print(f"Candidate conversion: {candidate_before} candidates")

    cycle_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cycle_dir = runs_dir / f"candidate_conversion_{cycle_stamp}"
    cycle_dir.mkdir(parents=True, exist_ok=True)

    omni_base_cfg = _write_variant_config(
        omni_nmdb_config, cycle_dir / "omni_nmdb_base.json", strict_top_p=None
    )
    omni_strict_cfg = _write_variant_config(
        omni_nmdb_config, cycle_dir / "omni_nmdb_strict.json", strict_top_p=strict_top_p
    )
    geomag_base_cfg = _write_variant_config(
        geomag_config, cycle_dir / "geomag_base.json", strict_top_p=None
    )
    geomag_strict_cfg = _write_variant_config(
        geomag_config, cycle_dir / "geomag_strict.json", strict_top_p=strict_top_p
    )

    updated_rows: dict[str, dict] = {row["event_key"]: dict(row) for row in rows}
    changed_rows = []
    detailed_rows = []
    replicated_new = 0
    rejected_new = 0

    for index, row in enumerate(candidates, start=1):
        event_key = _safe_str(row.get("event_key"))
        source_run_id = _safe_str(row.get("source_run_id"))
        event_id = _safe_str(row.get("event_id"))
        manual_review = _safe_str(row.get("manual_review"), default="unknown").lower()
        old_status = _safe_str(row.get("status"), default="candidate").lower()
        old_shift_drop = _safe_str(row.get("shift_drop"), default="unknown").lower()

        print(f"[{index}/{candidate_before}] {event_key}")

        try:
            event_start, event_end = _read_event_interval(runs_dir, source_run_id, event_id)
            window_start_iso, window_days = _window_start_days(event_start, event_end, pad_days)

            variant_metrics = {}
            for variant_name, omni_cfg, geomag_cfg in (
                ("base", omni_base_cfg, geomag_base_cfg),
                ("strict", omni_strict_cfg, geomag_strict_cfg),
            ):
                omni_run = run_omni_nmdb_demo(
                    project_root,
                    window_start_iso,
                    window_days,
                    nmdb_stations,
                    omni_cfg,
                    holdout_ratio=holdout_ratio,
                    holdout_mode=holdout_mode,
                )
                geomag_run = run_geomag_demo(
                    project_root,
                    window_start_iso,
                    window_days,
                    geomag_stations,
                    geomag_elements,
                    geomag_cfg,
                    holdout_ratio=holdout_ratio,
                    holdout_mode=holdout_mode,
                )

                _, catalog_omni = build_holdout_catalog(omni_run, q_threshold)
                _, catalog_geomag = build_holdout_catalog(geomag_run, q_threshold)
                holdout_count = max(len(catalog_omni), len(catalog_geomag))

                suffix_base = f"_conv_{source_run_id}_{event_id}_{variant_name}_geomag_holdout"
                _, overlap_holdout_rows = compute_overlaps(
                    omni_run,
                    geomag_run,
                    overlap_window_hours,
                    output_suffix=suffix_base,
                    holdout_only_b=True,
                    max_q_value_b=q_threshold,
                )
                overlap_holdout_count = _count_overlap_ratio(overlap_holdout_rows)

                suffix_quality = (
                    f"_conv_{source_run_id}_{event_id}_{variant_name}_geomag_holdout_nmdb_quality"
                )
                _, overlap_quality_rows = compute_overlaps(
                    omni_run,
                    geomag_run,
                    overlap_window_hours,
                    output_suffix=suffix_quality,
                    holdout_only_b=True,
                    max_q_value_b=q_threshold,
                    min_nmdb_edges=3,
                    min_nmdb_pair_median=0.9,
                    nmdb_filter_side="a",
                )
                overlap_quality_count = _count_overlap_ratio(overlap_quality_rows)

                shift_counts_holdout = []
                shift_counts_quality = []
                if variant_name == "base":
                    for shift_day in shifts:
                        shifted_run = run_omni_nmdb_demo(
                            project_root,
                            window_start_iso,
                            window_days,
                            nmdb_stations,
                            omni_cfg,
                            nmdb_time_offset=f"+{int(shift_day)}d",
                            holdout_ratio=holdout_ratio,
                            holdout_mode=holdout_mode,
                        )
                        shift_suffix_h = (
                            f"_conv_{source_run_id}_{event_id}_{variant_name}_shift{int(shift_day)}_geomag_holdout"
                        )
                        _, shift_h_rows = compute_overlaps(
                            shifted_run,
                            geomag_run,
                            overlap_window_hours,
                            output_suffix=shift_suffix_h,
                            holdout_only_b=True,
                            max_q_value_b=q_threshold,
                        )
                        shift_counts_holdout.append(_count_overlap_ratio(shift_h_rows))

                        shift_suffix_q = (
                            f"_conv_{source_run_id}_{event_id}_{variant_name}_shift{int(shift_day)}_geomag_holdout_nmdb_quality"
                        )
                        _, shift_q_rows = compute_overlaps(
                            shifted_run,
                            geomag_run,
                            overlap_window_hours,
                            output_suffix=shift_suffix_q,
                            holdout_only_b=True,
                            max_q_value_b=q_threshold,
                            min_nmdb_edges=3,
                            min_nmdb_pair_median=0.9,
                            nmdb_filter_side="a",
                        )
                        shift_counts_quality.append(_count_overlap_ratio(shift_q_rows))

                variant_metrics[variant_name] = {
                    "holdout_q05": holdout_count,
                    "overlap_geomag_holdout": overlap_holdout_count,
                    "overlap_nmdb_quality": overlap_quality_count,
                    "shift_counts_holdout": shift_counts_holdout,
                    "shift_counts_quality": shift_counts_quality,
                    "omni_run_id": omni_run.name,
                    "geomag_run_id": geomag_run.name,
                }

            holdout_q05_new = min(
                metric["holdout_q05"] for metric in variant_metrics.values()
            )
            overlap_geomag_new = min(
                metric["overlap_geomag_holdout"] for metric in variant_metrics.values()
            )
            overlap_nmdb_new = min(
                metric["overlap_nmdb_quality"] for metric in variant_metrics.values()
            )

            base_metrics = variant_metrics["base"]
            shift_holdout = base_metrics["shift_counts_holdout"]
            shift_quality = base_metrics["shift_counts_quality"]
            if (
                base_metrics["overlap_geomag_holdout"] > 0
                and base_metrics["overlap_nmdb_quality"] > 0
                and shift_holdout
                and shift_quality
                and max(shift_holdout) < base_metrics["overlap_geomag_holdout"]
                and max(shift_quality) < base_metrics["overlap_nmdb_quality"]
            ):
                shift_drop_new = "yes"
            else:
                shift_drop_new = "no"

            new_status, reason = _status_after_cycle(
                old_status=old_status,
                old_shift_drop=old_shift_drop,
                manual_review=manual_review,
                holdout_q05=holdout_q05_new,
                overlap_geomag_holdout=overlap_geomag_new,
                overlap_nmdb_quality=overlap_nmdb_new,
                shift_drop=shift_drop_new,
            )

            updated = dict(row)
            updated["holdout_q05"] = str(int(holdout_q05_new))
            updated["overlap_geomag_holdout"] = str(int(overlap_geomag_new))
            updated["overlap_nmdb_quality"] = str(int(overlap_nmdb_new))
            updated["shift_drop"] = shift_drop_new
            updated["status"] = new_status
            updated_rows[event_key] = updated

            if old_status != new_status:
                if new_status == "replicated":
                    replicated_new += 1
                if new_status == "rejected":
                    rejected_new += 1
                changed_rows.append(
                    {
                        "event_key": event_key,
                        "old_status": old_status,
                        "new_status": new_status,
                        "reason": reason,
                    }
                )

            detailed_rows.append(
                {
                    "event_key": event_key,
                    "source_run_id": source_run_id,
                    "event_id": event_id,
                    "window_start": window_start_iso,
                    "window_days": window_days,
                    "manual_review": manual_review,
                    "old_status": old_status,
                    "new_status": new_status,
                    "reason": reason,
                    "base_holdout_q05": base_metrics["holdout_q05"],
                    "base_overlap_geomag_holdout": base_metrics["overlap_geomag_holdout"],
                    "base_overlap_nmdb_quality": base_metrics["overlap_nmdb_quality"],
                    "base_shift_counts_holdout": "|".join(
                        str(value) for value in base_metrics["shift_counts_holdout"]
                    ),
                    "base_shift_counts_nmdb_quality": "|".join(
                        str(value) for value in base_metrics["shift_counts_quality"]
                    ),
                    "strict_holdout_q05": variant_metrics["strict"]["holdout_q05"],
                    "strict_overlap_geomag_holdout": variant_metrics["strict"][
                        "overlap_geomag_holdout"
                    ],
                    "strict_overlap_nmdb_quality": variant_metrics["strict"][
                        "overlap_nmdb_quality"
                    ],
                    "holdout_q05_final": holdout_q05_new,
                    "overlap_geomag_holdout_final": overlap_geomag_new,
                    "overlap_nmdb_quality_final": overlap_nmdb_new,
                    "shift_drop_final": shift_drop_new,
                }
            )
        except Exception as exc:
            reason = f"conversion_error: {exc}"
            detailed_rows.append(
                {
                    "event_key": event_key,
                    "source_run_id": source_run_id,
                    "event_id": event_id,
                    "window_start": "",
                    "window_days": "",
                    "manual_review": manual_review,
                    "old_status": old_status,
                    "new_status": old_status,
                    "reason": reason,
                    "base_holdout_q05": "",
                    "base_overlap_geomag_holdout": "",
                    "base_overlap_nmdb_quality": "",
                    "base_shift_counts_holdout": "",
                    "base_shift_counts_nmdb_quality": "",
                    "strict_holdout_q05": "",
                    "strict_overlap_geomag_holdout": "",
                    "strict_overlap_nmdb_quality": "",
                    "holdout_q05_final": row.get("holdout_q05", ""),
                    "overlap_geomag_holdout_final": row.get("overlap_geomag_holdout", ""),
                    "overlap_nmdb_quality_final": row.get("overlap_nmdb_quality", ""),
                    "shift_drop_final": row.get("shift_drop", ""),
                }
            )

    final_rows = [updated_rows[key] for key in sorted(updated_rows.keys())]
    with event_evidence_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_EVIDENCE_FIELDS)
        writer.writeheader()
        writer.writerows(final_rows)

    candidate_left = sum(
        1 for row in final_rows if _safe_str(row.get("status"), "").lower() == "candidate"
    )

    conversion_report_path.parent.mkdir(parents=True, exist_ok=True)
    report_fields = [
        "timestamp",
        "candidate_before",
        "replicated_new",
        "rejected_new",
        "candidate_left",
        "event_key",
        "old_status",
        "new_status",
        "reason",
    ]
    with conversion_report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=report_fields)
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "candidate_before": candidate_before,
                "replicated_new": replicated_new,
                "rejected_new": rejected_new,
                "candidate_left": candidate_left,
                "event_key": "",
                "old_status": "",
                "new_status": "",
                "reason": "summary",
            }
        )
        for row in changed_rows:
            writer.writerow(
                {
                    "timestamp": "",
                    "candidate_before": "",
                    "replicated_new": "",
                    "rejected_new": "",
                    "candidate_left": "",
                    "event_key": row["event_key"],
                    "old_status": row["old_status"],
                    "new_status": row["new_status"],
                    "reason": row["reason"],
                }
            )

    details_path = cycle_dir / "conversion_details.csv"
    if detailed_rows:
        detail_fields = list(detailed_rows[0].keys())
        with details_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=detail_fields)
            writer.writeheader()
            writer.writerows(detailed_rows)
    else:
        details_path.write_text("", encoding="utf-8")

    summary = {
        "candidate_before": candidate_before,
        "replicated_new": replicated_new,
        "rejected_new": rejected_new,
        "candidate_left": candidate_left,
        "changed_rows": changed_rows,
        "cycle_dir": str(cycle_dir),
        "conversion_report": str(conversion_report_path),
        "details_csv": str(details_path),
    }
    summary_path = cycle_dir / "conversion_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("Candidate conversion summary:")
    print(
        f"  candidate_before={candidate_before} replicated_new={replicated_new} rejected_new={rejected_new} candidate_left={candidate_left}"
    )
    print("  conversion_report:", conversion_report_path)
    print("  details_csv:", details_path)

    return summary
