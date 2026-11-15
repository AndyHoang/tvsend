"""The pop-up screens of the list: choose a folder (f), switch TV (t), a yes/no question."""

import os
import threading

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, OptionList, Static
from textual.widgets.option_list import Option

from .. import discovery
from ..config import TV, Config
from .wizard import FolderTree, PathInput

BOX_CSS = """
    %s { align: center middle; }
    %s > Vertical {
        width: 90%%; max-width: 100; height: auto; max-height: 90%%;
        padding: 1 2; border: round $primary; background: $surface;
    }
"""


def folder_problem(path: str) -> str:
    """Why this cannot be the video folder ('' = it can)."""
    if not path:
        return "Type a folder path."
    if not os.path.isdir(path):
        return "There is no folder %s" % path
    if not os.access(path, os.R_OK | os.X_OK):
        return "This folder cannot be read: %s" % path
    return ""


class ConfirmScreen(ModalScreen):
    """A yes/no question. Gives True (y / Enter), False (n) or None (Esc: never mind)."""

    DEFAULT_CSS = BOX_CSS % ("ConfirmScreen", "ConfirmScreen")
    BINDINGS = [
        Binding("y,enter", "answer(True)", "Yes"),
        Binding("n", "answer(False)", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, question: str, hint: str = "y = yes · n = no · Esc = cancel"):
        super().__init__()
        self.question, self.hint = question, hint

    def compose(self):
        text = Text(self.question + "\n\n", style="bold")
        text.append(self.hint, style="dim")
        with Vertical():
            yield Static(text, id="question")

    def action_answer(self, yes: bool):
        self.dismiss(yes)

    def action_cancel(self):
        self.dismiss(None)


class FolderScreen(ModalScreen):
    """Choose the video folder: type a path (Tab completes) or pick it in the tree.
    Gives (the folder's absolute path, remember it as the regular folder?), or None when cancelled."""

    DEFAULT_CSS = (
        (BOX_CSS % ("FolderScreen", "FolderScreen"))
        + """
    FolderScreen #tree { height: 14; margin-top: 1; }
    FolderScreen #problem { color: $error; }
    """
    )
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, start: str):
        super().__init__()
        self.start = start

    def compose(self):
        with Vertical():
            yield Static(Text("Choose your video folder", style="bold"))
            yield PathInput(value=self.start, placeholder="folder path", id="path")
            yield Checkbox(
                "Remember as my regular folder (off: only until tvsend closes)", True, id="remember"
            )
            yield FolderTree(os.path.expanduser("~"), id="tree")
            yield Static("", id="problem")
            yield Static(
                Text("Enter in the path field confirms · Tab completes the path, then moves on to the "
                     "switch (Space flips it) and the folder tree (Enter picks a folder) · Esc cancels",
                     style="dim")
            )  # fmt: skip

    def on_mount(self):
        box = self.query_one("#path", Input)
        box.focus()
        box.cursor_position = len(box.value)

    def on_directory_tree_directory_selected(self, event):
        event.stop()
        box = self.query_one("#path", Input)
        box.value = str(event.path)
        box.cursor_position = len(box.value)
        self.query_one("#problem", Static).update("")

    def on_input_changed(self, event):
        event.stop()  # not the list's filter

    def on_input_submitted(self, event):
        event.stop()
        text = event.value.strip()
        path = os.path.abspath(os.path.expanduser(text)) if text else ""
        problem = folder_problem(path)
        if problem:
            self.query_one("#problem", Static).update(problem)
        else:
            self.dismiss((path, self.query_one("#remember", Checkbox).value))

    def action_cancel(self):
        self.dismiss(None)


class TvScreen(ModalScreen):
    """Choose a TV: the saved ones at once, newly found ones after a search of the network.
    Gives the chosen TV, or None when cancelled."""

    DEFAULT_CSS = (
        (BOX_CSS % ("TvScreen", "TvScreen"))
        + """
    TvScreen #tvs { height: auto; max-height: 12; margin: 1 0; }
    TvScreen #address { display: none; }
    TvScreen #address.on { display: block; }
    """
    )
    BINDINGS = [
        Binding("r", "search", "Search again"),
        Binding("m", "manual", "Type an address"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, cfg: Config, current_id: str):
        super().__init__()
        self.cfg, self.current_id = cfg, current_id
        self.saved = {t.id: t for t in cfg.tvs}
        self.found: dict[str, TV] = {}  # seen on the network (or typed) in this dialog
        self.searched = False
        self._search_id = 0
        self._closed = False

    def compose(self):
        with Vertical():
            yield Static(Text("Choose your TV", style="bold"))
            yield OptionList(id="tvs")
            yield Input(placeholder="the TV's address - Enter looks it up, Esc cancels", id="address")
            yield Static("", id="state")
            yield Static(
                Text("Enter = choose · r = search again · m = type an address · Esc = cancel", style="dim")
            )

    def on_mount(self):
        self.fill()
        self.query_one("#tvs", OptionList).focus()
        self.action_search()

    def on_unmount(self):
        self._closed = True

    # -- the list
    def rows(self) -> list[TV]:
        tvs = [self.found.get(i, t) for i, t in self.saved.items()]
        tvs += [t for i, t in self.found.items() if i not in self.saved]
        return tvs

    def fill(self):
        box = self.query_one("#tvs", OptionList)
        keep = box.highlighted
        box.clear_options()
        tvs = self.rows()
        width = max([len(t.name) for t in tvs] + [8])
        for t in tvs:
            notes = [
                n
                for n, on in (
                    ("in use", t.id == self.current_id),
                    ("default", t.id == self.cfg.default_tv),
                    ("saved", t.id in self.saved),
                    ("new", t.id not in self.saved),
                    ("not found right now", self.searched and t.id not in self.found),
                )
                if on
            ]
            box.add_option(
                Option("%s   %-15s  (%s)" % (t.name.ljust(width), t.address, ", ".join(notes)), id=t.id)
            )
        if tvs:
            box.highlighted = min(keep or 0, len(tvs) - 1)

    def say(self, text: str):
        try:
            self.query_one("#state", Static).update(text)
        except Exception:
            pass

    def _from_thread(self, fn, *args):
        if not self._closed:
            try:
                self.app.call_from_thread(fn, *args)
            except Exception:
                pass

    # -- searching
    def action_search(self):
        self._search_id += 1
        self.say("Looking on your network…")
        threading.Thread(target=self._search, args=(self._search_id,), daemon=True).start()

    def _search(self, search_id: int):
        try:
            tvs = discovery.search()
        except Exception:
            tvs = []
        self._from_thread(self._searched, search_id, tvs)

    def _searched(self, search_id: int, tvs: list[TV]):
        if search_id != self._search_id or self._closed:
            return
        typed = {i: t for i, t in self.found.items() if i not in self.saved and i not in {t.id for t in tvs}}
        self.found = {**{t.id: t for t in tvs}, **typed}
        self.searched = True
        self.fill()
        if tvs:
            self.say("%d TV%s found on your network." % (len(tvs), "" if len(tvs) == 1 else "s"))
        else:
            self.say("No TV found on your network. Is it on, and on the same network? r searches again.")

    # -- typing an address
    def action_manual(self):
        box = self.query_one("#address", Input)
        box.add_class("on")
        box.focus()

    def _hide_address(self):
        box = self.query_one("#address", Input)
        box.value = ""
        box.remove_class("on")
        self.query_one("#tvs", OptionList).focus()

    def on_input_changed(self, event):
        event.stop()  # not the list's filter

    def on_input_submitted(self, event):
        event.stop()
        text = event.value.strip()
        if not text:
            return self._hide_address()
        self.say("Asking %s…" % text)
        threading.Thread(target=self._lookup, args=(text,), daemon=True).start()

    def _lookup(self, text: str):
        try:
            tv = discovery.from_user_input(text)
        except Exception:
            tv = None
        self._from_thread(self._looked_up, text, tv)

    def _looked_up(self, text: str, tv: TV | None):
        if self._closed:
            return
        if not tv:
            return self.say("No TV that accepts video answered at %s." % text)
        self.found[tv.id] = tv
        self._hide_address()
        self.fill()
        ids = [t.id for t in self.rows()]
        self.query_one("#tvs", OptionList).highlighted = ids.index(tv.id)
        self.say("Found %s. Enter chooses it." % tv.name)

    # -- choosing
    def on_option_list_option_selected(self, event):
        event.stop()
        tv = next((t for t in self.rows() if t.id == event.option.id), None)
        if tv:
            self.dismiss(tv)

    def action_cancel(self):
        if self.query_one("#address", Input).has_class("on"):
            return self._hide_address()
        self.dismiss(None)
