"""Path utility functions."""

import os
from pathlib import Path


def abbreviate_path(path: str | Path, max_len: int = 60) -> str:
    """Abbreviate a path for display by replacing middle parts with '...'."""
    path_str = str(path)
    if len(path_str) <= max_len:
        return path_str
    parts = path_str.replace("\\", "/").split("/")
    if len(parts) <= 3:
        return "..." + path_str[-max_len + 3:]
    # Keep first 2 and last 2 parts, abbreviate the rest
    head = parts[:2]
    tail = parts[-2:]
    middle_count = len(parts) - 4
    abbreviated = head + [f"...({middle_count} dirs)"] + tail
    result = "/".join(abbreviated)
    if len(result) > max_len:
        return "..." + path_str[-max_len + 3:]
    return result
