import csv
import statistics
from pathlib import Path

import pandas as pd


def _parse_domain_metrics(raw) -> dict[str, float]:
    if raw is None:
        return {}
    if isinstance(raw, float) and pd.isna(raw):
        return {}
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return {}
    metrics: dict[str, float] = {}
    for part in text.split("|"):
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        if number.is_integer():
            number = int(number)
        metrics[key] = number
    return metrics


def _load_events(run_dir: Path) -> pd.DataFrame:
    events_path = run_dir / "events.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Missing events.csv: {events_path}")
    events = pd.read_csv(events_path)
    events["event_start"] = pd.to_datetime(events["event_start"], utc=True, errors="coerce")
    events["event_end"] = pd.to_datetime(events["event_end"], utc=True, errors="coerce")
    events = events.dropna(subset=["event_start", "event_end"])
    return events


def _load_candidates(run_dir: Path) -> pd.DataFrame:
    candidates_path = run_dir / "top_candidates.csv"
    if not candidates_path.exists():
        raise FileNotFoundError(f"Missing top_candidates.csv: {candidates_path}")
    candidates = pd.read_csv(candidates_path)
    candidates["anchor_start_time"] = pd.to_datetime(
        candidates["anchor_start_time"], utc=True, errors="coerce"
    )
    candidates["anchor_end_time"] = pd.to_datetime(
        candidates["anchor_end_time"], utc=True, errors="coerce"
    )
    candidates["other_start_time"] = pd.to_datetime(
        candidates["other_start_time"], utc=True, errors="coerce"
    )
    candidates["other_end_time"] = pd.to_datetime(
        candidates["other_end_time"], utc=True, errors="coerce"
    )
    candidates = candidates.dropna(
        subset=["anchor_start_time", "anchor_end_time", "other_start_time", "other_end_time"]
    )
    return candidates


def _build_event_domain_stats(events: pd.DataFrame, candidates: pd.DataFrame):
    event_entries = []
    for _, row in events.iterrows():
        event_entries.append((row.get("event_id"), row["event_start"], row["event_end"]))

    stats: dict[str, dict[str, dict[str, float]]] = {}
    for event_id, _start, _end in event_entries:
        stats[str(event_id)] = {"edge_counts": {}, "novelty_sums": {}}

    for _, row in candidates.iterrows():
        start = min(row["anchor_start_time"], row["other_start_time"])
        end = max(row["anchor_end_time"], row["other_end_time"])
        if pd.isna(start) or pd.isna(end):
            continue
        edge_novelty = float(row.get("edge_novelty", 0) or 0.0)
        domains = {row.get("anchor_domain_id"), row.get("other_domain_id")}
        for event_id, event_start, event_end in event_entries:
            if start <= event_end and end >= event_start:
                bucket = stats.get(str(event_id))
                if bucket is None:
                    bucket = {"edge_counts": {}, "novelty_sums": {}}
                    stats[str(event_id)] = bucket
                for domain_id in domains:
                    if domain_id is None or pd.isna(domain_id):
                        continue
                    counts = bucket["edge_counts"]
                    sums = bucket["novelty_sums"]
                    counts[domain_id] = counts.get(domain_id, 0) + 1
                    sums[domain_id] = sums.get(domain_id, 0.0) + edge_novelty
                break
    return stats


def _build_event_nmdb_stats(events: pd.DataFrame, candidates: pd.DataFrame):
    event_entries = []
    for _, row in events.iterrows():
        event_entries.append((row.get("event_id"), row["event_start"], row["event_end"]))

    stats: dict[str, dict[str, float | list[float]]] = {}
    for event_id, _start, _end in event_entries:
        stats[str(event_id)] = {"pair_fractions": []}

    for _, row in candidates.iterrows():
        anchor_id = str(row.get("anchor_source_id") or "")
        other_id = str(row.get("other_source_id") or "")
        if not (anchor_id.startswith("nmdb_") or other_id.startswith("nmdb_")):
            continue
        start = min(row["anchor_start_time"], row["other_start_time"])
        end = max(row["anchor_end_time"], row["other_end_time"])
        if pd.isna(start) or pd.isna(end):
            continue
        pair_fraction = float(row.get("pair_valid_fraction", 0.0) or 0.0)
        for event_id, event_start, event_end in event_entries:
            if start <= event_end and end >= event_start:
                bucket = stats.get(str(event_id))
                if bucket is None:
                    bucket = {"pair_fractions": []}
                    stats[str(event_id)] = bucket
                bucket["pair_fractions"].append(pair_fraction)
                break

    metrics = {}
    for event_id, bucket in stats.items():
        values = bucket.get("pair_fractions", [])
        if values:
            median_val = float(statistics.median(values))
            min_val = float(min(values))
        else:
            median_val = 0.0
            min_val = 0.0
        metrics[event_id] = {
            "edges_count": len(values),
            "pair_median": median_val,
            "pair_min": min_val,
        }
    return metrics


def _get_domain_stats(events: pd.DataFrame, run_dir: Path):
    counts_col = "domain_edge_counts"
    sums_col = "domain_novelty_sums"
    has_columns = counts_col in events.columns and sums_col in events.columns
    if has_columns:
        stats = {}
        for _, row in events.iterrows():
            event_id = str(row.get("event_id"))
            stats[event_id] = {
                "edge_counts": _parse_domain_metrics(row.get(counts_col)),
                "novelty_sums": _parse_domain_metrics(row.get(sums_col)),
            }
        return stats

    candidates = _load_candidates(run_dir)
    return _build_event_domain_stats(events, candidates)


def _get_nmdb_stats(events: pd.DataFrame, run_dir: Path):
    count_col = "nmdb_edges_count"
    median_col = "nmdb_pair_valid_fraction_median"
    min_col = "nmdb_edges_valid_min"
    has_columns = (
        count_col in events.columns and median_col in events.columns and min_col in events.columns
    )
    if has_columns:
        stats = {}
        for _, row in events.iterrows():
            event_id = str(row.get("event_id"))
            count_value = row.get(count_col)
            median_value = row.get(median_col)
            min_value = row.get(min_col)
            if pd.isna(count_value):
                count_value = 0
            if pd.isna(median_value):
                median_value = 0.0
            if pd.isna(min_value):
                min_value = 0.0
            stats[event_id] = {
                "edges_count": int(count_value or 0),
                "pair_median": float(median_value or 0.0),
                "pair_min": float(min_value or 0.0),
            }
        return stats

    candidates = _load_candidates(run_dir)
    return _build_event_nmdb_stats(events, candidates)


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(int(value))
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _filter_events(
    events: pd.DataFrame,
    stats: dict[str, dict[str, dict[str, float]]],
    require_domain: str | None,
    min_domain_edges: int,
    min_domain_novelty_sum: float,
    nmdb_stats: dict[str, dict[str, float]],
    min_nmdb_edges: int,
    min_nmdb_pair_median: float,
    require_holdout: bool,
    max_q_value: float | None,
):
    if (
        not require_domain
        and min_nmdb_edges <= 0
        and min_nmdb_pair_median <= 0
        and not require_holdout
        and max_q_value is None
    ):
        return events
    if require_domain is not None:
        require_domain = str(require_domain)
    keep_rows = []
    for _, row in events.iterrows():
        event_id = str(row.get("event_id"))
        if require_holdout:
            if "is_holdout" not in events.columns:
                continue
            if not _to_bool(row.get("is_holdout")):
                continue
        if max_q_value is not None:
            if "q_value" not in events.columns:
                continue
            q_value = row.get("q_value")
            if pd.isna(q_value):
                continue
            try:
                q_value = float(q_value)
            except ValueError:
                continue
            if q_value > max_q_value:
                continue
        if require_domain:
            bucket = stats.get(event_id, {"edge_counts": {}, "novelty_sums": {}})
            edge_counts = bucket.get("edge_counts", {})
            novelty_sums = bucket.get("novelty_sums", {})
            if edge_counts.get(require_domain, 0) < min_domain_edges:
                continue
            if novelty_sums.get(require_domain, 0.0) < min_domain_novelty_sum:
                continue
        if min_nmdb_edges > 0 or min_nmdb_pair_median > 0:
            nmdb_bucket = nmdb_stats.get(event_id, {"edges_count": 0, "pair_median": 0.0})
            if nmdb_bucket.get("edges_count", 0) < min_nmdb_edges:
                continue
            if nmdb_bucket.get("pair_median", 0.0) < min_nmdb_pair_median:
                continue
        keep_rows.append(row)
    if not keep_rows:
        return events.iloc[0:0].copy()
    return pd.DataFrame(keep_rows)


def compute_overlaps(
    run_a: Path,
    run_b: Path,
    window_hours: float,
    output_dir: Path | None = None,
    output_suffix: str | None = None,
    require_domain: str | None = None,
    min_domain_edges: int = 0,
    min_domain_novelty_sum: float = 0.0,
    min_nmdb_edges: int = 0,
    min_nmdb_pair_median: float = 0.0,
    nmdb_filter_side: str = "both",
    holdout_only_a: bool = False,
    holdout_only_b: bool = False,
    max_q_value_a: float | None = None,
    max_q_value_b: float | None = None,
):
    run_a = Path(run_a)
    run_b = Path(run_b)
    events_a = _load_events(run_a)
    events_b = _load_events(run_b)

    if require_domain or min_nmdb_edges > 0 or min_nmdb_pair_median > 0:
        stats_a = _get_domain_stats(events_a, run_a) if require_domain else {}
        stats_b = _get_domain_stats(events_b, run_b) if require_domain else {}
        nmdb_a = (
            _get_nmdb_stats(events_a, run_a)
            if (min_nmdb_edges > 0 or min_nmdb_pair_median > 0)
            else {}
        )
        nmdb_b = (
            _get_nmdb_stats(events_b, run_b)
            if (min_nmdb_edges > 0 or min_nmdb_pair_median > 0)
            else {}
        )
        side = str(nmdb_filter_side or "both").lower()
        if side not in {"a", "b", "both"}:
            raise ValueError("nmdb_filter_side must be 'a', 'b', or 'both'")
        min_nmdb_edges_a = min_nmdb_edges if side in {"a", "both"} else 0
        min_nmdb_edges_b = min_nmdb_edges if side in {"b", "both"} else 0
        min_nmdb_pair_median_a = min_nmdb_pair_median if side in {"a", "both"} else 0.0
        min_nmdb_pair_median_b = min_nmdb_pair_median if side in {"b", "both"} else 0.0
        events_a = _filter_events(
            events_a,
            stats_a,
            require_domain,
            min_domain_edges,
            min_domain_novelty_sum,
            nmdb_a,
            min_nmdb_edges_a,
            min_nmdb_pair_median_a,
            holdout_only_a,
            max_q_value_a,
        )
        events_b = _filter_events(
            events_b,
            stats_b,
            require_domain,
            min_domain_edges,
            min_domain_novelty_sum,
            nmdb_b,
            min_nmdb_edges_b,
            min_nmdb_pair_median_b,
            holdout_only_b,
            max_q_value_b,
        )
    elif holdout_only_a or holdout_only_b or max_q_value_a is not None or max_q_value_b is not None:
        events_a = _filter_events(
            events_a,
            {},
            None,
            0,
            0.0,
            {},
            0,
            0.0,
            holdout_only_a,
            max_q_value_a,
        )
        events_b = _filter_events(
            events_b,
            {},
            None,
            0,
            0.0,
            {},
            0,
            0.0,
            holdout_only_b,
            max_q_value_b,
        )

    if output_dir is None:
        output_dir = run_a.parent
    output_dir = Path(output_dir)

    rows = []
    window_delta = pd.Timedelta(hours=float(window_hours))

    for _, row_a in events_a.iterrows():
        start_a = row_a["event_start"]
        end_a = row_a["event_end"]
        duration_a = (end_a - start_a).total_seconds()
        if duration_a <= 0:
            continue
        for _, row_b in events_b.iterrows():
            start_b = row_b["event_start"]
            end_b = row_b["event_end"]
            duration_b = (end_b - start_b).total_seconds()
            if duration_b <= 0:
                continue

            overlap = min(end_a, end_b) - max(start_a, start_b)
            overlap_seconds = max(0.0, overlap.total_seconds())

            gap = max(start_a, start_b) - min(end_a, end_b)
            gap_seconds = max(0.0, gap.total_seconds())

            near_match = gap <= window_delta
            if overlap_seconds == 0.0 and not near_match:
                continue

            overlap_ratio = overlap_seconds / min(duration_a, duration_b)
            rows.append(
                {
                    "run_a": run_a.name,
                    "event_id_a": row_a.get("event_id"),
                    "start_a": start_a.isoformat(),
                    "end_a": end_a.isoformat(),
                    "duration_hours_a": duration_a / 3600.0,
                    "run_b": run_b.name,
                    "event_id_b": row_b.get("event_id"),
                    "start_b": start_b.isoformat(),
                    "end_b": end_b.isoformat(),
                    "duration_hours_b": duration_b / 3600.0,
                    "overlap_hours": overlap_seconds / 3600.0,
                    "overlap_ratio": overlap_ratio,
                    "gap_hours": gap_seconds / 3600.0,
                    "near_match": bool(near_match),
                }
            )

    rows.sort(
        key=lambda item: (
            item["overlap_ratio"],
            item["overlap_hours"],
            -item["gap_hours"],
        ),
        reverse=True,
    )

    suffix = output_suffix or ""
    output_name = f"overlaps_{run_a.name}__{run_b.name}{suffix}.csv"
    output_path = output_dir / output_name
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
        else:
            writer.writeheader()

    return output_path, rows
