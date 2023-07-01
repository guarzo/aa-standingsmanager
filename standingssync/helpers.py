"""Helpers for standingssync."""

import json
from pathlib import Path


def store_json(data, filename: str):
    """Store data as JSON in a file."""
    path = Path.cwd() / f"{filename}.json"
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
