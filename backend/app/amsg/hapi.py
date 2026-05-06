import csv
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _server_dir_name(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    netloc = parsed.netloc or "server"
    return netloc.replace(":", "_")


def _cache_root(cache_dir: Path, base_url: str, dataset_id: str) -> Path:
    return cache_dir / _server_dir_name(base_url) / dataset_id


def _format_time_param(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_cache_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_time(value: str) -> datetime:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Could not parse time '{value}'")
    return parsed.to_pydatetime()


def fetch_info(base_url: str, dataset_id: str, cache_dir: Path, refresh: bool = False):
    base_url = _normalize_base_url(base_url)
    cache_root = _cache_root(cache_dir, base_url, dataset_id)
    cache_root.mkdir(parents=True, exist_ok=True)

    info_path = cache_root / "info.json"
    if info_path.exists() and not refresh:
        return json.loads(info_path.read_text(encoding="utf-8"))

    url = f"{base_url}/info?id={urllib.parse.quote(dataset_id)}"
    with urllib.request.urlopen(url) as response:
        payload = response.read()
    info_path.write_bytes(payload)
    return json.loads(payload.decode("utf-8"))


def get_fill_map(info: dict) -> dict:
    fills = {}
    for param in info.get("parameters", []):
        name = param.get("name")
        if not name:
            continue
        if "fill" in param:
            fills[name] = param.get("fill")
    return fills


def _fill_lookup(fill_map: dict, parameters: list[str]) -> dict:
    lookup = {}
    for name in parameters:
        fill = fill_map.get(name)
        if fill is None:
            lookup[name] = None
            continue
        fill_str = str(fill)
        fill_num = None
        try:
            fill_num = float(fill)
        except Exception:
            fill_num = None
        lookup[name] = (fill_str, fill_num)
    return lookup


def _is_fill(value: str, fill_spec) -> bool:
    if fill_spec is None:
        return False
    fill_str, fill_num = fill_spec
    if value == fill_str:
        return True
    if fill_num is None:
        return False
    try:
        return float(value) == fill_num
    except Exception:
        return False


def parse_hapi_csv(text: str, parameters: list[str], fill_map: dict) -> pd.DataFrame:
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        return pd.DataFrame(columns=parameters)

    reader = csv.reader(lines)
    rows = list(reader)
    if not rows:
        return pd.DataFrame(columns=parameters)

    header = rows[0]
    if header[: len(parameters)] == parameters:
        rows = rows[1:]

    time_name = parameters[0]
    fill_lookup = _fill_lookup(fill_map, parameters)

    times = []
    data_cols = {name: [] for name in parameters[1:]}

    for row in rows:
        if len(row) < len(parameters):
            continue
        time_str = row[0].strip()
        parsed_time = pd.to_datetime(time_str, utc=True, errors="coerce")
        if pd.isna(parsed_time):
            continue
        times.append(parsed_time)

        for idx, name in enumerate(parameters[1:], start=1):
            value = row[idx].strip()
            if value == "" or _is_fill(value, fill_lookup.get(name)):
                data_cols[name].append(np.nan)
                continue
            try:
                data_cols[name].append(float(value))
            except Exception:
                data_cols[name].append(np.nan)

    frame = {time_name: times}
    frame.update(data_cols)
    return pd.DataFrame(frame)


def _coerce_time_values(series: pd.Series) -> pd.Series:
    def _unwrap(value):
        if isinstance(value, (list, tuple, np.ndarray)):
            if len(value) == 0:
                return None
            return value[0]
        return value

    cleaned = series.map(_unwrap)
    return pd.to_datetime(cleaned, utc=True, errors="coerce")


def _chunk_ranges(start: datetime, end: datetime, chunk_days: int):
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        yield current, chunk_end
        current = chunk_end


def fetch_data(
    base_url: str,
    dataset_id: str,
    start: datetime,
    end: datetime,
    parameters: list[str],
    cache_dir: Path,
    chunk_days: int = 7,
):
    base_url = _normalize_base_url(base_url)
    cache_root = _cache_root(cache_dir, base_url, dataset_id)
    cache_root.mkdir(parents=True, exist_ok=True)

    info = fetch_info(base_url, dataset_id, cache_dir)
    fill_map = get_fill_map(info)

    param_hash = hashlib.md5(",".join(parameters).encode("utf-8")
    ).hexdigest()[:8]

    frames = []
    for chunk_start, chunk_end in _chunk_ranges(start, end, chunk_days):
        cache_name = f"{_format_cache_stamp(chunk_start)}__{_format_cache_stamp(chunk_end)}__{param_hash}.csv"
        cache_path = cache_root / cache_name

        if cache_path.exists():
            text = cache_path.read_text(encoding="utf-8")
        else:
            params = {
                "id": dataset_id,
                "time.min": _format_time_param(chunk_start),
                "time.max": _format_time_param(chunk_end),
                "parameters": ",".join(parameters),
                "format": "csv",
            }
            url = f"{base_url}/data?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(url) as response:
                payload = response.read()
            cache_path.write_bytes(payload)
            text = payload.decode("utf-8")

        df = parse_hapi_csv(text, parameters, fill_map)
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=parameters)

    df = pd.concat(frames, ignore_index=True)
    time_col = parameters[0]
    if time_col not in df.columns:
        return df

    df[time_col] = _coerce_time_values(df[time_col])
    df = df.dropna(subset=[time_col])
    df = df.drop_duplicates(subset=[time_col])
    df = df.sort_values(time_col)

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("UTC")
    else:
        start_ts = start_ts.tz_convert("UTC")
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    else:
        end_ts = end_ts.tz_convert("UTC")
    df = df[(df[time_col] >= start_ts) & (df[time_col] <= end_ts)]
    return df.reset_index(drop=True)


def parse_start_end(start: str, days: int) -> tuple[datetime, datetime]:
    start_dt = _parse_time(start)
    end_dt = start_dt + timedelta(days=int(days))
    return start_dt, end_dt
