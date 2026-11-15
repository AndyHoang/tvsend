"""`tvsend doctor`: a plain-text report of everything playback depends on.

Made to be pasted into a bug report: it names the TV and the addresses on the home
network, but never lists file names from the video folder.
"""

import os
import platform
import sys

from . import __version__, discovery, firewall, library, paths
from .backends import open_tv
from .backends.base import ACTIVE, STATE_TEXT
from .config import Config
from .server import FileServer


def _line(label: str, value: str) -> None:
    print("%-18s %s" % (label + ":", value))


def run_doctor(cfg: Config) -> int:
    """Print the report. Returns 0 when everything needed for playing works, 1 otherwise."""
    problems = 0
    print("tvsend doctor")
    print("-------------")
    _line("tvsend", __version__ + (" (standalone binary)" if getattr(sys, "frozen", False) else ""))
    _line("System", "%s %s (%s)" % (platform.system(), platform.release(), platform.machine()))
    _line("Python", platform.python_version())
    config_file = paths.config_file()
    _line("Config file", config_file + ("" if os.path.exists(config_file) else "  (not created yet)"))

    # ---- the folder
    if not cfg.folder:
        _line("Video folder", "not chosen yet - run: tvsend setup")
        problems += 1
    elif not os.path.isdir(cfg.folder):
        _line("Video folder", "%s  (MISSING)" % cfg.folder)
        problems += 1
    else:
        entries, notes = library.scan(cfg.folder)
        _line(
            "Video folder",
            "%s  (%d video%s%s)"
            % (
                cfg.folder,
                len(entries),
                "" if len(entries) == 1 else "s",
                ", %d sub-folder%s unreadable" % (len(notes), "" if len(notes) == 1 else "s")
                if notes
                else "",
            ),
        )

    # ---- the TV
    tv = cfg.tv()
    if not tv:
        _line("TV", "none saved - run: tvsend setup")
        print("\nResult: setup is not finished.")
        return 1
    _line("TV", "%s%s" % (tv.name, "  (model %s)" % tv.model if tv.model and tv.model != tv.name else ""))
    _line("TV address", "%s  (%s, %d saved)" % (tv.address, tv.backend, len(cfg.tvs)))
    backend = open_tv(tv)
    state = backend.state()
    answering = state.state != ""
    if answering:
        _line("TV answers", "yes - %s" % STATE_TEXT.get(state.state, state.state.lower()))
    else:
        _line("TV answers", "NO - switched off, in deep standby, on another network, or its address changed")
        problems += 1

    # ---- this computer
    local_ip = ""
    try:
        local_ip = discovery.local_ip_for(tv.address)
        _line("This computer", "%s  (the address the TV fetches from)" % local_ip)
    except OSError as e:
        _line("This computer", "NO ROUTE to the TV's address (%s)" % e)
        problems += 1

    server = None
    if local_ip:
        server = FileServer(local_ip, cfg.port)
        try:
            server.start()
            _line("Port %d" % cfg.port, "free, the file server can start")
        except OSError as e:
            server = None
            _line(
                "Port %d" % cfg.port,
                "IN USE (%s) - normal while tvsend is playing, otherwise another "
                "program has it" % (e.strerror or e),
            )

    kind = firewall.detect()
    _line("Firewall", firewall.FIREWALL_NAME.get(kind, kind))

    # ---- can the TV fetch from here?
    try:
        if not answering:
            _line("Connection test", "skipped - the TV is not answering")
        elif not server:
            _line("Connection test", "skipped - the file server could not start")
        elif state.state in ACTIVE:
            _line("Connection test", "skipped - the TV is playing and the test would interrupt it")
        else:
            result = firewall.run_test(backend, server)
            if result.ok:
                _line("Connection test", "passed - the TV fetched a test file from this computer")
            else:
                problems += 1
                _line("Connection test", "FAILED - " + result.detail)
                rule = firewall.rule_command(kind, tv.address, local_ip, cfg.port)
                print()
                print(firewall.explain(kind))
                if rule:
                    print("\n    %s\n" % firewall.command_text(rule))
                    print("Run that command, then run tvsend doctor again.")
    finally:
        if server:
            server.stop()

    print()
    print(
        "Result: everything tvsend needs is working."
        if not problems
        else "Result: %d problem%s found (in CAPITALS above)." % (problems, "" if problems == 1 else "s")
    )
    return 0 if not problems else 1
