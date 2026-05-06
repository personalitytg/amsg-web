import numpy as np


def quantile_edges(values: np.ndarray, bins: int):
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        return np.array([], dtype=float)
    if bins <= 1:
        return np.array([], dtype=float)
    qs = np.linspace(0.0, 1.0, bins + 1)[1:-1]
    return np.quantile(valid, qs)


def tokenize_window(values: np.ndarray, global_edges: np.ndarray, bins: int, missing_token: int):
    length = values.size
    tokens = np.zeros(length, dtype=np.uint8)
    valid_mask = np.isfinite(values)

    if global_edges.size:
        global_bins = np.zeros(length, dtype=np.int32)
        global_bins[valid_mask] = np.digitize(values[valid_mask], global_edges)
    else:
        global_bins = np.zeros(length, dtype=np.int32)

    local_edges = quantile_edges(values, bins)
    if local_edges.size:
        local_bins = np.zeros(length, dtype=np.int32)
        local_bins[valid_mask] = np.digitize(values[valid_mask], local_edges)
    else:
        local_bins = np.zeros(length, dtype=np.int32)

    combined = global_bins * bins + local_bins
    combined = np.clip(combined, 0, 255)
    tokens[:] = combined.astype(np.uint8)
    tokens[~valid_mask] = missing_token
    return tokens.tobytes()
