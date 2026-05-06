import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config
from .io import SeriesData, format_timestamp
from .pipeline import make_run_dir, run_pipeline

SWPC_URLS = {
    "mag": "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json",
    "kp": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "plasma": "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json",
    "xray": "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json",
}

TEMP_MIN_VALID_FRACTION = 0.2


@dataclass
class SwpcSourceSpec:
    source_id: str
    domain_id: str
    url: str
    cache_path: Path
    column: str
    notes: str | None = None


def _fetch_json(url: str, cache_dir: Path, refresh: bool = False) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_name = Path(urllib.parse.urlparse(url).path).name
    destination = cache_dir / file_name
    if destination.exists() and not refresh:
        return destination

    with urllib.request.urlopen(url) as response:
        payload = response.read()
    destination.write_bytes(payload)
    return destination


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_list_of_lists(data):
    if not data:
        return pd.DataFrame()
    header = data[0]
    rows = data[1:]
    return pd.DataFrame(rows, columns=header)


def _parse_time_tag(series: pd.Series):
    return pd.to_datetime(series, utc=True, errors="coerce")


def _coerce_float(series: pd.Series):
    return pd.to_numeric(series, errors="coerce").astype(float)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float, np.number)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y"}


def _apply_time_filter(df: pd.DataFrame, days: int):
    if days <= 0:
        return df
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return df[df["time_tag"] >= cutoff]


def _resample_series(df: pd.DataFrame, value_col: str, freq: str, days: int):
    if df.empty:
        return pd.Series(dtype=float)
    df = df.copy()
    df["time_tag"] = _parse_time_tag(df["time_tag"])
    df = df.dropna(subset=["time_tag"])
    if df.empty:
        return pd.Series(dtype=float)
    df = _apply_time_filter(df, days)
    if df.empty:
        return pd.Series(dtype=float)
    df[value_col] = _coerce_float(df[value_col])
    series = df.set_index("time_tag")[value_col].sort_index()
    return series.resample(freq).mean()


def _valid_fraction(series: pd.Series):
    if series.empty:
        return 0.0
    return float(np.isfinite(series.to_numpy()).mean())


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


def build_swpc_sources(cache_dir: Path, days: int, freq: str, include_kp: bool = False):
    mag_path = _fetch_json(SWPC_URLS["mag"], cache_dir)
    mag_df = _parse_list_of_lists(_read_json(mag_path))

    plasma_path = _fetch_json(SWPC_URLS["plasma"], cache_dir)
    plasma_df = _parse_list_of_lists(_read_json(plasma_path))

    xray_path = _fetch_json(SWPC_URLS["xray"], cache_dir)
    xray_df = pd.DataFrame(_read_json(xray_path))

    if mag_df.empty or xray_df.empty or plasma_df.empty:
        raise RuntimeError("SWPC data could not be loaded.")

    if "time_tag" not in mag_df.columns:
        raise RuntimeError("Missing column 'time_tag' in mag data.")

    mag_series = {}
    for column in ["bz_gsm", "bt"]:
        if column not in mag_df.columns:
            raise RuntimeError(f"Missing column '{column}' in mag data.")
        mag_series[column] = _resample_series(mag_df, column, freq, days)

    if "time_tag" not in plasma_df.columns:
        raise RuntimeError("Missing column 'time_tag' in plasma data.")

    plasma_series = {}
    for column in ["speed", "density", "temperature"]:
        if column not in plasma_df.columns:
            raise RuntimeError(f"Missing column '{column}' in plasma data.")
        plasma_series[column] = _resample_series(plasma_df, column, freq, days)

    if "time_tag" not in xray_df.columns:
        raise RuntimeError("Missing column 'time_tag' in X-ray data.")
    if "energy" not in xray_df.columns:
        raise RuntimeError("Missing column 'energy' in X-ray data.")
    if "flux" not in xray_df.columns:
        raise RuntimeError("Missing column 'flux' in X-ray data.")

    xray_df["energy"] = xray_df["energy"].astype(str)
    xray_df = xray_df[xray_df["energy"] == "0.1-0.8nm"].copy()
    if xray_df.empty:
        raise RuntimeError("No GOES X-ray rows for energy=0.1-0.8nm.")

    contamination_col = None
    for candidate in ["electron_contaminaton", "electron_contamination"]:
        if candidate in xray_df.columns:
            contamination_col = candidate
            break

    if contamination_col:
        bad_mask = xray_df[contamination_col].apply(_truthy)
        xray_df.loc[bad_mask, "flux"] = np.nan

    xray_series = _resample_series(xray_df, "flux", freq, days)

    series_map = {
        "swpc_mag_bz_gsm": mag_series["bz_gsm"],
        "swpc_mag_bt": mag_series["bt"],
        "swpc_xray_flux": xray_series,
        "swpc_plasma_speed": plasma_series["speed"],
        "swpc_plasma_density": plasma_series["density"],
    }

    source_specs = [
        SwpcSourceSpec(
            source_id="swpc_mag_bz_gsm",
            domain_id="swpc_mag",
            url=SWPC_URLS["mag"],
            cache_path=mag_path,
            column="bz_gsm",
        ),
        SwpcSourceSpec(
            source_id="swpc_mag_bt",
            domain_id="swpc_mag",
            url=SWPC_URLS["mag"],
            cache_path=mag_path,
            column="bt",
        ),
        SwpcSourceSpec(
            source_id="swpc_xray_flux",
            domain_id="swpc_xray",
            url=SWPC_URLS["xray"],
            cache_path=xray_path,
            column="flux",
            notes="energy=0.1-0.8nm, electron_contamination->NaN",
        ),
        SwpcSourceSpec(
            source_id="swpc_plasma_speed",
            domain_id="swpc_plasma",
            url=SWPC_URLS["plasma"],
            cache_path=plasma_path,
            column="speed",
        ),
        SwpcSourceSpec(
            source_id="swpc_plasma_density",
            domain_id="swpc_plasma",
            url=SWPC_URLS["plasma"],
            cache_path=plasma_path,
            column="density",
        ),
    ]

    if _valid_fraction(plasma_series["temperature"]) >= TEMP_MIN_VALID_FRACTION:
        series_map["swpc_plasma_temp"] = plasma_series["temperature"]
        source_specs.append(
            SwpcSourceSpec(
                source_id="swpc_plasma_temp",
                domain_id="swpc_plasma",
                url=SWPC_URLS["plasma"],
                cache_path=plasma_path,
                column="temperature",
                notes="included because valid fraction >= 0.2",
            )
        )

    if include_kp:
        kp_path = _fetch_json(SWPC_URLS["kp"], cache_dir)
        kp_df = _parse_list_of_lists(_read_json(kp_path))
        if not kp_df.empty and "Kp" in kp_df.columns:
            if "time_tag" not in kp_df.columns:
                raise RuntimeError("Missing column 'time_tag' in Kp data.")
            kp_series = _resample_series(kp_df, "Kp", freq, days).ffill()
            series_map["swpc_kp"] = kp_series
            source_specs.append(
                SwpcSourceSpec(
                    source_id="swpc_kp",
                    domain_id="swpc_kp",
                    url=SWPC_URLS["kp"],
                    cache_path=kp_path,
                    column="Kp",
                    notes="upsampled with ffill",
                )
            )

    aligned = _align_series(series_map)
    if not aligned:
        raise RuntimeError("Failed to align SWPC sources.")

    sources: list[SeriesData] = []
    for spec in source_specs:
        series = aligned.get(spec.source_id)
        if series is None:
            continue
        sources.append(
            SeriesData(
                source_id=spec.source_id,
                domain_id=spec.domain_id,
                timestamps=series.index.to_numpy(),
                values=series.to_numpy(dtype=float),
                quality=None,
                path=spec.cache_path,
            )
        )

    return sources, source_specs


def run_swpc_demo(
    project_root: Path,
    days: int,
    config_path: Path | None = None,
    include_kp: bool = False,
):
    if config_path is None:
        config_path = project_root / "configs" / "swpc_7day.yaml"
    config = load_config(config_path)

    freq = config.get("freq") or "1min"
    cache_dir = project_root / "data" / "cache" / "swpc"

    sources, specs = build_swpc_sources(cache_dir, days, freq, include_kp=include_kp)
    required_ids = {
        "swpc_mag_bz_gsm",
        "swpc_mag_bt",
        "swpc_xray_flux",
        "swpc_plasma_speed",
        "swpc_plasma_density",
    }
    available_ids = {source.source_id for source in sources}
    missing_ids = sorted(required_ids - available_ids)
    if missing_ids:
        raise RuntimeError(
            f"SWPC demo missing required sources after alignment: {', '.join(missing_ids)}"
        )

    run_dir = make_run_dir(project_root / "runs")
    results, events = run_pipeline(sources, config, run_dir, return_events=True)

    inputs_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freq": freq,
        "days": days,
        "include_kp": include_kp,
        "sources": [
            {
                "source_id": spec.source_id,
                "domain_id": spec.domain_id,
                "url": spec.url,
                "cache_path": str(spec.cache_path),
                "column": spec.column,
                "notes": spec.notes,
            }
            for spec in specs
        ],
    }
    inputs_path = run_dir / "inputs_swpc.json"
    inputs_path.write_text(json.dumps(inputs_payload, indent=2), encoding="utf-8")

    manifest_path = run_dir / "manifest.json"
    stats = {}
    if manifest_path.exists():
        try:
            stats = json.loads(manifest_path.read_text(encoding="utf-8")).get("stats", {})
        except Exception:
            stats = {}

    start_time = min(series.start_time() for series in sources)
    end_time = max(series.end_time() for series in sources)

    print("SWPC demo run:", run_dir)
    print(f"Time range: {start_time} -> {end_time}")
    if stats:
        print(
            f"Points: {stats.get('total_points')} | Windows: {stats.get('total_windows')} | Candidates: {stats.get('total_candidates')} | Events: {stats.get('total_events')}"
        )

    cross_domain_events = [evt for evt in events if evt.cross_domain_edges_count > 0]
    same_domain_events = [evt for evt in events if evt.cross_domain_edges_count == 0]
    cross_domain_events.sort(key=lambda evt: evt.event_score, reverse=True)
    same_domain_events.sort(key=lambda evt: evt.event_score, reverse=True)

    print("Top cross-domain EVENTS:")
    for item in cross_domain_events[:10]:
        print(
            f"  {item.event_id} {format_timestamp(item.event_start)} -> {format_timestamp(item.event_end)} score={item.event_score:.3f} orphan={item.orphan_score:.1f} nms={item.best_nms:.3f} p_value={item.best_p_value:.3f}"
        )

    print("Top same-domain EVENTS:")
    for item in same_domain_events[:10]:
        print(
            f"  {item.event_id} {format_timestamp(item.event_start)} -> {format_timestamp(item.event_end)} score={item.event_score:.3f} orphan={item.orphan_score:.1f} nms={item.best_nms:.3f} p_value={item.best_p_value:.3f}"
        )

    return run_dir
