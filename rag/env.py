"""Load settings from a `.env` file in the project folder (if it exists).

Lines look like  NAME=value  (no quotes needed). Lines starting with # are ignored.
Variables already set in the environment are never overwritten.
The .env file holds secrets: never share it or commit it.
"""
import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def parse(text):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key.strip():
            values[key.strip()] = value
    return values


def load(path=ENV_PATH):
    """Put values from the .env file into os.environ. Returns the names that were set."""
    if not path.exists():
        return []
    set_names = []
    for key, value in parse(path.read_text(encoding="utf-8")).items():
        if value and key not in os.environ:
            os.environ[key] = value
            set_names.append(key)
    return set_names
