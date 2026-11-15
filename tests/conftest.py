import os
import sys
import time

# Must be set before tvsend.player is imported: its waiting times are read at import.
os.environ["TVSEND_POLL"] = "0.05"
os.environ["TVSEND_END_SLACK"] = "4.0"
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402
from fake_tv import FakeTV  # noqa: E402

from tvsend.server import FileServer  # noqa: E402


@pytest.fixture(autouse=True)
def private_dirs(tmp_path, monkeypatch):
    """Every test gets its own config, state and cache folders."""
    for name in ("config", "state", "cache"):
        monkeypatch.setenv("XDG_%s_HOME" % name.upper(), str(tmp_path / name))


@pytest.fixture
def fake_tv():
    tv = FakeTV()
    yield tv
    tv.close()


def make_video(path, size=64, age=60):
    """A dummy video file, last changed `age` seconds ago."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(range(256)) * (size // 256) + bytes(range(size % 256)))
    old = time.time() - age
    os.utime(path, (old, old))
    return str(path)


@pytest.fixture
def videos(tmp_path):
    """A folder with three settled videos: a.mp4, b.mkv and sub/c.mp4."""
    folder = tmp_path / "videos"
    make_video(folder / "a.mp4", 300)
    make_video(folder / "b.mkv", 200)
    make_video(folder / "sub" / "c.mp4", 100)
    return str(folder)


@pytest.fixture(scope="session")
def server():
    """One file server for the whole run (stopping one takes half a second)."""
    srv = FileServer("127.0.0.1", 0)
    srv.start()
    yield srv
    srv.stop()


def wait_for(cond, timeout=5.0, step=0.01):
    """Wait until cond() is true; returns its value (falsy when the time ran out)."""
    end = time.time() + timeout
    while time.time() < end:
        value = cond()
        if value:
            return value
        time.sleep(step)
    return cond()
