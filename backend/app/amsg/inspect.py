import json
from pathlib import Path

import numpy as np
import pandas as pd

from .hapi import fetch_data, parse_start_end
from .geomag import fetch_geomag_station
from .pageviews import fetch_pageviews_series, resample_pageviews_series, pageviews_source_id
from .omni import OMNI_BASE_URL, OMNI_DATASET_ID, OMNI_PARAMETERS
from .omni_btc import build_omni_btc_sources
from .omni_nmdb import build_omni_nmdb_sources
from .swpc import build_swpc_sources
from .transforms import apply_transform
from .usgs import fetch_usgs_iv


def _load_manifest(run_dir: Path):
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_events(run_dir: Path):
    events_path = run_dir / "events.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Missing events.csv: {events_path}")
    return pd.read_csv(events_path)


def _parse_time(value):
    return pd.to_datetime(value, utc=True, errors="coerce")


def _format_time_index(index: pd.DatetimeIndex):
    return index.map(lambda value: value.isoformat())


def _align_series_map(series_map: dict[str, pd.Series]):
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


def _load_swpc_sources(run_dir: Path, project_root: Path, config: dict):
    inputs_path = run_dir / "inputs_swpc.json"
    if not inputs_path.exists():
        raise FileNotFoundError("inputs_swpc.json not found; inspect supports SWPC runs.")

    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    days = int(payload.get("days", 7))
    freq = payload.get("freq") or config.get("freq") or "1min"
    include_kp = bool(payload.get("include_kp", False))
    expected_sources = [
        item.get("source_id")
        for item in payload.get("sources", [])
        if item.get("source_id")
    ]

    cache_dir = project_root / "data" / "cache" / "swpc"
    sources, _ = build_swpc_sources(cache_dir, days, freq, include_kp=include_kp)

    if expected_sources:
        sources = [source for source in sources if source.source_id in expected_sources]

    series_map = {}
    for source in sources:
        times = pd.to_datetime(source.timestamps, utc=True, errors="coerce")
        if times.isna().all():
            raise RuntimeError(f"Unparseable timestamps for {source.source_id}")
        series_map[source.source_id] = pd.Series(source.values, index=times).sort_index()

    aligned = _align_series_map(series_map)
    if not aligned:
        raise RuntimeError("Failed to align SWPC sources for inspection.")

    return aligned


def _load_omni_sources(run_dir: Path, project_root: Path, config: dict):
    inputs_path = run_dir / "inputs_omni.json"
    if not inputs_path.exists():
        raise FileNotFoundError("inputs_omni.json not found; inspect supports OMNI runs.")

    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    start = payload.get("start")
    end = payload.get("end")
    if not start or not end:
        raise ValueError("inputs_omni.json missing start/end.")

    base_url = payload.get("base_url", OMNI_BASE_URL)
    dataset_id = payload.get("dataset_id", OMNI_DATASET_ID)
    parameters = payload.get("parameters") or OMNI_PARAMETERS
    chunk_days = int(payload.get("chunk_days", 7))
    freq = payload.get("freq") or config.get("freq") or "1min"

    start_dt = pd.to_datetime(start, utc=True, errors="coerce")
    end_dt = pd.to_datetime(end, utc=True, errors="coerce")
    if pd.isna(start_dt) or pd.isna(end_dt):
        start_dt, end_dt = parse_start_end(start, int(payload.get("days", 30)))

    cache_dir = project_root / "data" / "cache" / "hapi"
    df = fetch_data(
        base_url,
        dataset_id,
        start_dt.to_pydatetime(),
        end_dt.to_pydatetime(),
        parameters,
        cache_dir,
        chunk_days=chunk_days,
    )

    time_col = parameters[0]
    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df = df.dropna(subset=[time_col])

    required_cols = ["BZ_GSM", "flow_speed", "proton_density", "SYM_H"]
    for col in required_cols:
        if col not in df.columns:
            raise RuntimeError(f"OMNI data missing column '{col}'.")

    series_map = {
        "omni_bz_gsm": df.set_index(time_col)["BZ_GSM"].resample(freq).mean(),
        "omni_flow_speed": df.set_index(time_col)["flow_speed"].resample(freq).mean(),
        "omni_proton_density": df.set_index(time_col)["proton_density"].resample(freq).mean(),
        "omni_sym_h": df.set_index(time_col)["SYM_H"].resample(freq).mean(),
    }

    aligned = _align_series_map(series_map)
    if not aligned:
        raise RuntimeError("Failed to align OMNI sources for inspection.")

    return aligned


def _load_omni_nmdb_sources(run_dir: Path, project_root: Path, config: dict):
    inputs_path = run_dir / "inputs_omni_nmdb.json"
    if not inputs_path.exists():
        raise FileNotFoundError("inputs_omni_nmdb.json not found.")

    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    start = payload.get("start")
    days = int(payload.get("days", 30))
    stations = payload.get("stations") or []
    if not start or not stations:
        raise ValueError("inputs_omni_nmdb.json missing start or stations.")

    freq = payload.get("freq") or config.get("freq") or "1min"
    chunk_days = int(payload.get("chunk_days", 7))
    nmdb_cfg = payload.get("nmdb", {})
    dtype = nmdb_cfg.get("dtype", "corr_for_efficiency")
    tabchoice = nmdb_cfg.get("tabchoice", "ori")
    yunits = int(nmdb_cfg.get("yunits", 0))
    time_offset = nmdb_cfg.get("time_offset")

    cache_dir_hapi = project_root / "data" / "cache" / "hapi"
    cache_dir_nmdb = project_root / "data" / "cache" / "nmdb"
    sources, _, _ = build_omni_nmdb_sources(
        cache_dir_hapi,
        cache_dir_nmdb,
        start,
        days,
        stations,
        freq,
        chunk_days=chunk_days,
        dtype=dtype,
        tabchoice=tabchoice,
        yunits=yunits,
        nmdb_time_offset=time_offset,
    )

    series_map = {}
    for source in sources:
        times = pd.to_datetime(source.timestamps, utc=True, errors="coerce")
        if times.isna().all():
            raise RuntimeError(f"Unparseable timestamps for {source.source_id}")
        series_map[source.source_id] = pd.Series(source.values, index=times).sort_index()

    aligned = _align_series_map(series_map)
    if not aligned:
        raise RuntimeError("Failed to align OMNI+NMDB sources for inspection.")

    return aligned


def _load_omni_btc_sources(run_dir: Path, project_root: Path, config: dict):
    inputs_path = run_dir / "inputs_omni_btc.json"
    if not inputs_path.exists():
        raise FileNotFoundError("inputs_omni_btc.json not found.")

    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    start = payload.get("start")
    days = int(payload.get("days", 30))
    if not start:
        raise ValueError("inputs_omni_btc.json missing start.")

    freq = payload.get("freq") or config.get("freq") or "1min"
    chunk_days = int(payload.get("chunk_days", 7))
    btc_cfg = payload.get("btc", {})
    btc_path = btc_cfg.get("path")
    if not btc_path:
        raise ValueError("inputs_omni_btc.json missing btc path.")
    btc_time_col = btc_cfg.get("time_col", "time")
    btc_price_col = btc_cfg.get("price_col", "close")
    btc_volume_col = btc_cfg.get("volume_col")
    btc_transform = btc_cfg.get("transform", "log_return")
    btc_time_offset = btc_cfg.get("time_offset", "0")

    cache_dir = project_root / "data" / "cache" / "hapi"
    sources, _, _ = build_omni_btc_sources(
        cache_dir,
        start,
        days,
        freq,
        Path(btc_path),
        btc_time_col,
        btc_price_col,
        btc_volume_col,
        btc_transform,
        btc_time_offset,
        chunk_days=chunk_days,
    )

    series_map = {}
    for source in sources:
        times = pd.to_datetime(source.timestamps, utc=True, errors="coerce")
        if times.isna().all():
            raise RuntimeError(f"Unparseable timestamps for {source.source_id}")
        series_map[source.source_id] = pd.Series(source.values, index=times).sort_index()

    aligned = _align_series_map(series_map)
    if not aligned:
        raise RuntimeError("Failed to align OMNI+BTC sources for inspection.")

    return aligned


def _load_usgs_sources(run_dir: Path, project_root: Path, config: dict):
    inputs_path = run_dir / "inputs_usgs.json"
    if not inputs_path.exists():
        raise FileNotFoundError("inputs_usgs.json not found.")

    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    start = payload.get("start")
    end = payload.get("end")
    sites = payload.get("sites") or []
    params = payload.get("params") or []
    if not start or not end or not sites or not params:
        raise ValueError("inputs_usgs.json missing start/end/sites/params.")

    freq = payload.get("freq") or config.get("freq") or "15min"
    transform = (payload.get("transform") or "identity").strip().lower()

    cache_dir = project_root / "data" / "cache" / "usgs"
    series_map = fetch_usgs_iv(sites, params, start, end, cache_dir)
    if not series_map:
        raise RuntimeError("No USGS data returned for inspection.")

    resampled = {}
    for source_id, series in series_map.items():
        if transform == "detrend":
            base = series.resample(freq).mean()
            baseline = base.rolling(window=96, min_periods=48).median()
            resampled[source_id] = base - baseline
        else:
            transformed = pd.Series(
                apply_transform(series.to_numpy(dtype=float), transform),
                index=series.index,
            )
            resampled[source_id] = transformed.resample(freq).mean()

    aligned = _align_series_map(resampled)
    if not aligned:
        raise RuntimeError("Failed to align USGS sources for inspection.")

    return aligned


def _load_geomag_sources(run_dir: Path, project_root: Path, config: dict):
    inputs_path = run_dir / "inputs_geomag.json"
    if not inputs_path.exists():
        raise FileNotFoundError("inputs_geomag.json not found.")

    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    start = payload.get("start")
    end = payload.get("end")
    days = int(payload.get("days", 30))
    stations = payload.get("stations") or []
    elements = payload.get("elements") or []
    sampling_period = int(payload.get("sampling_period", 60))
    if not start or not stations or not elements:
        raise ValueError("inputs_geomag.json missing start/stations/elements.")

    freq = payload.get("freq") or config.get("freq") or "1min"

    start_dt = pd.to_datetime(start, utc=True, errors="coerce")
    end_dt = pd.to_datetime(end, utc=True, errors="coerce") if end else pd.NaT
    if pd.isna(start_dt) or pd.isna(end_dt):
        start_dt, end_dt = parse_start_end(start, days)

    cache_dir = project_root / "data" / "cache" / "geomag"
    series_map = {}
    for station in stations:
        series_map.update(
            fetch_geomag_station(
                station,
                elements,
                start_dt,
                end_dt,
                cache_dir,
                sampling_period=sampling_period,
            )
        )
    if not series_map:
        raise RuntimeError("No geomag data returned for inspection.")

    resampled = {}
    for source_id, series in series_map.items():
        resampled[source_id] = series.resample(freq).mean()

    aligned = _align_series_map(resampled)
    if not aligned:
        raise RuntimeError("Failed to align geomag sources for inspection.")

    return aligned


def _load_pageviews_sources(run_dir: Path, project_root: Path, config: dict):
    inputs_path = run_dir / "inputs_pageviews.json"
    if not inputs_path.exists():
        raise FileNotFoundError("inputs_pageviews.json not found.")

    payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    start = payload.get("start")
    end = payload.get("end")
    days = int(payload.get("days", 30))
    articles = payload.get("articles") or []
    project = payload.get("project", "en.wikipedia")
    access = payload.get("access", "all-access")
    agent = payload.get("agent", "all-agents")
    granularity = payload.get("granularity", "daily")
    if not start or not articles:
        raise ValueError("inputs_pageviews.json missing start/articles.")

    freq = payload.get("freq") or config.get("freq") or "1h"
    start_dt = pd.to_datetime(start, utc=True, errors="coerce")
    end_dt = pd.to_datetime(end, utc=True, errors="coerce") if end else pd.NaT
    if pd.isna(start_dt) or pd.isna(end_dt):
        start_dt, end_dt = parse_start_end(start, days)

    cache_dir = project_root / "data" / "cache" / "pageviews"
    series_map = {}
    for article in articles:
        series = fetch_pageviews_series(
            project,
            access,
            agent,
            article,
            granularity,
            start_dt,
            end_dt,
            cache_dir,
        )
        if series is None:
            continue
        series_map[pageviews_source_id(article)] = resample_pageviews_series(
            series, freq, granularity
        )

    if not series_map:
        raise RuntimeError("No pageviews data returned for inspection.")

    aligned = _align_series_map(series_map)
    if not aligned:
        raise RuntimeError("Failed to align pageviews sources for inspection.")

    return aligned


def inspect_event(run_dir: Path, event_id: str, out_dir: Path, project_root: Path | None = None, pad_minutes: float | None = None):
    run_dir = Path(run_dir).resolve()
    out_dir = Path(out_dir).resolve()
    if project_root is None:
        project_root = run_dir.parents[1]
    else:
        project_root = Path(project_root).resolve()

    manifest = _load_manifest(run_dir)
    config = manifest.get("config", {})
    events = _load_events(run_dir)

    match = events[events["event_id"] == event_id]
    if match.empty:
        raise ValueError(f"Event '{event_id}' not found in {run_dir / 'events.csv'}")

    row = match.iloc[0]
    event_start = _parse_time(row["event_start"])
    event_end = _parse_time(row["event_end"])
    if pd.isna(event_start) or pd.isna(event_end):
        raise ValueError("Event time range could not be parsed.")

    if pad_minutes is None:
        window_sizes = config.get("window_sizes", [])
        if window_sizes:
            pad_minutes = 2 * max(window_sizes)
        else:
            pad_minutes = 0

    pad = pd.Timedelta(minutes=float(pad_minutes))
    start = event_start - pad
    end = event_end + pad

    if (run_dir / "inputs_usgs.json").exists():
        series_map = _load_usgs_sources(run_dir, project_root, config)
    elif (run_dir / "inputs_geomag.json").exists():
        series_map = _load_geomag_sources(run_dir, project_root, config)
    elif (run_dir / "inputs_pageviews.json").exists():
        series_map = _load_pageviews_sources(run_dir, project_root, config)
    elif (run_dir / "inputs_omni_nmdb.json").exists():
        series_map = _load_omni_nmdb_sources(run_dir, project_root, config)
    elif (run_dir / "inputs_omni_btc.json").exists():
        series_map = _load_omni_btc_sources(run_dir, project_root, config)
    elif (run_dir / "inputs_swpc.json").exists():
        series_map = _load_swpc_sources(run_dir, project_root, config)
    elif (run_dir / "inputs_omni.json").exists():
        series_map = _load_omni_sources(run_dir, project_root, config)
    else:
        raise RuntimeError(
            "Inspect supports USGS, SWPC, OMNI, OMNI+NMDB, and OMNI+BTC runs only."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    combined = pd.DataFrame(index=pd.DatetimeIndex([]))

    for source_id, series in series_map.items():
        sliced = series.loc[start:end]
        if combined.empty:
            combined = pd.DataFrame(index=sliced.index)
        combined[source_id] = sliced

        missing_flag = np.isnan(sliced.to_numpy())
        df = pd.DataFrame(
            {
                "time": _format_time_index(sliced.index),
                "value": sliced.to_numpy(dtype=float),
                "missing_flag": missing_flag.astype(int),
            }
        )
        df.to_csv(out_dir / f"{source_id}.csv", index=False)

    combined_out = combined.copy()
    combined_out.insert(0, "time", _format_time_index(combined.index))
    combined_out.to_csv(out_dir / "combined.csv", index=False)

    return out_dir
