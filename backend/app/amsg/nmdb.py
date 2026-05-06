import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

NMDB_BASE_URL = "https://www.nmdb.eu/nest/draw_graph.php"
DEFAULT_DTYPE = "corr_for_efficiency"
DEFAULT_TABCHOICE = "ori"
DEFAULT_YUNITS = 0


def _parse_time(value):
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Could not parse time '{value}'")
    return parsed.to_pydatetime()


def _format_cache_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _cache_path(cache_dir: Path, stations: list[str], start: datetime, end: datetime, dtype: str) -> Path:
    stations_joined = "-".join(stations)
    name = f"{stations_joined}__{_format_cache_stamp(start)}__{_format_cache_stamp(end)}__{dtype}.txt"
    return cache_dir / name


def _build_params(
    stations: list[str],
    start: datetime,
    end: datetime,
    dtype: str,
    tabchoice: str,
    yunits: int,
):
    params = {
        "wget": 1,
        "output": "ascii",
        "tabchoice": tabchoice,
        "dtype": dtype,
        "date_choice": "bydate",
        "start_year": start.year,
        "start_month": f"{start.month:02d}",
        "start_day": f"{start.day:02d}",
        "start_hour": f"{start.hour:02d}",
        "start_min": f"{start.minute:02d}",
        "end_year": end.year,
        "end_month": f"{end.month:02d}",
        "end_day": f"{end.day:02d}",
        "end_hour": f"{end.hour:02d}",
        "end_min": f"{end.minute:02d}",
        "yunits": yunits,
    }
    query = urllib.parse.urlencode(params)
    station_params = "&".join(
        urllib.parse.urlencode({"stations[]": station}) for station in stations
    )
    return f"{query}&{station_params}"


def parse_nmdb_text(text: str) -> pd.DataFrame:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_line = None
    data_lines = []

    for line in lines:
        if line.startswith("#"):
            continue
        if ";" in line:
            data_lines.append(line)
        else:
            header_line = line

    if not header_line:
        raise ValueError("NMDB header line with station names not found.")

    stations = header_line.split()
    if not stations:
        raise ValueError("NMDB header did not include station names.")

    times = []
    values = {station: [] for station in stations}

    for line in data_lines:
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 1 + len(stations):
            continue
        timestamp = pd.to_datetime(parts[0], utc=True, errors="coerce")
        if pd.isna(timestamp):
            continue
        times.append(timestamp)
        for idx, station in enumerate(stations, start=1):
            value = parts[idx]
            try:
                values[station].append(float(value))
            except Exception:
                values[station].append(np.nan)

    frame = {"Time": pd.Series(times)}
    for station in stations:
        frame[station] = values[station]
    return pd.DataFrame(frame)


def fetch_nmdb(
    stations: list[str],
    start: str | datetime,
    end: str | datetime,
    dtype: str = DEFAULT_DTYPE,
    tabchoice: str = DEFAULT_TABCHOICE,
    yunits: int = DEFAULT_YUNITS,
    cache_dir: Path | None = None,
    refresh: bool = False,
):
    if isinstance(start, str):
        start_dt = _parse_time(start)
    else:
        start_dt = start
    if isinstance(end, str):
        end_dt = _parse_time(end)
    else:
        end_dt = end

    cache_dir = cache_dir or Path("data") / "cache" / "nmdb"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(cache_dir, stations, start_dt, end_dt, dtype)

    if cache_path.exists() and not refresh:
        text = cache_path.read_text(encoding="utf-8")
    else:
        query = _build_params(stations, start_dt, end_dt, dtype, tabchoice, yunits)
        url = f"{NMDB_BASE_URL}?{query}"
        with urllib.request.urlopen(url) as response:
            payload = response.read()
        cache_path.write_bytes(payload)
        text = payload.decode("utf-8", errors="replace")

    return parse_nmdb_text(text)


def parse_start_end(start: str, days: int):
    start_dt = _parse_time(start)
    end_dt = start_dt + timedelta(days=int(days))
    return start_dt, end_dt


def run_nmdb_demo(
    project_root: Path,
    start: str,
    days: int,
    stations: list[str],
    dtype: str = DEFAULT_DTYPE,
    tabchoice: str = DEFAULT_TABCHOICE,
    yunits: int = DEFAULT_YUNITS,
    save_csv: bool = True,
):
    start_dt, end_dt = parse_start_end(start, days)

    cache_dir = project_root / "data" / "cache" / "nmdb"
    df = fetch_nmdb(
        stations=stations,
        start=start_dt,
        end=end_dt,
        dtype=dtype,
        tabchoice=tabchoice,
        yunits=yunits,
        cache_dir=cache_dir,
    )

    if df.empty or "Time" not in df.columns:
        raise RuntimeError("NMDB response did not contain data.")

    time_series = pd.to_datetime(df["Time"], utc=True, errors="coerce")
    df = df.drop(columns=["Time"])

    print("NMDB demo")
    print(f"Time range: {start_dt.isoformat()} -> {end_dt.isoformat()}")

    for station in df.columns:
        values = pd.to_numeric(df[station], errors="coerce")
        total = len(values)
        missing = int(values.isna().sum())
        missing_fraction = missing / total if total else 0.0
        print(
            f"  {station}: points={total - missing} missing_fraction={missing_fraction:.3f}"
        )

    if save_csv:
        derived_dir = project_root / "data" / "derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        stations_joined = "-".join(stations)
        out_name = f"nmdb_{_format_cache_stamp(start_dt)}__{_format_cache_stamp(end_dt)}__{stations_joined}.csv"
        output_path = derived_dir / out_name
        df_out = pd.DataFrame({"Time": time_series})
        for station in df.columns:
            df_out[station] = pd.to_numeric(df[station], errors="coerce")
        df_out.to_csv(output_path, index=False)
        print("Saved:", output_path)

    return df
