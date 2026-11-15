"""Where tvsend keeps its files (XDG folders, the same on Linux and macOS)."""

import json
import os

APP = "tvsend"


def _base(env: str, default: str) -> str:
    return os.path.join(os.environ.get(env) or os.path.expanduser(default), APP)


def config_dir() -> str:
    return _base("XDG_CONFIG_HOME", "~/.config")


def state_dir() -> str:
    return _base("XDG_STATE_HOME", "~/.local/state")


def cache_dir() -> str:
    return _base("XDG_CACHE_HOME", "~/.cache")


def config_file() -> str:
    return os.path.join(config_dir(), "config.toml")


def write_atomic(path: str, text: str) -> None:
    """Write a file so that a crash never leaves it half-written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: str, data: dict) -> None:
    try:
        write_atomic(path, json.dumps(data))
    except OSError:
        pass
