"""`tvsend update` and the quiet "new version available" line.

The only outside connection tvsend ever makes is here: a plain GET to GitHub for
the latest release (and, for `tvsend update`, the download of that release).
"""

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

from . import __version__, paths

REPO = "AndyHoang/tvsend"
# Where the latest release is described. The environment override exists for the tests.
LATEST_URL = os.environ.get("TVSEND_UPDATE_URL") or "https://api.github.com/repos/%s/releases/latest" % REPO
CHECKSUMS = "SHA256SUMS"
CHECK_EVERY = 24 * 3600  # seconds between automatic checks
MAX_BINARY = 300_000_000  # bytes; refuse anything absurd


class UpdateError(Exception):
    pass


def asset_name() -> str:
    """The release file for this computer, e.g. 'tvsend-linux-x86_64'."""
    system = {"linux": "linux", "darwin": "macos"}.get(sys.platform)
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if not system or not arch:
        raise UpdateError("there is no tvsend download for this system (%s, %s)" % (sys.platform, machine))
    return "tvsend-%s-%s" % (system, arch)


def _get(url: str, timeout: float, limit: int = 5_000_000) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "tvsend/%s" % __version__, "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("the download from %s is larger than expected" % url)
    return data


def latest_release(timeout: float = 10.0) -> dict:
    """{'version': '1.2.3', 'assets': {file name: download URL}} of the newest release."""
    try:
        data = json.loads(_get(LATEST_URL, timeout))
        version = str(data["tag_name"]).lstrip("v")
        assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError("could not ask GitHub for the newest version (%s)" % e) from e
    if not version:
        raise UpdateError("GitHub did not name a newest version")
    return {"version": version, "assets": assets}


def latest_version(timeout: float = 10.0) -> str:
    return latest_release(timeout)["version"]


def _key(version: str) -> tuple:
    """'1.10.0' -> (1, 10, 0), so that 1.10 counts as newer than 1.9."""
    parts = []
    for p in version.lstrip("v").split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return _key(candidate) > _key(current)


def is_binary() -> bool:
    """True when running as the standalone (PyInstaller) binary."""
    return bool(getattr(sys, "frozen", False))


def package_manager(exe: str) -> str:
    """The command that updates tvsend when a package manager installed it, else ''."""
    real = os.path.realpath(exe)
    if "/Cellar/" in real or "/homebrew/" in real.lower() or "/linuxbrew/" in real:
        return "brew upgrade tvsend"
    if shutil.which("pacman"):
        try:
            owned = (
                subprocess.run(
                    ["pacman", "-Qo", real], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
                ).returncode
                == 0
            )
        except (OSError, subprocess.SubprocessError):
            owned = False
        if owned:
            return "your AUR helper, for example: paru -S tvsend-bin"
    return ""


def _expected_hash(checksums: str, name: str) -> str:
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return ""


def cmd_update() -> int:
    """`tvsend update`: replace this binary with the newest release. Returns the exit code."""
    if not is_binary():
        print("tvsend is running from source here, so there is no binary to replace.")
        print("Update the source instead (git pull, then uv sync).")
        return 0
    exe = sys.executable
    manager = package_manager(exe)
    if manager:
        print("This tvsend was installed by a package manager. Update it with: %s" % manager)
        return 0
    try:
        name = asset_name()
        print("Asking GitHub for the newest version...")
        release = latest_release()
        if not is_newer(release["version"]):
            print("tvsend %s is the newest version." % __version__)
            return 0
        url, sums_url = release["assets"].get(name), release["assets"].get(CHECKSUMS)
        if not url or not sums_url:
            raise UpdateError("release %s has no download for this system (%s)" % (release["version"], name))
        folder = os.path.dirname(os.path.realpath(exe))
        if not os.access(folder, os.W_OK):
            raise UpdateError("no permission to write in %s" % folder)
        print("Downloading tvsend %s..." % release["version"])
        try:
            data = _get(url, 120, MAX_BINARY)
            wanted = _expected_hash(_get(sums_url, 30).decode("utf-8", "replace"), name)
        except UpdateError:
            raise
        except Exception as e:
            raise UpdateError("the download failed (%s)" % e) from e
        got = hashlib.sha256(data).hexdigest()
        if not wanted or got != wanted:
            raise UpdateError("the downloaded file does not match its checksum - nothing was changed")
        target = os.path.realpath(exe)
        tmp = "%s.new.%d" % (target, os.getpid())
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.chmod(tmp, stat.S_IMODE(os.stat(target).st_mode) | 0o111)
            os.replace(tmp, target)  # one step: the old binary is never left half-written
        except OSError as e:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise UpdateError("could not replace %s (%s)" % (target, e)) from e
    except UpdateError as e:
        print("Update failed: %s." % e, file=sys.stderr)
        return 1
    _remember(release["version"])
    print("Updated tvsend %s -> %s." % (__version__, release["version"]))
    return 0


# ---------------------------------------------------------------- the quiet daily check
def _stamp_file() -> str:
    return os.path.join(paths.cache_dir(), "update.json")


def _remember(version: str) -> None:
    paths.write_json(_stamp_file(), {"checked": time.time(), "latest": version})


def update_notice(cfg, timeout: float = 2.0) -> str:
    """'' or one line saying a newer version exists. Never raises.

    Asks GitHub at most once every 24 hours (the answer is remembered in the cache folder)
    and not at all when `check_updates = false` or when running from source. It may wait
    up to `timeout` seconds, so call it from a background thread."""
    try:
        if not getattr(cfg, "check_updates", True) or not is_binary():
            return ""
        seen = paths.read_json(_stamp_file())
        latest = seen.get("latest") if isinstance(seen.get("latest"), str) else ""
        checked = seen.get("checked") if isinstance(seen.get("checked"), (int, float)) else 0
        if time.time() - checked >= CHECK_EVERY:
            try:
                latest = latest_version(timeout)
            except UpdateError:
                pass
            _remember(latest or "")  # also after a failure: no retry storm while offline
        if latest and is_newer(latest):
            return "tvsend %s is available (you have %s) - run: tvsend update" % (latest, __version__)
    except Exception:
        pass
    return ""
