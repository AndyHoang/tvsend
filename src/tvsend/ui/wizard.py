"""The first-run setup: choose the TV, test the connection, choose the folder, learn the keys."""

import os
import sys
import threading

from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import ContentSwitcher, DirectoryTree, Input, OptionList, Static
from textual.widgets.option_list import Option

from .. import config, discovery, firewall
from ..backends import open_tv
from ..backends.base import ACTIVE
from ..config import TV, Config
from ..server import FileServer

STEPS = ["Choose your TV", "Connection test", "Choose your video folder", "Keys"]

NOTHING_FOUND = """No TV found. The usual reasons:

  • the TV is switched off or in deep standby
  • the TV and this computer are on different networks (for example a guest Wi-Fi, or a VPN
    on this computer)
  • the TV's "DLNA", "media sharing" or "allow devices to connect" setting is off
  • a firewall on this computer hides the TVs' answers to the search

If the TV is on, typing its address usually works even behind a firewall: press m. The
address is shown in the TV's network settings (it looks like 192.168.1.20).
Press r to search again."""

# macOS 15 and later ask once whether the terminal app may reach devices on the local
# network; if that was denied, nothing on the home network answers.
MAC_LOCAL_NETWORK = """

On a Mac: the terminal app needs permission to reach devices on your network. Check
System Settings › Privacy & Security › Local Network, switch your terminal app on, then
press r."""

SEARCHING = """Looking on your network…

This takes a few seconds: first one question to the whole network, then, if nothing
answers, each address near this computer is asked directly."""

KEYS = """You are ready. These keys are all you need:

  Enter     play the highlighted clip; the next ones follow by themselves
  n / b     next / previous clip
  p         pause / resume
  s         stop
  /         filter the list by typing part of a name
  ?         all keys

Run  tvsend setup  any time to change the TV or the folder."""

PORT_BUSY = "port_busy"
TV_PLAYING = "tv_playing"


def test_connection(tv: TV, port: int, even_if_playing: bool = False):
    """Start a file server just for the test and ask the TV to fetch from it.
    Returns (reason, detail, local_ip); reason is a firewall.* reason, PORT_BUSY or TV_PLAYING."""
    try:
        local_ip = discovery.local_ip_for(tv.address)
    except OSError as e:
        return firewall.TV_SILENT, "This computer has no route to the TV's address (%s)." % e, ""
    backend = open_tv(tv)
    if not even_if_playing and backend.state().state in ACTIVE:
        return TV_PLAYING, "The TV is playing something; the test would interrupt it.", local_ip
    server = FileServer(local_ip, port)
    try:
        server.start()
    except OSError as e:
        return (
            PORT_BUSY,
            (
                "Port %d on this computer is in use by another program (%s). "
                "If tvsend is already playing something, that is the reason." % (port, e)
            ),
            local_ip,
        )
    try:
        r = firewall.run_test(backend, server)
    finally:
        server.stop()
    return r.reason, r.detail, local_ip


def complete_path(text: str) -> str:
    """Tab completion for a folder path: extend to the longest unambiguous folder name."""
    if not text:
        return text
    full = os.path.expanduser(text)
    head, tail = os.path.split(full)
    try:
        names = sorted(
            n
            for n in os.listdir(head or ".")
            if n.startswith(tail)
            and (tail.startswith(".") or not n.startswith("."))
            and os.path.isdir(os.path.join(head, n))
        )
    except OSError:
        return text
    if not names:
        return text
    common = os.path.commonprefix(names)
    done = os.path.join(head, common) + (os.sep if len(names) == 1 else "")
    return done if len(done) > len(full) else text


class PathInput(Input):
    async def _on_key(self, event):
        if event.key == "tab":
            new = complete_path(self.value)
            if new != self.value:
                self.value = new
                self.cursor_position = len(new)
                event.prevent_default()
                event.stop()
                return
        await super()._on_key(event)


class FolderTree(DirectoryTree):
    def filter_paths(self, paths):
        return [p for p in paths if not p.name.startswith(".") and p.is_dir()]


class SetupWizard(App):
    """Run it, then read .tv and .folder. `run()` returns True when the user finished all steps."""

    TITLE = "tvsend setup"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    #head { height: 1; padding: 0 1; background: $panel; text-style: bold; }
    #steps { height: 1fr; padding: 1 2; }
    #hint { height: 1; padding: 0 1; background: $panel; }
    #tvs { height: auto; max-height: 12; margin: 1 0; }
    #address { display: none; }
    #address.on { display: block; }
    #tree { height: 1fr; margin-top: 1; }
    """
    BINDINGS = [
        Binding("enter", "next", "Next", show=False),
        Binding("n", "next", "Next", show=False),
        Binding("b", "back", "Back", show=False),
        Binding("escape", "back", "Back", show=False),
        Binding("r", "search", "Search again", show=False),
        Binding("m", "manual", "Type an address", show=False),
        Binding("t", "test", "Test again", show=False),
        Binding("a", "apply", "Apply", show=False),
        Binding("q", "leave", "Quit", show=False),
    ]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.step = 0
        self.found: list[TV] = []
        self.typed: set[str] = set()  # IDs of TVs added by typing an address
        self.tv: TV | None = cfg.tv()
        self.folder = cfg.folder or config.default_video_folder()
        self.searching = False
        self.test = None  # None = not run, "running", or (reason, detail, local_ip)
        self.rule: list[str] | None = None
        self.firewall_kind = ""
        self.apply_note = ""
        self._closing = False
        self._search_id = 0
        self._test_id = 0

    # ---- layout
    def compose(self):
        yield Static("", id="head")
        with ContentSwitcher(initial="step0", id="steps"):
            with Vertical(id="step0"):
                yield Static("", id="tv_status")
                yield OptionList(id="tvs")
                yield Input(
                    placeholder="the TV's address, for example 192.168.1.20 - Enter looks it up, Esc cancels",
                    id="address",
                )
            with Vertical(id="step1"):
                yield Static("", id="test_text")
            with Vertical(id="step2"):
                yield Static(
                    "Where are your videos? Sub-folders are included.\n"
                    "Type a path (Tab completes it) or pick a folder in the tree below."
                )
                yield PathInput(value=self.folder, id="path")
                yield FolderTree(os.path.expanduser("~"), id="tree")
                yield Static("", id="folder_msg")
            with Vertical(id="step3"):
                yield Static(KEYS)
        yield Static("", id="hint")

    def on_mount(self):
        self.show_step()
        self.action_search()

    def on_unmount(self):
        self._closing = True

    def from_thread(self, fn, *args):
        if not self._closing:
            try:
                self.call_from_thread(fn, *args)
            except Exception:
                pass

    # ---- moving between steps
    def show_step(self):
        self.query_one("#head", Static).update(
            "Setup %d/%d ─ %s" % (self.step + 1, len(STEPS), STEPS[self.step])
        )
        self.query_one("#steps", ContentSwitcher).current = "step%d" % self.step
        hints = [
            "Enter = choose   r = search again   m = type an address   q = quit",
            "Enter = next   t = test again   b = back   q = quit",
            "Enter = next (in the path field)   Tab = complete / move   Esc = back",
            "Enter = finish   b = back   q = quit",
        ]
        hint = hints[self.step]
        if self.step == 1 and self.rule and self.test_failed():
            hint = "a = apply now   t = test again   Enter = continue anyway   b = back   q = quit"
        self.query_one("#hint", Static).update(hint)
        if self.step == 0:
            self.query_one("#tvs", OptionList).focus()
        elif self.step == 2:
            self.query_one("#path", Input).focus()
        else:
            self.set_focus(None)

    def go(self, step: int):
        self.step = step
        self.show_step()
        if step == 1 and self.test is None:
            self.action_test()

    def action_next(self):
        if self.step == 0:
            self.choose_tv()
        elif self.step == 1:
            if self.test != "running":
                self.go(2)
        elif self.step == 2:
            self.choose_folder()
        else:
            self.exit(True)

    def action_back(self):
        box = self.query_one("#address", Input)
        if self.step == 0 and box.has_class("on"):
            box.remove_class("on")
            self.query_one("#tvs", OptionList).focus()
        elif self.step > 0:
            self.go(self.step - 1)

    def action_leave(self):
        self.exit(False)

    # ---- step 1: the TV
    def action_search(self):
        if self.step != 0 or self.searching:
            return
        self.searching = True
        self._search_id += 1
        self.show_tvs()
        threading.Thread(target=self._search, args=(self._search_id,), daemon=True).start()

    def _search(self, run_id):
        try:
            found = discovery.search()
        except Exception:
            found = []
        self.from_thread(self._searched, run_id, found)

    def _searched(self, run_id, found):
        if run_id != self._search_id:
            return
        self.searching = False
        known = {t.id for t in found}
        typed = [t for t in self.found if t.id not in known and t.id in self.typed]
        self.found = found + typed
        self.show_tvs()

    def show_tvs(self):
        status, box = self.query_one("#tv_status", Static), self.query_one("#tvs", OptionList)
        keep = box.highlighted
        box.clear_options()
        width = max([len(t.name) for t in self.found] + [10])
        for t in self.found:
            box.add_option(Option("%s   %s" % (t.name.ljust(width), t.address), id=t.id))
        if self.found:
            ids = [t.id for t in self.found]
            current = self.tv.id if self.tv else None
            box.highlighted = ids.index(current) if current in ids else min(keep or 0, len(ids) - 1)
        if self.searching:
            status.update(SEARCHING if not self.found else "Looking on your network…")
        elif self.found:
            status.update(
                "Found %d TV%s. Choose the one to send videos to."
                % (len(self.found), "" if len(self.found) == 1 else "s")
            )
        else:
            status.update(NOTHING_FOUND + (MAC_LOCAL_NETWORK if sys.platform == "darwin" else ""))

    def choose_tv(self):
        box = self.query_one("#tvs", OptionList)
        if box.highlighted is None or not self.found:
            return
        tv = self.found[box.highlighted]
        if not self.tv or tv.id != self.tv.id or tv.address != self.tv.address:
            self.test = None  # another TV: the test must run again
        self.tv = tv
        self.go(1)

    def on_option_list_option_selected(self, event):
        event.stop()
        self.choose_tv()

    def action_manual(self):
        if self.step != 0:
            return
        box = self.query_one("#address", Input)
        box.add_class("on")
        box.focus()

    def _lookup(self, text):
        try:
            tv = discovery.from_user_input(text)
        except Exception:
            tv = None
        self.from_thread(self._looked_up, text, tv)

    def _looked_up(self, text, tv):
        status = self.query_one("#tv_status", Static)
        if not tv:
            status.update(
                "Nothing at %s answered as a TV that accepts video. Check the address and "
                "that the TV is on." % text
            )
            return
        self.typed.add(tv.id)  # keep it in the list across "search again"
        self.found = [t for t in self.found if t.id != tv.id] + [tv]
        self.tv = tv
        box = self.query_one("#address", Input)
        box.value = ""
        box.remove_class("on")
        self.show_tvs()
        self.query_one("#tvs", OptionList).focus()

    # ---- step 2: the connection test
    def test_failed(self) -> bool:
        return isinstance(self.test, tuple) and self.test[0] != firewall.OK

    def action_test(self, even_if_playing=None):
        if self.step != 1 or self.test == "running" or not self.tv:
            return
        if even_if_playing is None:  # pressing t after "the TV is playing" means: test anyway
            even_if_playing = isinstance(self.test, tuple) and self.test[0] == TV_PLAYING
        self.test, self.rule = "running", None
        self._test_id += 1
        self.show_test()
        threading.Thread(
            target=self._test, args=(self._test_id, self.tv, even_if_playing), daemon=True
        ).start()

    def _test(self, run_id, tv, even_if_playing):
        try:
            result = test_connection(tv, self.cfg.port, even_if_playing)
        except Exception as e:
            result = (firewall.BLOCKED, "The test itself failed: %s" % e, "")
        kind, rule = "", None
        if result[0] == firewall.BLOCKED:
            kind = firewall.detect()
            rule = firewall.rule_command(kind, tv.address, result[2], self.cfg.port)
        self.from_thread(self._tested, run_id, result, kind, rule)

    def _tested(self, run_id, result, kind, rule):
        if run_id != self._test_id:
            return
        self.test, self.firewall_kind, self.rule = result, kind, rule
        self.show_test()
        self.show_step()

    def show_test(self):
        out = Text()
        name = self.tv.name if self.tv else "the TV"
        out.append(
            "tvsend runs a small file server on this computer, and %s fetches the video from it.\n"
            "This step checks that the TV can get through.\n\n" % name
        )
        if self.test == "running":
            out.append("Testing… (up to 10 seconds)")
        elif isinstance(self.test, tuple):
            reason, detail, _ = self.test
            if reason == firewall.OK:
                out.append("✔ Passed. ", style="bold green")
                out.append(detail + "\n\nPress Enter to continue.")
            elif reason == TV_PLAYING:
                out.append("Not tested. ", style="bold yellow")
                out.append(detail + "\n\nPress t to test anyway, or Enter to skip the test.")
            elif reason == PORT_BUSY:
                out.append("Not tested. ", style="bold yellow")
                out.append(detail + "\n\nPress t to try again, or Enter to continue without the test.")
            elif reason == firewall.TV_SILENT:
                out.append("✘ Failed. ", style="bold red")
                out.append(
                    detail + "\n\nPress t to test again, b to choose another TV, or Enter to continue anyway."
                )
            else:
                out.append("✘ Blocked. ", style="bold red")
                out.append(detail + "\n\n")
                out.append(
                    "Firewall on this computer: %s.\n"
                    % firewall.FIREWALL_NAME.get(self.firewall_kind, self.firewall_kind)
                )
                out.append(firewall.explain(self.firewall_kind) + "\n")
                if self.rule:
                    out.append("\n    " + firewall.command_text(self.rule) + "\n\n", style="bold")
                    out.append(
                        "Press a and tvsend runs this command for you (it asks for your password), "
                        "or run it yourself in another terminal and press t to test again."
                    )
                else:
                    out.append("\nPress t to test again, or Enter to continue anyway.")
            if self.apply_note:
                out.append("\n\n" + self.apply_note, style="yellow")
        self.query_one("#test_text", Static).update(out)

    def action_apply(self):
        if self.step != 1 or not self.rule or not self.test_failed():
            return
        cmd = self.rule
        with self.suspend():
            print("\ntvsend is about to run:\n\n    %s\n" % firewall.command_text(cmd), flush=True)
            ok, output = firewall.apply(cmd)
            if output:
                print(output, flush=True)
        self.apply_note = (
            ""
            if ok
            else "The command did not succeed%s" % (": " + output.splitlines()[-1] if output else ".")
        )
        self.test = None
        self.action_test(even_if_playing=True)

    # ---- step 3: the folder
    def on_directory_tree_directory_selected(self, event):
        event.stop()
        box = self.query_one("#path", Input)
        box.value = str(event.path)
        box.cursor_position = len(box.value)
        self.query_one("#folder_msg", Static).update("")

    def choose_folder(self):
        text = self.query_one("#path", Input).value.strip()
        path = os.path.abspath(os.path.expanduser(text)) if text else ""
        if not path or not os.path.isdir(path):
            self.query_one("#folder_msg", Static).update(
                Text(
                    "Type the path of a folder." if not path else "There is no folder %s" % path,
                    style="bold red",
                )
            )
            return
        self.folder = path
        self.go(3)

    def on_input_submitted(self, event):
        event.stop()
        if event.input.id == "address":
            text = event.value.strip()
            if text:
                self.query_one("#tv_status", Static).update("Asking %s…" % text)
                threading.Thread(target=self._lookup, args=(text,), daemon=True).start()
        elif event.input.id == "path":
            self.choose_folder()


def run_wizard(cfg: Config) -> bool:
    """Run the setup. On completion the choices are put into cfg and saved; returns False if the user quit."""
    app = SetupWizard(cfg)
    if not app.run() or not app.tv:
        return False
    cfg.add_tv(app.tv, make_default=True)
    cfg.folder = app.folder
    config.save(cfg)
    return True
