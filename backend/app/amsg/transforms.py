import numpy as np


def log_return(values):
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr
    output = np.full(arr.shape, np.nan, dtype=float)
    if arr.size < 2:
        return output
    prev = arr[:-1]
    curr = arr[1:]
    valid = np.isfinite(prev) & np.isfinite(curr) & (prev > 0) & (curr > 0)
    output[1:] = np.where(valid, np.log(curr / prev), np.nan)
    return output


def apply_transform(values, transform):
    if transform is None:
        return np.asarray(values, dtype=float)
    name = str(transform).strip().lower()
    if name in {"", "identity", "none"}:
        return np.asarray(values, dtype=float)
    if name in {"log_return", "logreturn", "log-returns", "log_returns"}:
        return log_return(values)
    raise ValueError(f"Unsupported transform '{transform}'.")
