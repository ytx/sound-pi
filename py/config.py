"""Configuration persistence via JSON file."""

import json
import os
from pathlib import Path

from logger import get_logger

log = get_logger("config")

_CONFIG_DIR = Path.home() / ".config" / "sound-pi"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS = {
    "master_volume": 80,
    "muted": False,
    "last_screen": "vu_meter",
}

_data: dict = {}


def load() -> dict:
    global _data
    _data = dict(_DEFAULTS)
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE) as f:
                _data.update(json.load(f))
            log.info("loaded %s", _CONFIG_FILE)
        except Exception as e:
            log.warning("config load failed: %s", e)
    return _data


def save():
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w") as f:
            json.dump(_data, f, indent=2)
    except Exception as e:
        log.warning("config save failed: %s", e)


def get(key: str, default=None):
    return _data.get(key, default)


def set(key: str, value):
    _data[key] = value
    save()
