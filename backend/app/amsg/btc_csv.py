from pathlib import Path

import numpy as np
import pandas as pd

from .time_utils import parse_time_offset
from .transforms import apply_transform


def _resolve_column(df: pd.DataFrame, name: str | int | None, fallbacks: list[str]):
    if name is not None:
        if isinstance(name, int):
            if 0 <= name < len(df.columns):
                return df.columns[name]
        else:
            text = str(name)
            if text.isdigit():
                idx = int(text)
                if 0 <= idx < len(df.columns):
                    return df.columns[idx]
            if text in df.columns:
                return text
            lowered = text.lower()
            for col in df.columns:
                if str(col).lower() == lowered:
                    return col
    for fallback in fallbacks:
        for col in df.columns:
            if str(col).lower() == fallback.lower():
                return col
    return None


def _parse_btc_time(series: pd.Series):
    raw = pd.to_numeric(series, errors="coerce")
    numeric_ratio = float(raw.notna().mean())
    if numeric_ratio >= 0.8:
        median = raw.dropna().abs().median()
        if pd.isna(median):
            return pd.to_datetime(series, utc=True, errors="coerce")
        if median >= 1e14:
            unit = "us"
        elif median >= 1e12:
            unit = "ms"
        else:
            unit = "s"
        return pd.to_datetime(raw, utc=True, errors="coerce", unit=unit)
    return pd.to_datetime(series, utc=True, errors="coerce")


def _looks_numeric(value) -> bool:
    try:
        float(str(value))
        return True
    except Exception:
        return False


def load_btc_csv(
    path: str | Path,
    time_col: str = "time",
    price_col: str | None = "close",
    volume_col: str | None = None,
    transform: str | None = "log_return",
    time_offset: str | None = None,
):
    path = Path(path)
    df = pd.read_csv(path)

    time_name = _resolve_column(
        df, time_col, ["time", "timestamp", "date", "open_time"]
    )

    price_name = _resolve_column(df, price_col, ["close", "price", "last"])
    if not time_name or not price_name:
        if df.columns.size and all(_looks_numeric(col) for col in df.columns):
            df = pd.read_csv(path, header=None)
            default_cols = [
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ]
            if df.shape[1] <= len(default_cols):
                df.columns = default_cols[: df.shape[1]]
            else:
                df.columns = default_cols + [f"col_{i}" for i in range(len(default_cols), df.shape[1])]
            time_name = _resolve_column(
                df, time_col, ["time", "timestamp", "date", "open_time"]
            )
            price_name = _resolve_column(df, price_col, ["close", "price", "last"])

    if not time_name:
        raise ValueError(
            f"BTC CSV missing time column '{time_col}'. Available columns: {list(df.columns)}"
        )
    if not price_name:
        raise ValueError(
            f"BTC CSV missing price column '{price_col}'. Available columns: {list(df.columns)}"
        )

    times = _parse_btc_time(df[time_name])
    values = pd.to_numeric(df[price_name], errors="coerce").to_numpy(dtype=float)

    valid = ~pd.isna(times)
    times = times[valid]
    values = values[valid]

    if time_offset:
        delta = parse_time_offset(time_offset)
        if delta != pd.Timedelta(0):
            times = times + delta

    frame = pd.DataFrame({"time": times, "value": values})
    frame = frame.sort_values("time")
    frame = frame.drop_duplicates(subset=["time"], keep="last")
    frame = frame.set_index("time")

    transformed = apply_transform(frame["value"].to_numpy(dtype=float), transform)
    series = pd.Series(transformed, index=frame.index, name="btc_usd")
    return series
