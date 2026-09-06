from datetime import datetime, date
import pandas as pd
from functools import singledispatch
import numpy as np

@singledispatch
def _sanitize_for_json(obj):
    """Default sanitizer for objects that are not otherwise handled."""
    return str(obj)

@_sanitize_for_json.register(np.integer)
@_sanitize_for_json.register(int)
def _sanitize_int(obj):
    return int(obj)

@_sanitize_for_json.register(np.floating)
@_sanitize_for_json.register(float)
def _sanitize_float(obj):
    """Sanitizer for float types, converting nan/inf to None."""
    if np.isnan(obj) or np.isinf(obj):
        return None
    return float(obj)

@_sanitize_for_json.register(type(None))
@_sanitize_for_json.register(bool)
@_sanitize_for_json.register(str)
def _sanitize_passthrough(obj):
    return obj

@_sanitize_for_json.register(dict)
def _sanitize_dict(obj):
    # --- FIX: Ensure dictionary keys are JSON-serializable (strings). ---
    # The original implementation only sanitized values, not keys. This caused an
    # error when a dictionary had non-string keys, like pandas Timestamps.
    return {str(k): _sanitize_for_json(v) for k, v in obj.items()}

@_sanitize_for_json.register(list)
def _sanitize_list(obj):
    return [_sanitize_for_json(v) for v in obj]

@_sanitize_for_json.register(pd.Timestamp)
@_sanitize_for_json.register(datetime)
@_sanitize_for_json.register(date)
def _sanitize_datetime(obj):
    return obj.isoformat()

@_sanitize_for_json.register(pd.Series)
def _sanitize_series(obj):
    """Sanitizer for pandas Series objects."""
    # --- FIX: Preserve DatetimeIndex during JSON serialization ---
    # If the series has a DatetimeIndex, convert it to a dictionary
    # to preserve the date information. Otherwise, just convert values to a list.
    if isinstance(obj.index, pd.DatetimeIndex):
        return _sanitize_for_json(obj.to_dict())
    return _sanitize_for_json(obj.to_list())

@_sanitize_for_json.register(np.ndarray)
def _sanitize_ndarray(obj):
    """Sanitizer for numpy ndarray objects."""
    return _sanitize_for_json(obj.tolist())