"""tvsend - send video files from your terminal to a TV on your home network.

  tvsend                    open the list of your video folder (first run starts setup)
  tvsend <folder>           open the list for that folder only, this time
  tvsend <file>...          play the file(s) on the TV now
  tvsend <link>             play a direct video link (http/https) on the TV now
  tvsend stop               stop playback on the TV
  tvsend status             what the TV is doing
  tvsend tv                 list the TVs, find new ones, choose the default
  tvsend setup              run the setup again
  tvsend doctor             check the connection to the TV and print a report
  tvsend update             replace tvsend with the newest release
  tvsend --version | --help

A file or folder named like a command is given with a path: tvsend ./stop
"""

import os
import sys
import threading
import time

from . import __version__, config, discovery, library, paths
from .backends import open_tv
from .backends.base import HALTED, STATE_TEXT
from .config import Config
from .player import url_name
from .server import FileServer

OK_ENDINGS = ("finished", "stopped", "quit", "viewer", "other")


def err(text: str) -> None:
    print(text, file=sys.stderr)


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


# ---------------------------------------------------------------- getting ready
def ensure_setup(cfg: Config, need_folder: bool) -> bool:
    """Make sure a TV (and, for the list, a folder) is chosen; runs the setup on first use."""
    if cfg.tv() and (cfg.folder or not need_folder):
        return True
    if not interactive():
        err("tvsend is not set up yet. Run `tvsend` once in a terminal to choose your TV and folder.")
        return False
    from .ui.wizard import run_wizard

    if not run_wizard(cfg):
        err("Setup was not finished. Run `tvsend` again when you are ready.")
        return False
    return True


def _server_log():
    """A function that appends lines to the file server's log (a fresh file per run)."""
    path = os.path.join(paths.state_dir(), "server.log")
    lock = threading.Lock()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
    except OSError:
        return None

    def log(line: str) -> None:
        with lock:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass

    return log


def find_tv(cfg: Config):
    """The default TV's back-end. If the TV does not answer at its saved address, look for
    it on the network by its ID and remember the new address."""
    tv = cfg.tv()
    backend = open_tv(tv)
    if backend.state().state == "":
        print("%s is not answering at %s - looking for it..." % (tv.name, tv.address))
        for found in discovery.search(3.0):
            if found.id == tv.id:
                if (found.address, found.control_url) != (tv.address, tv.control_url):
                    print("Found it at %s." % found.address)
                    was_default = cfg.default_tv == tv.id
                    cfg.add_tv(found, make_default=was_default)
                    try:
                        config.save(cfg)
                    except OSError:
                        pass
                    backend = open_tv(found)
                break
    return backend


def start_server(cfg: Config, tv_address: str) -> FileServer | None:
    try:
        ip = discovery.local_ip_for(tv_address)
        server = FileServer(ip, cfg.port, log=_server_log())
        server.start()
    except (OSError, ValueError) as e:
        err("Cannot start the file server for the TV on port %d: %s" % (cfg.port, e))
        err(
            "Is another tvsend already running? Otherwise check the network, or change `port` in %s."
            % paths.config_file()
        )
        return None
    return server


# ---------------------------------------------------------------- commands
def cmd_list(cfg: Config, folder: str) -> int:
    from .ui.app import SWITCH_TV, TvApp

    while True:
        backend = find_tv(cfg)
        server = start_server(cfg, backend.tv.address)
        if not server:
            return 1
        app = TvApp(cfg, folder, backend, server)
        result = app.run()
        ctrl = app.ctrl
        was_playing = False
        if ctrl.is_alive():
            was_playing = bool(ctrl.view()["item"])
            if was_playing:  # the TV fetches the video from this program: without it the clip cannot go on
                ctrl.send("stop")
                deadline = time.time() + 5
                while ctrl.view()["item"] and time.time() < deadline:
                    time.sleep(0.05)
            ctrl.send("close")
            ctrl.join(5)
        server.stop()
        if result != SWITCH_TV:
            break
        # another TV was chosen in the list: open the list again for it, in the same folder
        folder = app.folder
        try:
            cfg = config.load()
        except config.ConfigError as e:
            err(str(e))
            return 2
    if was_playing:
        print("Stopped the TV, because playback needs tvsend to stay open.")
    _update_notice(cfg)
    return 0


def cmd_play(cfg: Config, targets: list[str]) -> int:
    from .plain import run_foreground
    from .player import Controller

    entries = []
    for t in targets:
        if library.is_url(t):
            entries.append(library.url_entry(t))
        else:
            if not library.is_video(t):
                print("note: %s does not look like a video file - trying anyway." % os.path.basename(t))
            entries.append(library.make_entry(os.path.abspath(t)))
    backend = find_tv(cfg)
    if backend.state().state == "":
        err("%s is not answering - is it switched on and on the same network?" % backend.name)
        return 1
    server = None
    if any(not e.get("remote") for e in entries):
        server = start_server(cfg, backend.tv.address)
        if not server:
            return 1
    print("Playing %d clip%s on %s." % (len(entries), "" if len(entries) == 1 else "s", backend.name))
    try:
        ended = run_foreground(Controller(backend, server), entries, loop=False)
    finally:
        if server:
            server.stop()
    return 0 if ended in OK_ENDINGS else 1


def cmd_stop(cfg: Config) -> int:
    backend = open_tv(cfg.tv())
    ok, reply = backend.stop()
    if ok:
        print("Told %s to stop." % backend.name)
        return 0
    if backend.state().state in HALTED:
        print("%s is not playing anything." % backend.name)
        return 0
    err("%s did not accept the stop command (%s)." % (backend.name, reply))
    return 1


def cmd_status(cfg: Config) -> int:
    tv = cfg.tv()
    st, pos, dur, uri = open_tv(tv).state()
    if st == "":
        print("%s (%s): not answering - is it switched on and on the same network?" % (tv.name, tv.address))
        return 1
    print("%s (%s): %s" % (tv.name, tv.address, STATE_TEXT.get(st, st.lower())))
    if uri and st not in HALTED:
        print("  clip: %s" % (url_name(uri) or uri))
        print("  position: %s / %s" % (library.clock(pos) if pos else "0:00", library.clock(dur)))
    return 0


def cmd_tv(cfg: Config) -> int:
    print("Looking for TVs on your network...")
    found = {t.id: t for t in discovery.search(3.0)}
    rows = [(found.get(t.id, t), t.id in found, True) for t in cfg.tvs]
    rows += [(t, True, False) for t in found.values() if not cfg.tv(t.id)]
    if not rows:
        print("No TV found. Is it switched on and on the same network as this computer?")
    for i, (t, seen, saved) in enumerate(rows, 1):
        notes = [
            n
            for n, on in (
                ("default", saved and t.id == cfg.default_tv),
                ("saved", saved),
                ("not found right now", not seen),
            )
            if on
        ]
        print(
            "  %d) %s  %s%s"
            % (
                i,
                library.fit(t.name, 32),
                library.fit(t.address, 16),
                "  (%s)" % ", ".join(notes) if notes else "",
            )
        )
    if not interactive():
        return 0
    try:
        answer = input("Number to use as the default TV, m to type an address, Enter to leave: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if not answer:
        return 0
    if answer.lower() == "m":
        try:
            tv = discovery.from_user_input(input("TV address: "))
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not tv:
            err("No TV that accepts video answered at that address.")
            return 1
    elif answer.isdigit() and 1 <= int(answer) <= len(rows):
        tv = rows[int(answer) - 1][0]
    else:
        err('Did not understand "%s".' % answer)
        return 1
    cfg.add_tv(tv, make_default=True)
    config.save(cfg)
    print("%s is now the default TV." % tv.name)
    return 0


def cmd_setup(cfg: Config) -> int:
    if not interactive():
        err("`tvsend setup` needs a terminal.")
        return 1
    from .ui.wizard import run_wizard

    return 0 if run_wizard(cfg) else 1


def _update_notice(cfg: Config) -> None:
    try:
        from .update import update_notice

        text = update_notice(cfg)
    except Exception:
        return
    if text:
        print(text)


# ---------------------------------------------------------------- entry
def cmd_open(cfg: Config, targets: list[str]) -> int:
    """No arguments, a folder, or files/links: decide by looking at what was given."""
    missing = [t for t in targets if not library.is_url(t) and not os.path.exists(t)]
    if missing:
        err("Not found: %s" % ", ".join(missing))
        if len(targets) == 1 and os.sep not in targets[0]:
            err("(`tvsend --help` lists the commands.)")
        return 2
    folders = [t for t in targets if not library.is_url(t) and os.path.isdir(t)]
    if folders and len(targets) > 1:
        err("Give one folder to open its list, or files and links to play - not a mix.")
        return 2
    want_list = not targets or bool(folders)
    if not ensure_setup(cfg, need_folder=not targets):
        return 1
    if want_list:
        return cmd_list(cfg, os.path.abspath(folders[0]) if folders else cfg.folder)
    return cmd_play(cfg, targets)


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if argv and argv[0] in ("-V", "--version", "version"):
        print("tvsend %s" % __version__)
        return 0
    if argv and argv[0].startswith("-"):
        err("Unknown option %s. Try `tvsend --help`." % argv[0])
        return 2
    try:
        cfg = config.load()
    except config.ConfigError as e:
        err(str(e))
        return 2
    if len(argv) == 1:
        cmd = argv[0]
        if cmd == "setup":
            return cmd_setup(cfg)
        if cmd == "update":
            from .update import cmd_update

            return cmd_update()
        if cmd == "doctor":
            from .doctor import run_doctor

            return run_doctor(cfg)
        if cmd in ("stop", "status", "tv"):
            if cmd != "tv" and not cfg.tv():
                err("No TV chosen yet. Run `tvsend` to set it up.")
                return 1
            return {"stop": cmd_stop, "status": cmd_status, "tv": cmd_tv}[cmd](cfg)
    return cmd_open(cfg, argv)


def run() -> None:
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
