"""The saved settings: TVs, the video folder, the port, list preferences."""

import json
import os
from dataclasses import dataclass, field, fields

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from . import paths

AVTRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
DEFAULT_PORT = 8765


class ConfigError(Exception):
    pass


@dataclass
class TV:
    id: str  # the TV's own device ID (UDN); stays the same when its address changes
    name: str
    address: str
    control_url: str
    location: str = ""  # where its device description was read from
    service: str = AVTRANSPORT
    model: str = ""
    backend: str = "dlna"


@dataclass
class Config:
    folder: str = ""
    default_tv: str = ""
    port: int = DEFAULT_PORT
    sort: str = "name"
    loop: bool = True
    check_updates: bool = True
    tvs: list[TV] = field(default_factory=list)

    def tv(self, tv_id: str | None = None) -> TV | None:
        """The TV with this ID, or the default one (the first saved one if no default is set)."""
        wanted = tv_id or self.default_tv
        for t in self.tvs:
            if t.id == wanted:
                return t
        return self.tvs[0] if self.tvs and not tv_id else None

    def add_tv(self, tv: TV, make_default: bool = False) -> None:
        self.tvs = [t for t in self.tvs if t.id != tv.id] + [tv]
        if make_default or not self.default_tv:
            self.default_tv = tv.id


def _known(cls, data: dict) -> dict:
    names = {f.name: f.type for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def load() -> Config:
    """Read the config file. A missing file gives the defaults; a broken one raises ConfigError."""
    path = paths.config_file()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return Config()
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError("Cannot read %s: %s" % (path, e)) from e
    try:
        tvs = [TV(**_known(TV, t)) for t in data.get("tv", []) if isinstance(t, dict)]
        cfg = Config(**_known(Config, {k: v for k, v in data.items() if k != "tv"}))
    except TypeError as e:
        raise ConfigError("%s is missing a setting: %s" % (path, e)) from e
    cfg.tvs = tvs
    if not isinstance(cfg.port, int) or not 1024 <= cfg.port <= 65535:
        raise ConfigError("%s: port must be a number from 1024 to 65535" % path)
    return cfg


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)  # a JSON string is a valid TOML string


def dumps(cfg: Config) -> str:
    lines = ["# tvsend settings. Edit by hand if you like; `tvsend tv` manages the TVs.", ""]
    for f in fields(Config):
        if f.name != "tvs":
            lines.append("%s = %s" % (f.name, _value(getattr(cfg, f.name))))
    for tv in cfg.tvs:
        lines += ["", "[[tv]]"]
        lines += ["%s = %s" % (f.name, _value(getattr(tv, f.name))) for f in fields(TV)]
    return "\n".join(lines) + "\n"


def save(cfg: Config) -> None:
    paths.write_atomic(paths.config_file(), dumps(cfg))


def default_video_folder() -> str:
    """The usual videos folder of this system, or '' when there is none."""
    for cand in ("~/Videos", "~/Movies"):
        p = os.path.expanduser(cand)
        if os.path.isdir(p):
            return p
    return ""
