import zlib

import numpy as np

SEPARATOR = b"||"


def compress_len(data: bytes, level: int):
    if not data:
        return 0
    return len(zlib.compress(data, level))


def self_surprise(tokens: bytes, level: int):
    if not tokens:
        return 0.0
    length = len(tokens)
    return compress_len(tokens, level) / max(1, length)


def mutual_surprise(
    tokens_a: bytes,
    tokens_b: bytes,
    shift_d: int,
    level: int,
    missing_token: int | None = None,
    min_pair_tokens: int = 0,
):
    if not tokens_a or not tokens_b:
        return 0.0, 0, 0.0, 0

    arr_a = np.frombuffer(tokens_a, dtype=np.uint8)
    arr_b = np.frombuffer(tokens_b, dtype=np.uint8)
    base_len = max(1, arr_a.size)

    best_nms = 0.0
    best_shift = 0
    best_pair_fraction = 0.0
    best_pair_tokens = 0

    for shift in range(-shift_d, shift_d + 1):
        if shift == 0:
            sub_a = arr_a
            sub_b = arr_b
        elif shift > 0:
            sub_a = arr_a[shift:]
            sub_b = arr_b[:-shift]
        else:
            sub_a = arr_a[:shift]
            sub_b = arr_b[-shift:]

        if sub_a.size == 0 or sub_b.size == 0:
            continue

        if missing_token is not None:
            mask = (sub_a != missing_token) & (sub_b != missing_token)
            valid_count = int(mask.sum())
            pair_fraction = valid_count / float(base_len)
            if valid_count == 0 or (min_pair_tokens and valid_count < min_pair_tokens):
                nms = 0.0
            else:
                bytes_a = sub_a[mask].tobytes()
                bytes_b = sub_b[mask].tobytes()
                k_a = compress_len(bytes_a, level)
                k_b = compress_len(bytes_b, level)
                k_ab = compress_len(bytes_a + SEPARATOR + bytes_b, level)
                ms = k_a + k_b - k_ab
                denom = max(k_a, k_b)
                nms = ms / denom if denom > 0 else 0.0
        else:
            valid_count = int(sub_a.size)
            pair_fraction = valid_count / float(base_len)
            if min_pair_tokens and valid_count < min_pair_tokens:
                nms = 0.0
            else:
                bytes_a = sub_a.tobytes()
                bytes_b = sub_b.tobytes()
                k_a = compress_len(bytes_a, level)
                k_b = compress_len(bytes_b, level)
                k_ab = compress_len(bytes_a + SEPARATOR + bytes_b, level)
                ms = k_a + k_b - k_ab
                denom = max(k_a, k_b)
                nms = ms / denom if denom > 0 else 0.0

        if nms > best_nms or (nms == best_nms and pair_fraction > best_pair_fraction):
            best_nms = nms
            best_shift = shift
            best_pair_fraction = pair_fraction
            best_pair_tokens = valid_count

    return best_nms, best_shift, best_pair_fraction, best_pair_tokens
