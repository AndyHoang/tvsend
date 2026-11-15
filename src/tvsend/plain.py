"""Playing without the full-screen list: `tvsend file.mp4` shows one status line."""

import os
import queue
import select
import shutil
import signal
import sys
import time

from .backends.base import PAUSED, STATE_TEXT
from .library import clock, fit
from .player import Controller

KEY_HELP = "n next · b back · r restart · p pause · s stop · q quit"


class Keys:
    """Single key presses without Enter when run in a terminal; otherwise no keys at all."""

    def __init__(self):
        self.fd, self.saved = None, None
        try:
            if sys.stdin.isatty() and sys.stdout.isatty():
                import termios
                import tty

                self.fd = sys.stdin.fileno()
                self.saved = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
        except Exception:
            self.fd, self.saved = None, None

    @property
    def active(self):
        return self.fd is not None

    def get(self, timeout):
        """Wait up to timeout seconds; return a lowercase key or ''."""
        if self.fd is None:
            time.sleep(max(0.0, timeout))
            return ""
        try:
            if not select.select([self.fd], [], [], max(0.0, timeout))[0]:
                return ""
            data = os.read(self.fd, 64)
        except (OSError, ValueError):
            data = b""
        if not data:  # terminal went away
            self.close()
            return ""
        if data[:1] == b"\x1b":  # arrow keys etc. - ignore
            return ""
        return data[:1].decode("ascii", "ignore").lower()

    def close(self):
        if self.fd is not None and self.saved is not None:
            try:
                import termios

                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
            except Exception:
                pass
        self.fd = None


def run_foreground(ctrl: Controller, picked: list[dict], loop: bool) -> str:
    """Play in the foreground with a one-line status.
    Returns how it ended: 'finished', 'stopped', 'quit', 'viewer', 'other', 'lost' or 'failed'."""
    live = sys.stdout.isatty()
    ctrl.loop = loop
    ctrl.start()
    ctrl.send("play", picked, 0)
    keys = Keys()
    shown, quitting, flags = "", False, {"int": False, "since": 0.0}
    old_int = signal.signal(signal.SIGINT, lambda *a: flags.update(int=True))  # Ctrl+C = quit, tidily

    def say(msg):
        if live:
            sys.stdout.write("\r\x1b[K")
        print(msg, flush=True)

    def drain():
        while True:
            try:
                say(ctrl.events.get_nowait()[1])
            except queue.Empty:
                return

    try:
        while True:
            key = keys.get(0.2)
            if flags["int"]:
                flags["int"], key = False, "q"
            if key in ("q", "s"):
                quitting = quitting or key == "q"
                flags["since"] = flags["since"] or time.time()
                ctrl.send("stop")
            elif key in ("n", "b", "r", "p", " "):
                ctrl.send({"n": "next", "b": "prev", "r": "restart"}.get(key, "pause"))
            drain()
            v = ctrl.view()
            if v["ended"] or (flags["since"] and time.time() - flags["since"] > 45) or not ctrl.is_alive():
                break
            it = v["item"]
            if not it:
                continue
            if live:
                text = "%s %d/%d  %s  %s / %s  %s  [%s]" % (
                    "⏸" if v["st"] == PAUSED else "▶",
                    max(v["k"], 0) + 1,
                    v["n"],
                    it["name"],
                    clock(v["pos"]) if v["pos"] else "0:00",
                    clock(v["dur"]),
                    STATE_TEXT.get(v["st"], str(v["st"]).lower()),
                    "loop" if v["loop"] else "once",
                )
                if keys.active:
                    text += "   " + KEY_HELP
                cols = shutil.get_terminal_size((100, 24)).columns
                sys.stdout.write("\r" + fit(text, cols - 1).rstrip() + "\x1b[K")
                sys.stdout.flush()
            else:
                head = "%d/%d %s" % (max(v["k"], 0) + 1, v["n"], it["name"])
                if head != shown:
                    shown = head
                    print("playing " + head, flush=True)
    finally:
        signal.signal(signal.SIGINT, old_int)
        keys.close()
        ctrl.send("close")
        ctrl.join(5)
        drain()
        if live:
            sys.stdout.write("\r\x1b[K")
            sys.stdout.flush()
    return "quit" if quitting else (ctrl.ended or "failed")
