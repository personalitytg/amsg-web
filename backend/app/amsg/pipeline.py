import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .io import SeriesData, format_timestamp
from .surprise import mutual_surprise, self_surprise
from .tokenize import quantile_edges, tokenize_window


@dataclass
class WindowData:
    source_id: str
    domain_id: str
    window_size: int
    start_idx: int
    end_idx: int
    start_time: object
    end_time: object
    tokens: bytes
    self_surprise: float
    window_index: int
    valid_fraction: float
    is_holdout: bool


@dataclass
class CandidateResult:
    anchor_source_id: str
    anchor_domain_id: str
    other_source_id: str
    other_domain_id: str
    window_size: int
    anchor_start_time: object
    anchor_end_time: object
    other_start_time: object
    other_end_time: object
    self_surprise_anchor: float
    self_surprise_other: float
    anchor_valid_fraction: float
    other_valid_fraction: float
    pair_valid_fraction: float
    edge_novelty: int
    nms: float
    p_value: float
    best_shift: int


@dataclass
class EventResult:
    event_id: str
    event_start: object
    event_end: object
    is_holdout: bool
    baseline_scope: str
    q_value: float | None
    best_p_value: float
    best_nms: float
    edge_novelty_sum: float
    domain_edge_counts: dict[str, int]
    domain_novelty_sums: dict[str, float]
    nmdb_edge_count: int
    nmdb_edge_novelty_sum: float
    nmdb_edge_fraction: float
    nmdb_edges_count: int
    nmdb_pair_valid_fraction_median: float
    nmdb_edges_valid_min: float
    edges_count: int
    sources_involved: list[str]
    domains_involved: list[str]
    cross_domain_edges_count: int
    event_score: float
    orphan_score: float
    top_edges: list[str]
    top_nmdb_edges: list[str]
    score_breakdown: str


def _windows_overlap(win_a: WindowData, win_b: WindowData):
    try:
        return (win_a.start_time <= win_b.end_time) and (win_b.start_time <= win_a.end_time)
    except Exception:
        return True


def _git_commit():
    try:
        output = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return output.decode("utf-8").strip()
    except Exception:
        return None


def build_windows(series: SeriesData, config: dict, holdout_boundary: object | None = None):
    bins = config["bins"]
    step = config["step_size"]
    missing_token = config["missing_token"]
    min_valid_fraction = config["min_valid_fraction"]
    compress_level = config["compress_level"]

    values = series.values
    timestamps = series.timestamps
    global_edges = quantile_edges(values, bins)

    windows_by_size: dict[int, list[WindowData]] = {}
    total_windows = 0

    for size in config["window_sizes"]:
        windows = []
        if values.size < size:
            windows_by_size[size] = windows
            continue
        for start in range(0, values.size - size + 1, step):
            end = start + size
            window_values = values[start:end]
            valid_fraction = np.isfinite(window_values).mean() if window_values.size else 0.0
            if valid_fraction < min_valid_fraction:
                continue
            tokens = tokenize_window(window_values, global_edges, bins, missing_token)
            surprise = self_surprise(tokens, compress_level)
            windows.append(
                WindowData(
                    source_id=series.source_id,
                    domain_id=series.domain_id,
                    window_size=size,
                    start_idx=start,
                    end_idx=end,
                    start_time=timestamps[start],
                    end_time=timestamps[end - 1],
                    tokens=tokens,
                    self_surprise=surprise,
                    window_index=len(windows),
                    valid_fraction=float(valid_fraction),
                    is_holdout=holdout_boundary is not None
                    and _time_sort_key(timestamps[start]) >= _time_sort_key(holdout_boundary),
                )
            )
        windows_by_size[size] = windows
        total_windows += len(windows)

    return windows_by_size, total_windows


def select_candidates(windows_by_size: dict[int, list[WindowData]], top_p: float):
    candidates: list[WindowData] = []
    for size, windows in windows_by_size.items():
        if not windows:
            continue
        k = max(1, int(np.ceil(len(windows) * top_p)))
        top = sorted(windows, key=lambda win: win.self_surprise, reverse=True)[:k]
        candidates.extend(top)
    return candidates


def _compute_p_value(
    observed_nms: float,
    anchor_tokens: bytes,
    other_windows: list[WindowData],
    best_window: WindowData,
    config: dict,
    rng: np.random.RandomState,
):
    null_count = config["null_shifts_count"]
    if null_count <= 0 or len(other_windows) < 2:
        return 1.0

    shift_d = config["shift_d"]
    compress_level = config["compress_level"]
    min_shift_minutes = float(config.get("null_shift_min", 0))
    missing_token = config["missing_token"]
    min_pair_tokens = int(config.get("min_pair_tokens", 0))
    min_pair_valid_fraction = float(config.get("min_pair_valid_fraction", 0))

    eligible_indices = None
    if min_shift_minutes > 0:
        eligible_indices = []
        for idx, window in enumerate(other_windows):
            diff_minutes = _time_diff_minutes(best_window.start_time, window.start_time)
            if diff_minutes is None:
                eligible_indices = None
                break
            if diff_minutes >= min_shift_minutes:
                eligible_indices.append(idx)

    count_ge = 0
    if eligible_indices:
        eligible_array = np.asarray(eligible_indices, dtype=int)
        for _ in range(null_count):
            idx = int(eligible_array[rng.randint(0, eligible_array.size)])
            null_tokens = other_windows[idx].tokens
            nms, _, pair_fraction, pair_tokens = mutual_surprise(
                anchor_tokens,
                null_tokens,
                shift_d,
                compress_level,
                missing_token=missing_token,
                min_pair_tokens=min_pair_tokens,
            )
            if pair_tokens < min_pair_tokens or pair_fraction < min_pair_valid_fraction:
                nms = 0.0
            if nms >= observed_nms:
                count_ge += 1
    else:
        best_index = best_window.window_index
        for _ in range(null_count):
            offset = rng.randint(1, len(other_windows))
            idx = (best_index + offset) % len(other_windows)
            null_tokens = other_windows[idx].tokens
            nms, _, pair_fraction, pair_tokens = mutual_surprise(
                anchor_tokens,
                null_tokens,
                shift_d,
                compress_level,
                missing_token=missing_token,
                min_pair_tokens=min_pair_tokens,
            )
            if pair_tokens < min_pair_tokens or pair_fraction < min_pair_valid_fraction:
                nms = 0.0
            if nms >= observed_nms:
                count_ge += 1

    return (count_ge + 1) / (null_count + 1)


def _format_time(value):
    return format_timestamp(value)


def _time_diff_minutes(value_a, value_b):
    try:
        if isinstance(value_a, np.datetime64) or isinstance(value_b, np.datetime64):
            delta = abs(value_a - value_b)
            return float(delta / np.timedelta64(1, "m"))
    except Exception:
        pass

    if isinstance(value_a, (int, float, np.number)) and isinstance(
        value_b, (int, float, np.number)
    ):
        return abs(float(value_a) - float(value_b)) / 60.0

    try:
        import pandas as pd

        ta = pd.to_datetime(value_a, utc=True, errors="coerce")
        tb = pd.to_datetime(value_b, utc=True, errors="coerce")
        if pd.isna(ta) or pd.isna(tb):
            return None
        return abs((ta - tb).total_seconds()) / 60.0
    except Exception:
        return None


def _pair_key(source_a: str, source_b: str):
    return tuple(sorted([source_a, source_b]))


def _compute_source_self_stats(windows_by_source: dict[str, dict[int, list[WindowData]]]):
    stats = {}
    for source_id, windows_by_size in windows_by_source.items():
        values = []
        for windows in windows_by_size.values():
            values.extend([window.self_surprise for window in windows])
        if values:
            arr = np.asarray(values, dtype=float)
            stats[source_id] = {
                "median": float(np.quantile(arr, 0.5)),
                "q90": float(np.quantile(arr, 0.9)),
                "q99": float(np.quantile(arr, 0.99)),
            }
        else:
            stats[source_id] = {
                "median": 0.0,
                "q90": float("inf"),
                "q99": float("inf"),
            }
    return stats


def _filter_windows_by_holdout(
    windows_by_source: dict[str, dict[int, list[WindowData]]], include_holdout: bool
):
    filtered: dict[str, dict[int, list[WindowData]]] = {}
    for source_id, windows_by_size in windows_by_source.items():
        filtered_sizes: dict[int, list[WindowData]] = {}
        for size, windows in windows_by_size.items():
            if include_holdout:
                filtered_sizes[size] = windows
            else:
                filtered_sizes[size] = [window for window in windows if not window.is_holdout]
        filtered[source_id] = filtered_sizes
    return filtered


def _compute_holdout_boundary(series_list: list[SeriesData], ratio: float, mode: str | None):
    if ratio <= 0:
        return None
    if mode is not None and mode != "time":
        raise ValueError("holdout_mode must be 'time' or null")
    if not series_list:
        return None
    times = series_list[0].timestamps
    if times is None or len(times) == 0:
        return None
    try:
        import pandas as pd

        ts = pd.to_datetime(times, utc=True, errors="coerce")
        ts = ts.dropna()
        if ts.empty:
            return None
        ts = ts.sort_values()
        split_idx = int(math.floor(len(ts) * (1 - ratio)))
        if split_idx <= 0 or split_idx >= len(ts):
            raise ValueError("holdout_ratio results in empty train/test split.")
        return ts.iloc[split_idx]
    except Exception:
        split_idx = int(math.floor(len(times) * (1 - ratio)))
        if split_idx <= 0 or split_idx >= len(times):
            raise ValueError("holdout_ratio results in empty train/test split.")
        return times[split_idx]


def _apply_fdr(events: list[EventResult]):
    holdout_events = [evt for evt in events if evt.is_holdout]
    if not holdout_events:
        for evt in events:
            evt.q_value = None
        return
    pvals = np.asarray([evt.best_p_value for evt in holdout_events], dtype=float)
    order = np.argsort(pvals)
    ranked = pvals[order]
    m = float(len(ranked))
    qvals = ranked * m / (np.arange(1, len(ranked) + 1))
    qvals = np.minimum.accumulate(qvals[::-1])[::-1]
    qvals = np.clip(qvals, 0.0, 1.0)
    for idx, qval in zip(order, qvals):
        holdout_events[idx].q_value = float(qval)
    for evt in events:
        if not evt.is_holdout:
            evt.q_value = None


def _compute_pair_baseline(
    windows_by_source: dict[str, dict[int, list[WindowData]]],
    config: dict,
):
    sources = sorted(windows_by_source.keys())
    missing_token = config["missing_token"]
    min_pair_tokens = int(config.get("min_pair_tokens", 0))
    min_pair_valid_fraction = float(config.get("min_pair_valid_fraction", 0))
    shift_d = config["shift_d"]
    compress_level = config["compress_level"]

    pair_stats: dict[tuple[tuple[str, str], int], dict[str, float]] = {}

    for idx_a, source_a in enumerate(sources):
        for idx_b in range(idx_a + 1, len(sources)):
            source_b = sources[idx_b]
            windows_a_by_size = windows_by_source[source_a]
            windows_b_by_size = windows_by_source[source_b]
            common_sizes = set(windows_a_by_size.keys()).intersection(windows_b_by_size.keys())

            for size in common_sizes:
                windows_a = windows_a_by_size.get(size, [])
                windows_b = windows_b_by_size.get(size, [])
                if not windows_a or not windows_b:
                    continue

                index_b = {window.start_idx: window for window in windows_b}
                values = []
                for window_a in windows_a:
                    window_b = index_b.get(window_a.start_idx)
                    if window_b is None:
                        continue
                    nms, _, pair_fraction, pair_tokens = mutual_surprise(
                        window_a.tokens,
                        window_b.tokens,
                        shift_d,
                        compress_level,
                        missing_token=missing_token,
                        min_pair_tokens=min_pair_tokens,
                    )
                    if pair_tokens < min_pair_tokens or pair_fraction < min_pair_valid_fraction:
                        continue
                    values.append(nms)

                if values:
                    arr = np.asarray(values, dtype=float)
                    median = float(np.quantile(arr, 0.5))
                    q90 = float(np.quantile(arr, 0.9))
                    q99 = float(np.quantile(arr, 0.99))
                    count = int(arr.size)
                else:
                    median = 0.0
                    q90 = 1.0
                    q99 = 1.0
                    count = 0

                pair_stats[(_pair_key(source_a, source_b), size)] = {
                    "median": median,
                    "q90": q90,
                    "q99": q99,
                    "count": count,
                }

    return pair_stats


def _build_partner_map(pair_stats: dict[tuple[tuple[str, str], int], dict[str, float]], k: int):
    pair_medians: dict[tuple[str, str], float] = {}
    for (pair_key, _size), stats in pair_stats.items():
        current = pair_medians.get(pair_key)
        median = stats["median"]
        if current is None or median > current:
            pair_medians[pair_key] = median

    partner_map: dict[str, list[str]] = {}
    for (source_a, source_b), median in pair_medians.items():
        partner_map.setdefault(source_a, []).append((source_b, median))
        partner_map.setdefault(source_b, []).append((source_a, median))

    top_partners: dict[str, list[str]] = {}
    for source, entries in partner_map.items():
        entries_sorted = sorted(entries, key=lambda item: item[1], reverse=True)
        top_partners[source] = [item[0] for item in entries_sorted[:k]]
    return top_partners


def _edge_novelty(nms: float, pair_stats: dict, source_a: str, source_b: str, size: int):
    stats = pair_stats.get((_pair_key(source_a, source_b), size))
    if not stats:
        return 0
    q90 = stats["q90"]
    q99 = stats["q99"]
    if nms <= q90:
        return 0
    if nms <= q99:
        return 1
    return 2


def _format_edge(item: CandidateResult):
    return (
        f"{item.anchor_source_id}-{item.other_source_id}:"
        f"{item.edge_novelty}/{item.nms:.3f}/{item.p_value:.3f}"
    )


def _format_domain_metrics(values: dict[str, float]):
    parts = []
    for key in sorted(values.keys()):
        value = values[key]
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        parts.append(f"{key}={value}")
    return "|".join(parts)


def _time_sort_key(value):
    if isinstance(value, np.datetime64):
        return float(value.astype("datetime64[ns]").astype("int64"))
    if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
        return float(value)

    try:
        import pandas as pd

        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return 0.0
        return float(ts.value)
    except Exception:
        return 0.0


def _min_time(value_a, value_b):
    return value_a if _time_sort_key(value_a) <= _time_sort_key(value_b) else value_b


def _max_time(value_a, value_b):
    return value_a if _time_sort_key(value_a) >= _time_sort_key(value_b) else value_b


def consolidate_events(
    results: list[CandidateResult],
    merge_gap_minutes: float,
    partner_map: dict[str, list[str]],
    source_self_stats: dict[str, dict[str, float]],
    holdout_boundary: object | None = None,
):
    if not results:
        return []

    entries = []
    for item in results:
        start = _min_time(item.anchor_start_time, item.other_start_time)
        end = _max_time(item.anchor_end_time, item.other_end_time)
        entries.append({"start": start, "end": end, "item": item})

    entries.sort(key=lambda entry: _time_sort_key(entry["start"]))

    clusters: list[list[CandidateResult]] = []
    current_cluster: list[CandidateResult] = []
    current_end = None

    for entry in entries:
        if not current_cluster:
            current_cluster = [entry["item"]]
            current_end = entry["end"]
            continue

        overlap = _time_sort_key(entry["start"]) <= _time_sort_key(current_end)
        gap_minutes = _time_diff_minutes(current_end, entry["start"])

        if overlap or (gap_minutes is not None and gap_minutes <= merge_gap_minutes):
            current_cluster.append(entry["item"])
            current_end = _max_time(current_end, entry["end"])
        else:
            clusters.append(current_cluster)
            current_cluster = [entry["item"]]
            current_end = entry["end"]

    if current_cluster:
        clusters.append(current_cluster)

    events: list[EventResult] = []
    for idx, cluster in enumerate(clusters, start=1):
        event_start = _min_time(cluster[0].anchor_start_time, cluster[0].other_start_time)
        event_end = _max_time(cluster[0].anchor_end_time, cluster[0].other_end_time)
        is_holdout = holdout_boundary is not None and _time_sort_key(event_start) >= _time_sort_key(
            holdout_boundary
        )
        baseline_scope = "test" if is_holdout else "train"
        best_p_value = cluster[0].p_value
        best_nms = cluster[0].nms
        edge_novelty_sum = 0.0
        sources = set()
        domains = set()
        cross_domain_edges = 0
        per_source_self = {}
        domain_edge_counts: dict[str, int] = {}
        domain_novelty_sums: dict[str, float] = {}
        nmdb_pair_fractions: list[float] = []

        for item in cluster:
            event_start = _min_time(event_start, _min_time(item.anchor_start_time, item.other_start_time))
            event_end = _max_time(event_end, _max_time(item.anchor_end_time, item.other_end_time))
            best_p_value = min(best_p_value, item.p_value)
            best_nms = max(best_nms, item.nms)
            edge_novelty_sum += item.edge_novelty
            sources.update([item.anchor_source_id, item.other_source_id])
            domains.update([item.anchor_domain_id, item.other_domain_id])
            if item.anchor_domain_id != item.other_domain_id:
                cross_domain_edges += 1
            edge_domains = {item.anchor_domain_id, item.other_domain_id}
            for domain_id in edge_domains:
                domain_edge_counts[domain_id] = domain_edge_counts.get(domain_id, 0) + 1
                domain_novelty_sums[domain_id] = domain_novelty_sums.get(domain_id, 0.0) + item.edge_novelty
            if item.anchor_source_id.startswith("nmdb_") or item.other_source_id.startswith("nmdb_"):
                nmdb_pair_fractions.append(item.pair_valid_fraction)
            per_source_self[item.anchor_source_id] = max(
                per_source_self.get(item.anchor_source_id, 0.0),
                item.self_surprise_anchor,
            )
            per_source_self[item.other_source_id] = max(
                per_source_self.get(item.other_source_id, 0.0),
                item.self_surprise_other,
            )

        event_score = edge_novelty_sum * (1 + 0.1 * cross_domain_edges)

        sorted_edges = sorted(
            cluster,
            key=lambda item: (-item.edge_novelty, -item.nms, item.p_value),
        )
        top_edges = [_format_edge(item) for item in sorted_edges[:5]]
        nmdb_edges = [
            item
            for item in sorted_edges
            if item.anchor_source_id.startswith("nmdb_")
            or item.other_source_id.startswith("nmdb_")
        ]
        top_nmdb_edges = [_format_edge(item) for item in nmdb_edges[:3]]
        score_breakdown = f"novelty={int(edge_novelty_sum)}; cross={cross_domain_edges}"

        nmdb_edge_count = domain_edge_counts.get("nmdb_cosmicray", 0)
        nmdb_edge_novelty_sum = domain_novelty_sums.get("nmdb_cosmicray", 0.0)
        nmdb_edge_fraction = nmdb_edge_count / len(cluster) if cluster else 0.0
        nmdb_edges_count = len(nmdb_pair_fractions)
        nmdb_pair_valid_fraction_median = (
            float(np.median(nmdb_pair_fractions)) if nmdb_pair_fractions else 0.0
        )
        nmdb_edges_valid_min = float(min(nmdb_pair_fractions)) if nmdb_pair_fractions else 0.0

        orphan_score = 0.0
        for source_id, self_value in per_source_self.items():
            threshold = source_self_stats.get(source_id, {}).get("q90", float("inf"))
            if self_value < threshold:
                continue
            partners = partner_map.get(source_id, [])
            if not partners:
                continue
            partner_anomalous = False
            for partner_id in partners:
                partner_threshold = source_self_stats.get(partner_id, {}).get(
                    "q90", float("inf")
                )
                partner_value = per_source_self.get(partner_id)
                if partner_value is not None and partner_value >= partner_threshold:
                    partner_anomalous = True
                    break
            if not partner_anomalous:
                orphan_score += 1.0

        events.append(
            EventResult(
                event_id=f"e{idx:04d}",
                event_start=event_start,
                event_end=event_end,
                is_holdout=is_holdout,
                baseline_scope=baseline_scope,
                q_value=None,
                best_p_value=best_p_value,
                best_nms=best_nms,
                edge_novelty_sum=edge_novelty_sum,
                domain_edge_counts=domain_edge_counts,
                domain_novelty_sums=domain_novelty_sums,
                nmdb_edge_count=nmdb_edge_count,
                nmdb_edge_novelty_sum=nmdb_edge_novelty_sum,
                nmdb_edge_fraction=nmdb_edge_fraction,
                nmdb_edges_count=nmdb_edges_count,
                nmdb_pair_valid_fraction_median=nmdb_pair_valid_fraction_median,
                nmdb_edges_valid_min=nmdb_edges_valid_min,
                edges_count=len(cluster),
                sources_involved=sorted(sources),
                domains_involved=sorted(domains),
                cross_domain_edges_count=cross_domain_edges,
                event_score=event_score,
                orphan_score=orphan_score,
                top_edges=top_edges,
                top_nmdb_edges=top_nmdb_edges,
                score_breakdown=score_breakdown,
            )
        )

    return events


def run_pipeline(
    series_list: list[SeriesData],
    config: dict,
    run_dir: Path,
    return_events: bool = False,
):
    run_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.RandomState(config["seed"])
    holdout_ratio = float(config.get("holdout_ratio", 0.0))
    holdout_mode = config.get("holdout_mode", "time")
    holdout_boundary = _compute_holdout_boundary(series_list, holdout_ratio, holdout_mode)

    windows_by_source: dict[str, dict[int, list[WindowData]]] = {}
    candidates_by_source: dict[str, list[WindowData]] = {}
    window_counts = {}
    candidate_window_count = 0

    for series in series_list:
        windows_by_size, total_windows = build_windows(series, config, holdout_boundary)
        windows_by_source[series.source_id] = windows_by_size
        candidates = select_candidates(windows_by_size, config["top_p"])
        candidates_by_source[series.source_id] = candidates
        candidate_window_count += len(candidates)
        window_counts[series.source_id] = total_windows

    train_windows_by_source = _filter_windows_by_holdout(windows_by_source, include_holdout=False)
    baseline_stats = _compute_pair_baseline(train_windows_by_source, config)
    source_self_stats = _compute_source_self_stats(train_windows_by_source)
    orphan_partner_k = int(config.get("orphan_partner_k", 3))
    partner_map = _build_partner_map(baseline_stats, orphan_partner_k)

    results: list[CandidateResult] = []
    sources = sorted(series_list, key=lambda s: s.source_id)

    for idx_a, source_a in enumerate(sources):
        for idx_b, source_b in enumerate(sources):
            if idx_a == idx_b:
                continue
            for candidate in candidates_by_source[source_a.source_id]:
                windows_other = windows_by_source[source_b.source_id].get(
                    candidate.window_size, []
                )
                if not windows_other:
                    continue

                min_pair_valid_fraction = float(config.get("min_pair_valid_fraction", 0))
                min_pair_tokens = int(config.get("min_pair_tokens", 0))
                missing_token = config["missing_token"]

                best_nms = -1.0
                best_shift = 0
                best_window = None
                best_pair_fraction = 0.0
                for other in windows_other:
                    if not _windows_overlap(candidate, other):
                        continue
                    nms, shift, pair_fraction, pair_tokens = mutual_surprise(
                        candidate.tokens,
                        other.tokens,
                        config["shift_d"],
                        config["compress_level"],
                        missing_token=missing_token,
                        min_pair_tokens=min_pair_tokens,
                    )
                    if pair_tokens < min_pair_tokens or pair_fraction < min_pair_valid_fraction:
                        continue
                    if nms > best_nms:
                        best_nms = nms
                        best_shift = shift
                        best_window = other
                        best_pair_fraction = pair_fraction

                if best_window is None:
                    continue

                edge_novelty = _edge_novelty(
                    best_nms,
                    baseline_stats,
                    source_a.source_id,
                    source_b.source_id,
                    candidate.window_size,
                )

                p_value = _compute_p_value(
                    best_nms,
                    candidate.tokens,
                    windows_other,
                    best_window,
                    config,
                    rng,
                )

                results.append(
                    CandidateResult(
                        anchor_source_id=source_a.source_id,
                        anchor_domain_id=source_a.domain_id,
                        other_source_id=source_b.source_id,
                        other_domain_id=source_b.domain_id,
                        window_size=candidate.window_size,
                        anchor_start_time=candidate.start_time,
                        anchor_end_time=candidate.end_time,
                        other_start_time=best_window.start_time,
                        other_end_time=best_window.end_time,
                        self_surprise_anchor=candidate.self_surprise,
                        self_surprise_other=best_window.self_surprise,
                        anchor_valid_fraction=candidate.valid_fraction,
                        other_valid_fraction=best_window.valid_fraction,
                        pair_valid_fraction=best_pair_fraction,
                        edge_novelty=edge_novelty,
                        nms=best_nms,
                        p_value=p_value,
                        best_shift=best_shift,
                    )
                )

    results_sorted = sorted(results, key=lambda r: r.nms, reverse=True)

    events = consolidate_events(
        results_sorted,
        config.get("merge_gap_minutes", 30),
        partner_map,
        source_self_stats,
        holdout_boundary=holdout_boundary,
    )
    _apply_fdr(events)

    _write_outputs(
        series_list,
        config,
        run_dir,
        window_counts,
        candidate_window_count,
        results_sorted,
        events,
    )

    if return_events:
        return results_sorted, events
    return results_sorted


def _write_outputs(
    series_list: list[SeriesData],
    config: dict,
    run_dir: Path,
    window_counts: dict[str, int],
    candidate_window_count: int,
    results_sorted: list[CandidateResult],
    events: list[EventResult],
):
    run_id = run_dir.name
    top_candidates = results_sorted[:10]
    events_sorted = sorted(
        events,
        key=lambda evt: (-evt.event_score, evt.best_p_value, -evt.best_nms),
    )
    top_events = events_sorted[:10]

    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "config": config,
        "sources": [
            {
                "source_id": series.source_id,
                "domain_id": series.domain_id,
                "path": str(series.path) if series.path else None,
                "points": int(series.values.size),
                "start_time": series.start_time(),
                "end_time": series.end_time(),
            }
            for series in series_list
        ],
        "stats": {
            "total_points": int(sum(series.values.size for series in series_list)),
            "total_windows": int(sum(window_counts.values())),
            "total_candidates": int(candidate_window_count),
            "total_pairs": int(len(results_sorted)),
            "total_events": int(len(events)),
        },
        "holdout_summary": {
            "holdout_ratio": float(config.get("holdout_ratio", 0.0)),
            "holdout_mode": config.get("holdout_mode", "time"),
            "test_events": int(sum(1 for evt in events if evt.is_holdout)),
            "q_value_lt_0.1": int(
                sum(1 for evt in events if evt.is_holdout and evt.q_value is not None and evt.q_value < 0.1)
            ),
            "q_value_lt_0.05": int(
                sum(1 for evt in events if evt.is_holdout and evt.q_value is not None and evt.q_value < 0.05)
            ),
        },
        "top_candidates": [
            {
                "anchor_source_id": item.anchor_source_id,
                "other_source_id": item.other_source_id,
                "window_size": item.window_size,
                "start_time": _format_time(item.anchor_start_time),
                "end_time": _format_time(item.anchor_end_time),
                "nms": item.nms,
                "p_value": item.p_value,
                "anchor_valid_fraction": item.anchor_valid_fraction,
                "other_valid_fraction": item.other_valid_fraction,
                "pair_valid_fraction": item.pair_valid_fraction,
                "edge_novelty": item.edge_novelty,
            }
            for item in top_candidates
        ],
        "top_events": [
            {
                "event_id": item.event_id,
                "event_start": _format_time(item.event_start),
                "event_end": _format_time(item.event_end),
                "is_holdout": item.is_holdout,
                "baseline_scope": item.baseline_scope,
                "q_value": item.q_value,
                "event_score": item.event_score,
                "best_p_value": item.best_p_value,
                "best_nms": item.best_nms,
                "edge_novelty_sum": item.edge_novelty_sum,
                "orphan_score": item.orphan_score,
                "nmdb_edge_count": item.nmdb_edge_count,
                "nmdb_edge_novelty_sum": item.nmdb_edge_novelty_sum,
                "nmdb_edge_fraction": item.nmdb_edge_fraction,
                "nmdb_edges_count": item.nmdb_edges_count,
                "nmdb_pair_valid_fraction_median": item.nmdb_pair_valid_fraction_median,
                "nmdb_edges_valid_min": item.nmdb_edges_valid_min,
                "edges_count": item.edges_count,
                "cross_domain_edges_count": item.cross_domain_edges_count,
                "sources_involved": item.sources_involved,
                "domains_involved": item.domains_involved,
                "top_edges": item.top_edges[:3],
            }
            for item in top_events
        ],
    }

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    try:
        import pandas as pd

        rows = []
        for item in results_sorted:
            rows.append(
                {
                    "run_id": run_id,
                    "anchor_source_id": item.anchor_source_id,
                    "anchor_domain_id": item.anchor_domain_id,
                    "other_source_id": item.other_source_id,
                    "other_domain_id": item.other_domain_id,
                    "window_size": item.window_size,
                    "anchor_start_time": _format_time(item.anchor_start_time),
                    "anchor_end_time": _format_time(item.anchor_end_time),
                    "other_start_time": _format_time(item.other_start_time),
                    "other_end_time": _format_time(item.other_end_time),
                    "self_surprise_anchor": item.self_surprise_anchor,
                    "self_surprise_other": item.self_surprise_other,
                    "anchor_valid_fraction": item.anchor_valid_fraction,
                    "other_valid_fraction": item.other_valid_fraction,
                    "pair_valid_fraction": item.pair_valid_fraction,
                    "edge_novelty": item.edge_novelty,
                    "nms": item.nms,
                    "p_value": item.p_value,
                    "best_shift": item.best_shift,
                }
            )
        df = pd.DataFrame(rows)
        df.to_csv(run_dir / "top_candidates.csv", index=False)
    except Exception:
        fallback_path = run_dir / "top_candidates.csv"
        with fallback_path.open("w", encoding="utf-8") as handle:
            handle.write(
                "run_id,anchor_source_id,anchor_domain_id,other_source_id,other_domain_id,window_size,anchor_start_time,anchor_end_time,other_start_time,other_end_time,self_surprise_anchor,self_surprise_other,anchor_valid_fraction,other_valid_fraction,pair_valid_fraction,edge_novelty,nms,p_value,best_shift\n"
            )
            for item in results_sorted:
                handle.write(
                    f"{run_id},{item.anchor_source_id},{item.anchor_domain_id},{item.other_source_id},{item.other_domain_id},{item.window_size},{_format_time(item.anchor_start_time)},{_format_time(item.anchor_end_time)},{_format_time(item.other_start_time)},{_format_time(item.other_end_time)},{item.self_surprise_anchor},{item.self_surprise_other},{item.anchor_valid_fraction},{item.other_valid_fraction},{item.pair_valid_fraction},{item.edge_novelty},{item.nms},{item.p_value},{item.best_shift}\n"
                )

    _write_events_csv(run_dir, events_sorted, run_id)


def make_run_dir(base_dir: Path):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"run_{ts}"
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_events_csv(run_dir: Path, events: list[EventResult], run_id: str):
    try:
        import pandas as pd

        rows = []
        for item in events:
            rows.append(
                {
                    "run_id": run_id,
                    "event_id": item.event_id,
                    "event_start": _format_time(item.event_start),
                    "event_end": _format_time(item.event_end),
                    "is_holdout": item.is_holdout,
                    "baseline_scope": item.baseline_scope,
                    "q_value": item.q_value,
                    "event_score": item.event_score,
                    "best_p_value": item.best_p_value,
                    "best_nms": item.best_nms,
                    "edge_novelty_sum": item.edge_novelty_sum,
                    "orphan_score": item.orphan_score,
                    "top_edges": "|".join(item.top_edges),
                    "top_nmdb_edges": "|".join(item.top_nmdb_edges),
                    "score_breakdown": item.score_breakdown,
                    "domain_edge_counts": _format_domain_metrics(item.domain_edge_counts),
                    "domain_novelty_sums": _format_domain_metrics(item.domain_novelty_sums),
                    "nmdb_edge_count": item.nmdb_edge_count,
                    "nmdb_edge_novelty_sum": item.nmdb_edge_novelty_sum,
                    "nmdb_edge_fraction": item.nmdb_edge_fraction,
                    "nmdb_edges_count": item.nmdb_edges_count,
                    "nmdb_pair_valid_fraction_median": item.nmdb_pair_valid_fraction_median,
                    "nmdb_edges_valid_min": item.nmdb_edges_valid_min,
                    "edges_count": item.edges_count,
                    "cross_domain_edges_count": item.cross_domain_edges_count,
                    "sources_involved": "|".join(item.sources_involved),
                    "domains_involved": "|".join(item.domains_involved),
                }
            )
        df = pd.DataFrame(rows)
        df.to_csv(run_dir / "events.csv", index=False)
        return
    except Exception:
        pass

    fallback_path = run_dir / "events.csv"
    with fallback_path.open("w", encoding="utf-8") as handle:
        handle.write(
            "run_id,event_id,event_start,event_end,is_holdout,baseline_scope,q_value,event_score,best_p_value,best_nms,edge_novelty_sum,orphan_score,top_edges,top_nmdb_edges,score_breakdown,domain_edge_counts,domain_novelty_sums,nmdb_edge_count,nmdb_edge_novelty_sum,nmdb_edge_fraction,nmdb_edges_count,nmdb_pair_valid_fraction_median,nmdb_edges_valid_min,edges_count,cross_domain_edges_count,sources_involved,domains_involved\n"
        )
        for item in events:
            sources = "|".join(item.sources_involved)
            domains = "|".join(item.domains_involved)
            top_edges = "|".join(item.top_edges)
            top_nmdb_edges = "|".join(item.top_nmdb_edges)
            domain_edge_counts = _format_domain_metrics(item.domain_edge_counts)
            domain_novelty_sums = _format_domain_metrics(item.domain_novelty_sums)
            q_value = "" if item.q_value is None else item.q_value
            handle.write(
                f"{run_id},{item.event_id},{_format_time(item.event_start)},{_format_time(item.event_end)},{item.is_holdout},{item.baseline_scope},{q_value},{item.event_score},{item.best_p_value},{item.best_nms},{item.edge_novelty_sum},{item.orphan_score},{top_edges},{top_nmdb_edges},{item.score_breakdown},{domain_edge_counts},{domain_novelty_sums},{item.nmdb_edge_count},{item.nmdb_edge_novelty_sum},{item.nmdb_edge_fraction},{item.nmdb_edges_count},{item.nmdb_pair_valid_fraction_median},{item.nmdb_edges_valid_min},{item.edges_count},{item.cross_domain_edges_count},{sources},{domains}\n"
            )
