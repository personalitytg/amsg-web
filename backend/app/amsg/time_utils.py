import re

import numpy as np
import pandas as pd

_TIME_OFFSET_RE = re.compile(r"^\s*([+-]?\d+)\s*([a-zA-Z]+)\s*$")


def parse_time_offset(value):
    if value is None:
        return pd.Timedelta(0)
    if isinstance(value, pd.Timedelta):
        return value
    if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
        return pd.Timedelta(minutes=float(value))
    text = str(value).strip()
    if text == "":
        return pd.Timedelta(0)
    if text in {"0", "+0", "-0"}:
        return pd.Timedelta(0)
    match = _TIME_OFFSET_RE.match(text)
    if not match:
        raise ValueError(f"Invalid time_offset '{value}'. Use forms like +13d, -2h, +720min.")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit in {"d", "day", "days"}:
        return pd.Timedelta(days=amount)
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return pd.Timedelta(hours=amount)
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return pd.Timedelta(minutes=amount)
    if unit in {"s", "sec", "secs", "second", "seconds"}:
        return pd.Timedelta(seconds=amount)
    raise ValueError(f"Unsupported time_offset unit '{unit}'.")


def _infer_epoch_unit(values: np.ndarray):
    if values.size == 0:
        return "s"
    median = float(np.nanmedian(np.abs(values)))
    if median >= 1e12:
        return "ms"
    return "s"


def apply_time_offset(timestamps, offset):
    if offset is None:
        return timestamps
    delta = parse_time_offset(offset)
    if delta == pd.Timedelta(0):
        return timestamps

    if isinstance(timestamps, pd.DatetimeIndex):
        return timestamps + delta

    arr = np.asarray(timestamps)
    if np.issubdtype(arr.dtype, np.datetime64):
        shifted = pd.to_datetime(arr, utc=True, errors="coerce") + delta
        if shifted.isna().all():
            raise ValueError("time_offset applied to unparseable datetime timestamps.")
        return shifted.to_numpy()

    if np.issubdtype(arr.dtype, np.number):
        seconds = delta.total_seconds()
        if seconds == 0:
            return timestamps
        unit = _infer_epoch_unit(arr.astype(float))
        scale = 1000.0 if unit == "ms" else 1.0
        return arr + seconds * scale

    parsed = pd.to_datetime(arr, utc=True, errors="coerce")
    if parsed.isna().all():
        raise ValueError("time_offset applied to unparseable timestamps.")
    return (parsed + delta).to_numpy()
