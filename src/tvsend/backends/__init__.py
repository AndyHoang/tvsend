"""TV back-ends. Version 1 has DLNA; AirPlay and Chromecast would be added here."""

from ..config import TV
from .base import Backend
from .dlna import DlnaTV


def open_tv(tv: TV) -> Backend:
    if tv.backend == "dlna":
        return DlnaTV(tv)
    raise ValueError("unknown kind of TV: %s" % tv.backend)
