import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


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


def _normalize_shift_verdict(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    if text in {"no", "no_drop", "nodrop", "failed"}:
        return "no"
    if text in {"yes", "drop", "dropped", "ok"}:
        return "yes"
    if "no_drop" in text or "nodrop" in text:
        return "no"
    if "drop" in text:
        return "yes"
    return "unknown"


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


def _load_holdout_review(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    decisions: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            run_id = _safe_str(row.get("run_id"))
            event_id = _safe_str(row.get("event_id"))
            if not run_id or not event_id:
                continue
            decision = _safe_str(row.get("decision"), default="unknown").lower()
            decisions[f"{run_id}:{event_id}"] = decision
    return decisions


def _scan_holdout_catalogs(runs_dir: Path) -> set[str]:
    keys: set[str] = set()
    for catalog_path in runs_dir.rglob("holdout_catalog.csv"):
        run_id = catalog_path.parent.name
        try:
            with catalog_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    event_id = _safe_str(row.get("event_id"))
                    if event_id:
                        keys.add(f"{run_id}:{event_id}")
        except OSError:
            continue
    return keys


def _scan_overlap_counts(runs_dir: Path) -> tuple[dict[str, int], dict[str, int]]:
    geomag_holdout_counts: dict[str, int] = {}
    nmdb_quality_counts: dict[str, int] = {}

    for overlap_path in runs_dir.glob("overlaps_*.csv"):
        name = overlap_path.name
        is_geomag_holdout = name.endswith("_geomag_holdout.csv")
        is_nmdb_quality = (
            name.endswith("_geomag_holdout_nmdb_quality.csv")
            or name.endswith("_nmdb_quality.csv")
        )
        if not is_geomag_holdout and not is_nmdb_quality:
            continue
        try:
            with overlap_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    run_a = _safe_str(row.get("run_a"))
                    run_b = _safe_str(row.get("run_b"))
                    event_a = _safe_str(row.get("event_id_a"))
                    event_b = _safe_str(row.get("event_id_b"))
                    if run_a and event_a:
                        key_a = f"{run_a}:{event_a}"
                        if is_geomag_holdout:
                            geomag_holdout_counts[key_a] = geomag_holdout_counts.get(key_a, 0) + 1
                        if is_nmdb_quality:
                            nmdb_quality_counts[key_a] = nmdb_quality_counts.get(key_a, 0) + 1
                    if run_b and event_b:
                        key_b = f"{run_b}:{event_b}"
                        if is_geomag_holdout:
                            geomag_holdout_counts[key_b] = geomag_holdout_counts.get(key_b, 0) + 1
                        if is_nmdb_quality:
                            nmdb_quality_counts[key_b] = nmdb_quality_counts.get(key_b, 0) + 1
        except OSError:
            continue
    return geomag_holdout_counts, nmdb_quality_counts


def _collect_event_to_runs(holdout_keys: set[str], review_keys: set[str]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for key in holdout_keys.union(review_keys):
        run_id, _, event_id = key.partition(":")
        if not run_id or not event_id:
            continue
        bucket = mapping.setdefault(event_id, set())
        bucket.add(run_id)
    return mapping


def _collect_review_event_to_runs(review_map: dict[str, str]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for key in review_map:
        run_id, _, event_id = key.partition(":")
        if not run_id or not event_id:
            continue
        bucket = mapping.setdefault(event_id, set())
        bucket.add(run_id)
    return mapping


def _read_replication_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _infer_source_run_id(
    row: dict,
    event_to_runs: dict[str, set[str]],
    review_event_to_runs: dict[str, set[str]],
) -> str:
    for key in ("source_run_id", "source_run", "seed_run_id"):
        value = _safe_str(row.get(key))
        if value:
            return value
    event_id = _safe_str(row.get("event_id"))
    review_runs = sorted(review_event_to_runs.get(event_id, set()))
    if len(review_runs) == 1:
        return review_runs[0]
    runs = sorted(event_to_runs.get(event_id, set()))
    if len(runs) == 1:
        return runs[0]
    return "unknown"


def _aggregate_replication(
    replication_rows: list[dict],
    event_to_runs: dict[str, set[str]],
    review_event_to_runs: dict[str, set[str]],
) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for row in replication_rows:
        event_id = _safe_str(row.get("event_id"))
        if not event_id:
            continue
        source_run_id = _infer_source_run_id(row, event_to_runs, review_event_to_runs)
        event_key = f"{source_run_id}:{event_id}"
        bucket = grouped.setdefault(
            event_key,
            {
                "source_run_id": source_run_id,
                "event_id": event_id,
                "holdout_values": [],
                "overlap_geomag_values": [],
                "overlap_nmdb_values": [],
                "shift_values": [],
            },
        )
        bucket["holdout_values"].append(_safe_int(row.get("holdout_count_q05")))
        bucket["overlap_geomag_values"].append(_safe_int(row.get("overlap_geomag_holdout")))
        bucket["overlap_nmdb_values"].append(_safe_int(row.get("overlap_nmdb_quality")))
        bucket["shift_values"].append(_normalize_shift_verdict(row.get("shift_verdict")))

    aggregated: dict[str, dict] = {}
    for event_key, bucket in grouped.items():
        holdout_values = bucket["holdout_values"]
        overlap_geomag_values = bucket["overlap_geomag_values"]
        overlap_nmdb_values = bucket["overlap_nmdb_values"]
        shift_values = bucket["shift_values"]

        if shift_values and any(value == "no" for value in shift_values):
            shift_drop = "no"
        elif shift_values and all(value == "yes" for value in shift_values):
            shift_drop = "yes"
        elif shift_values and any(value == "yes" for value in shift_values):
            shift_drop = "partial"
        else:
            shift_drop = "unknown"

        aggregated[event_key] = {
            "source_run_id": bucket["source_run_id"],
            "event_id": bucket["event_id"],
            "holdout_q05": min(holdout_values) if holdout_values else 0,
            "overlap_geomag_holdout": min(overlap_geomag_values) if overlap_geomag_values else 0,
            "overlap_nmdb_quality": min(overlap_nmdb_values) if overlap_nmdb_values else 0,
            "shift_drop": shift_drop,
        }
    return aggregated


def _derive_status(
    holdout_q05: int,
    overlap_geomag_holdout: int,
    overlap_nmdb_quality: int,
    shift_drop: str,
    manual_review: str,
) -> str:
    review = _safe_str(manual_review, default="unknown").lower()
    shift = _safe_str(shift_drop, default="unknown").lower()

    if review == "reject" or shift == "no":
        return "rejected"
    if (
        holdout_q05 > 0
        and overlap_geomag_holdout > 0
        and overlap_nmdb_quality > 0
        and shift == "yes"
        and review == "keep"
    ):
        return "replicated"
    if holdout_q05 > 0 and overlap_geomag_holdout > 0:
        return "candidate"
    return "rejected"


def write_event_evidence(
    project_root: Path,
    runs_dir: Path | None = None,
    output_path: Path | None = None,
    replication_summary_path: Path | None = None,
    holdout_review_path: Path | None = None,
) -> tuple[Path, list[dict]]:
    project_root = Path(project_root)
    runs_dir = Path(runs_dir) if runs_dir else project_root / "runs"
    output_path = Path(output_path) if output_path else runs_dir / "event_evidence.csv"
    replication_summary_path = (
        Path(replication_summary_path)
        if replication_summary_path
        else project_root / "replication_summary.csv"
    )
    holdout_review_path = (
        Path(holdout_review_path) if holdout_review_path else project_root / "holdout_review.csv"
    )

    review_map = _load_holdout_review(holdout_review_path)
    holdout_keys = _scan_holdout_catalogs(runs_dir)
    geomag_holdout_counts, nmdb_quality_counts = _scan_overlap_counts(runs_dir)
    event_to_runs = _collect_event_to_runs(holdout_keys, set(review_map.keys()))
    review_event_to_runs = _collect_review_event_to_runs(review_map)
    replication_rows = _read_replication_rows(replication_summary_path)
    replication_map = _aggregate_replication(replication_rows, event_to_runs, review_event_to_runs)

    all_keys = set(review_map.keys()) | holdout_keys | set(replication_map.keys())

    rows: list[dict] = []
    for event_key in sorted(all_keys):
        source_run_id, _, event_id = event_key.partition(":")
        if not source_run_id or not event_id:
            continue

        rep = replication_map.get(event_key, {})
        holdout_q05 = 1 if event_key in holdout_keys else 0
        holdout_q05 = max(holdout_q05, _safe_int(rep.get("holdout_q05", 0)))
        overlap_geomag_holdout = max(
            _safe_int(rep.get("overlap_geomag_holdout", 0)),
            _safe_int(geomag_holdout_counts.get(event_key, 0)),
        )
        overlap_nmdb_quality = max(
            _safe_int(rep.get("overlap_nmdb_quality", 0)),
            _safe_int(nmdb_quality_counts.get(event_key, 0)),
        )
        shift_drop = _safe_str(rep.get("shift_drop"), default="unknown")
        manual_review = _safe_str(review_map.get(event_key), default="unknown")
        status = _derive_status(
            holdout_q05,
            overlap_geomag_holdout,
            overlap_nmdb_quality,
            shift_drop,
            manual_review,
        )

        rows.append(
            {
                "event_key": event_key,
                "source_run_id": source_run_id,
                "event_id": event_id,
                "holdout_q05": holdout_q05,
                "overlap_geomag_holdout": overlap_geomag_holdout,
                "overlap_nmdb_quality": overlap_nmdb_quality,
                "shift_drop": shift_drop,
                "manual_review": manual_review,
                "status": status,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_EVIDENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output_path, rows


def write_evidence_summary(
    project_root: Path,
    runs_dir: Path | None = None,
    event_evidence_path: Path | None = None,
    summary_json_path: Path | None = None,
    summary_csv_path: Path | None = None,
    refresh: bool = True,
) -> tuple[Path, Path, dict]:
    project_root = Path(project_root)
    runs_dir = Path(runs_dir) if runs_dir else project_root / "runs"
    event_evidence_path = (
        Path(event_evidence_path) if event_evidence_path else runs_dir / "event_evidence.csv"
    )
    summary_json_path = (
        Path(summary_json_path) if summary_json_path else runs_dir / "evidence_summary.json"
    )
    summary_csv_path = (
        Path(summary_csv_path) if summary_csv_path else runs_dir / "evidence_summary.csv"
    )

    if refresh or not event_evidence_path.exists():
        event_evidence_path, rows = write_event_evidence(
            project_root=project_root,
            runs_dir=runs_dir,
            output_path=event_evidence_path,
        )
    else:
        with event_evidence_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

    counts = Counter()
    for row in rows:
        counts[_safe_str(row.get("status"), default="rejected")] += 1

    replicated_rows = [
        row for row in rows if _safe_str(row.get("status"), "").lower() == "replicated"
    ]
    replicated_rows.sort(
        key=lambda row: (
            _safe_int(row.get("overlap_nmdb_quality")),
            _safe_int(row.get("overlap_geomag_holdout")),
            _safe_int(row.get("holdout_q05")),
        ),
        reverse=True,
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs_dir": str(runs_dir),
        "event_evidence_path": str(event_evidence_path),
        "counts": {
            "replicated": int(counts.get("replicated", 0)),
            "candidate": int(counts.get("candidate", 0)),
            "rejected": int(counts.get("rejected", 0)),
        },
        "total_events": len(rows),
        "top_replicated": replicated_rows[:10],
    }

    summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with summary_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["status", "count"])
        writer.writeheader()
        writer.writerow({"status": "replicated", "count": payload["counts"]["replicated"]})
        writer.writerow({"status": "candidate", "count": payload["counts"]["candidate"]})
        writer.writerow({"status": "rejected", "count": payload["counts"]["rejected"]})

    return summary_json_path, summary_csv_path, payload
