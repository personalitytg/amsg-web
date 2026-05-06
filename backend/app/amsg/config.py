import json
from pathlib import Path

DEFAULT_CONFIG = {
    "seed": 42,
    "bins": 8,
    "freq": None,
    "window_sizes": [64, 128, 256],
    "step_size": 16,
    "top_p": 0.05,
    "shift_d": 3,
    "null_shifts_count": 50,
    "null_shift_min": 0,
    "merge_gap_minutes": 30,
    "min_pair_valid_fraction": 0.9,
    "min_pair_tokens": 128,
    "orphan_partner_k": 3,
    "compress_level": 9,
    "missing_token": 255,
    "min_valid_fraction": 0.5,
    "holdout_ratio": 0.0,
    "holdout_mode": "time",
}


def _read_structured_file(path: Path):
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "PyYAML is required to read YAML files. Install with 'pip install pyyaml'."
            ) from exc
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    raise ValueError(f"Unsupported config format: {path}")


def load_config(path: str | Path):
    path = Path(path)
    data = _read_structured_file(path)
    if data is None:
        data = {}
    config = dict(DEFAULT_CONFIG)
    config.update(data)

    bins = int(config["bins"])
    if bins <= 1:
        raise ValueError("bins must be > 1")
    if bins * bins > 254:
        raise ValueError("bins * bins must be <= 254 to fit in a byte")

    window_sizes = [int(v) for v in config["window_sizes"]]
    if not window_sizes:
        raise ValueError("window_sizes must not be empty")
    if any(v <= 1 for v in window_sizes):
        raise ValueError("window_sizes must be > 1")

    step_size = int(config["step_size"])
    if step_size <= 0:
        raise ValueError("step_size must be > 0")

    top_p = float(config["top_p"])
    if not (0 < top_p <= 1):
        raise ValueError("top_p must be in (0, 1]")

    shift_d = int(config["shift_d"])
    if shift_d < 0:
        raise ValueError("shift_d must be >= 0")

    null_shifts_count = int(config["null_shifts_count"])
    if null_shifts_count < 0:
        raise ValueError("null_shifts_count must be >= 0")

    null_shift_min = float(config.get("null_shift_min", 0))
    if null_shift_min < 0:
        raise ValueError("null_shift_min must be >= 0")

    merge_gap_minutes = float(config.get("merge_gap_minutes", 30))
    if merge_gap_minutes < 0:
        raise ValueError("merge_gap_minutes must be >= 0")

    min_pair_valid_fraction = float(config.get("min_pair_valid_fraction", 0))
    if not (0 <= min_pair_valid_fraction <= 1):
        raise ValueError("min_pair_valid_fraction must be in [0, 1]")

    min_pair_tokens = int(config.get("min_pair_tokens", 0))
    if min_pair_tokens < 0:
        raise ValueError("min_pair_tokens must be >= 0")

    orphan_partner_k = int(config.get("orphan_partner_k", 3))
    if orphan_partner_k < 0:
        raise ValueError("orphan_partner_k must be >= 0")

    compress_level = int(config["compress_level"])
    if compress_level < 1 or compress_level > 9:
        raise ValueError("compress_level must be in [1, 9]")

    missing_token = int(config["missing_token"])
    if missing_token < 0 or missing_token > 255:
        raise ValueError("missing_token must be in [0, 255]")

    min_valid_fraction = float(config["min_valid_fraction"])
    if not (0 <= min_valid_fraction <= 1):
        raise ValueError("min_valid_fraction must be in [0, 1]")

    holdout_ratio = float(config.get("holdout_ratio", 0.0))
    if not (0 <= holdout_ratio < 1):
        raise ValueError("holdout_ratio must be in [0, 1)")

    holdout_mode = config.get("holdout_mode", "time")
    if holdout_mode is not None and holdout_mode != "time":
        raise ValueError("holdout_mode must be 'time' or null")

    config["bins"] = bins
    config["window_sizes"] = window_sizes
    config["step_size"] = step_size
    config["top_p"] = top_p
    config["shift_d"] = shift_d
    config["null_shifts_count"] = null_shifts_count
    config["null_shift_min"] = null_shift_min
    config["merge_gap_minutes"] = merge_gap_minutes
    config["min_pair_valid_fraction"] = min_pair_valid_fraction
    config["min_pair_tokens"] = min_pair_tokens
    config["orphan_partner_k"] = orphan_partner_k
    config["compress_level"] = compress_level
    config["missing_token"] = missing_token
    config["min_valid_fraction"] = min_valid_fraction
    config["holdout_ratio"] = holdout_ratio
    config["holdout_mode"] = holdout_mode

    freq = config.get("freq")
    if freq is not None and not isinstance(freq, str):
        raise ValueError("freq must be a string or null")
    config["freq"] = freq

    return config


def load_inputs(path: str | Path):
    path = Path(path)
    data = _read_structured_file(path)
    if data is None:
        return []
    if isinstance(data, dict):
        sources = data.get("sources", [])
    elif isinstance(data, list):
        sources = data
    else:
        raise ValueError("inputs file must be a list or have a 'sources' key")

    parsed = []
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError("each source entry must be a mapping")
        source_id = item.get("source_id") or item.get("id")
        if not source_id:
            raise ValueError("source_id is required for each source")
        domain_id = item.get("domain_id") or "default"
        path_value = item.get("path")
        if not path_value:
            raise ValueError(f"path is required for source {source_id}")
        source_path = Path(path_value)
        if not source_path.is_absolute():
            source_path = (path.parent / source_path).resolve()
        fmt = item.get("format")
        if not fmt:
            fmt = source_path.suffix.lstrip(".").lower()
        parsed.append(
            {
                "source_id": str(source_id),
                "domain_id": str(domain_id),
                "path": source_path,
                "format": fmt,
                "timestamp_col": item.get("timestamp_col", "timestamp"),
                "value_col": item.get("value_col", "value"),
                "quality_col": item.get("quality_col"),
                "transform": item.get("transform"),
                "time_offset": item.get("time_offset"),
            }
        )
    return parsed
