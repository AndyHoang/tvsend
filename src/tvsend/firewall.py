"""Can the TV reach this computer? The connection test, and help with the firewall when it cannot.

tvsend never changes the firewall by itself: it shows the exact command, and runs it
only after the user said yes (`apply`).
"""

import ipaddress
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import NamedTuple

from . import paths
from .backends.base import Backend
from .server import FileServer

MACOS_FIREWALL = "/usr/libexec/ApplicationFirewall/socketfilterfw"

# The start of an MP4 file (an 'ftyp' box, then an empty 'free' box): enough for a TV
# to recognise the kind of file and begin fetching it. It is not a playable video.
TEST_FILE = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41\x00\x00\x04\x00free" + b"\x00" * 1016

# Why a test ended the way it did.
OK = "ok"
TV_SILENT = "tv_silent"  # the TV did not answer at all (off, other network)
BLOCKED = "blocked"  # the TV answered but never fetched the file (firewall, wrong address)


class TestResult(NamedTuple):
    ok: bool
    reason: str  # OK, TV_SILENT or BLOCKED
    detail: str  # one plain sentence for the user


class _FetchWatch:
    """Notices when the test file is fetched.

    Uses `server.fetched(url)` when the server offers it; otherwise listens to the
    server's per-request log lines for the duration of the test."""

    def __init__(self, server: FileServer, url: str):
        self.server, self.url, self.seen = server, url, False
        self.name = os.path.basename(url)
        self._native = callable(getattr(server, "fetched", None))
        self._old_log = None

    def __enter__(self):
        if not self._native:
            self._old_log = self.server.log

            def log(line: str):
                # "<time> <client> <GET|HEAD> <name> [<range>] -> <code>..."
                parts = line.split(" -> ", 1)
                if self.name in parts[0] and len(parts) == 2 and parts[1][:1] == "2":
                    self.seen = True
                if self._old_log:
                    self._old_log(line)

            self.server.log = log
        return self

    def __exit__(self, *exc):
        if not self._native:
            self.server.log = self._old_log

    def fetched(self) -> bool:
        if self._native:
            return bool(self.server.fetched(self.url))
        return self.seen


def _wait(check, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return check()


def run_test(backend: Backend, server: FileServer, timeout: float = 8.0) -> TestResult:
    """Ask the TV to fetch a tiny test file from `server` (which must be started).

    Only the fetch matters: a TV may well refuse to play the file afterwards."""
    if backend.state().state == "":
        return TestResult(
            False, TV_SILENT, "The TV is not answering - is it switched on and on the same network?"
        )
    try:
        os.makedirs(paths.cache_dir(), exist_ok=True)
        folder = tempfile.mkdtemp(prefix="test-", dir=paths.cache_dir())
    except OSError as e:
        return TestResult(False, BLOCKED, "Could not write the test file (%s)." % e)
    path = os.path.join(folder, "tvsend-test.mp4")
    try:
        with open(path, "wb") as f:
            f.write(TEST_FILE)
        url = server.add(path)
        with _FetchWatch(server, url) as watch:
            accepted, reply = backend.load(url, "tvsend test", "video/mp4")
            if not watch.fetched() and not _wait(watch.fetched, timeout / 2):
                backend.play()  # some TVs fetch only when told to play
                _wait(watch.fetched, timeout / 2)
            got = watch.fetched()
        backend.stop()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if got:
        return TestResult(True, OK, "The TV can fetch files from this computer.")
    where = "%s:%d" % (server.host, server.port)
    if not accepted:
        return TestResult(
            False, BLOCKED, "The TV refused the test and did not fetch from %s (%s)." % (where, reply)
        )
    return TestResult(
        False, BLOCKED, "The TV accepted the test but could not reach this computer at %s." % where
    )


def connection_test(backend: Backend, server: FileServer, timeout: float = 8.0) -> tuple[bool, str]:
    """(ok, one plain sentence). See run_test() for the reason as well."""
    r = run_test(backend, server, timeout)
    return r.ok, r.detail


# ---------------------------------------------------------------- which firewall
def _run(cmd: list[str], timeout: float = 5.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)


def _ufw_enabled() -> bool | None:
    """True/False from ufw's own settings file (readable without root), None when unknown."""
    try:
        with open("/etc/ufw/ufw.conf", encoding="utf-8", errors="replace") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key.strip().upper() == "ENABLED":
                    return value.strip().strip("\"'").lower() == "yes"
    except OSError:
        pass
    return None


def detect() -> str:
    """The firewall in use: 'ufw', 'firewalld', 'macos', 'none' or 'unknown'. Never needs root."""
    if sys.platform == "darwin":
        if not os.path.exists(MACOS_FIREWALL):
            return "unknown"
        code, out = _run([MACOS_FIREWALL, "--getglobalstate"])
        if code != 0:
            return "unknown"
        return "none" if "disabled" in out.lower() or "state = 0" in out.lower() else "macos"
    if shutil.which("firewall-cmd"):
        code, out = _run(["firewall-cmd", "--state"])
        if code == 0 and "running" in out and "not running" not in out:
            return "firewalld"
    if shutil.which("ufw") or os.path.exists("/etc/ufw/ufw.conf"):
        enabled = _ufw_enabled()
        if enabled:
            return "ufw"
        if enabled is None:
            return "unknown"
    # no managed firewall is active; hand-made rules cannot be read without root
    if shutil.which("systemctl"):
        for unit in ("nftables", "iptables"):
            if _run(["systemctl", "is-active", unit])[1] == "active":
                return "unknown"
    return "none"


FIREWALL_NAME = {
    "ufw": "ufw",
    "firewalld": "firewalld",
    "macos": "the macOS application firewall",
    "none": "no firewall found",
    "unknown": "a firewall tvsend does not know",
}


def _ip(text: str) -> str | None:
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def rule_command(kind: str, tv_ip: str, local_ip: str, port: int) -> list[str] | None:
    """The command that lets this one TV reach this one port. None when there is nothing to offer."""
    tv, local = _ip(tv_ip), _ip(local_ip)
    if not tv or not local or not isinstance(port, int) or not 1 <= port <= 65535:
        return None
    if kind == "ufw":
        return ["sudo", "ufw", "allow", "from", tv, "to", local, "port", str(port), "proto", "tcp"]
    if kind == "firewalld":
        family = "ipv6" if ":" in tv else "ipv4"
        rule = 'rule family="%s" source address="%s" port port="%d" protocol="tcp" accept' % (
            family,
            tv,
            port,
        )
        return [
            "sudo",
            "sh",
            "-c",
            "firewall-cmd --permanent --add-rich-rule=%s && firewall-cmd --reload" % shlex.quote(rule),
        ]
    if kind == "macos":
        app = shlex.quote(os.path.realpath(sys.executable))
        return [
            "sudo",
            "sh",
            "-c",
            "%s --add %s && %s --unblockapp %s" % (MACOS_FIREWALL, app, MACOS_FIREWALL, app),
        ]
    return None


def command_text(cmd: list[str]) -> str:
    """The command as one line to show or copy."""
    return shlex.join(cmd)


def explain(kind: str) -> str:
    """One or two plain sentences about what the command does (or why there is none)."""
    if kind == "ufw":
        return "This lets only your TV reach only tvsend's port on this computer."
    if kind == "firewalld":
        return "This lets only your TV reach only tvsend's port, and keeps the rule after a restart."
    if kind == "macos":
        return (
            "The macOS firewall decides per program, not per port. macOS may have shown a window "
            'asking whether "%s" may accept incoming connections: choose Allow there and test '
            "again. If no window appeared, or Deny was chosen, the command below allows incoming "
            "connections for that one program." % os.path.basename(sys.executable)
        )
    if kind == "none":
        return (
            "No firewall seems to be active on this computer. Check that the TV and this computer "
            "are on the same network (not a guest network), and that the router does not "
            "separate Wi-Fi devices from each other."
        )
    return (
        "tvsend could not tell which firewall is in use. Allow incoming TCP connections from "
        "the TV's address to the port shown above in your firewall's settings."
    )


def apply(cmd: list[str]) -> tuple[bool, str]:
    """Run the firewall command. Call this only after the user agreed; sudo asks for the
    password on the terminal itself."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return p.returncode == 0, (p.stdout or "").strip()
