import json
from pathlib import Path


def store_json(data, filename: str):
    path = Path.cwd() / f"{filename}.json"
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=4)
