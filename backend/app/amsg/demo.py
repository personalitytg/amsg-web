from pathlib import Path

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG, load_config
from .io import SeriesData
from .pipeline import make_run_dir, run_pipeline


def _moving_average(values: np.ndarray, window: int):
    if window <= 1:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def generate_demo_series(seed: int = 7):
    rng = np.random.RandomState(seed)
    length = 1200
    timestamps = pd.date_range("2024-01-01", periods=length, freq="s", tz="UTC").to_numpy()

    base_a = rng.normal(0.0, 1.0, length)
    base_b = rng.normal(0.0, 1.0, length)
    base_c = rng.normal(0.0, 1.0, length)

    pattern_len = 128
    event_start = 400
    pattern = np.sin(np.linspace(0, 6 * np.pi, pattern_len)) * 2.0

    series_a = base_a.copy()
    series_b = base_b.copy()
    series_c = base_c.copy()

    series_a[event_start : event_start + pattern_len] += pattern
    series_b[event_start + 2 : event_start + 2 + pattern_len] += pattern * 1.4 + 0.5
    series_b = _moving_average(series_b, 3)

    sources = [
        SeriesData(
            source_id="source_a",
            domain_id="domain_1",
            timestamps=timestamps,
            values=series_a,
            quality=None,
            path=None,
        ),
        SeriesData(
            source_id="source_b",
            domain_id="domain_2",
            timestamps=timestamps,
            values=series_b,
            quality=None,
            path=None,
        ),
        SeriesData(
            source_id="source_c",
            domain_id="domain_3",
            timestamps=timestamps,
            values=series_c,
            quality=None,
            path=None,
        ),
    ]

    event_window = (event_start, event_start + pattern_len - 1)
    return sources, event_window


def run_demo(project_root: Path):
    config_path = project_root / "configs" / "default.yaml"
    if config_path.exists():
        config = load_config(config_path)
    else:
        config = dict(DEFAULT_CONFIG)

    config["top_p"] = max(config["top_p"], 0.1)
    config["null_shifts_count"] = min(config["null_shifts_count"], 30)

    sources, event_window = generate_demo_series()

    run_dir = make_run_dir(project_root / "runs")
    results, events = run_pipeline(sources, config, run_dir, return_events=True)

    print("Demo run:", run_dir)
    if events:
        best_event = sorted(events, key=lambda evt: evt.event_score, reverse=True)[0]
        print("Top event:")
        print(
            f"  event={best_event.event_id} score={best_event.event_score:.3f} orphan={best_event.orphan_score:.1f} nms={best_event.best_nms:.3f} p_value={best_event.best_p_value:.3f}"
        )
    elif results:
        best = results[0]
        print("Top candidate:")
        print(
            f"  sources={best.anchor_source_id}->{best.other_source_id} window={best.window_size} nms={best.nms:.3f} p_value={best.p_value:.3f}"
        )
    else:
        print("No candidates found.")

    print(f"Expected event index range: {event_window}")

    return run_dir
