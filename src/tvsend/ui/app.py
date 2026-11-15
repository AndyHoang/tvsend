"""The full-screen list: pick a clip, press Enter, it plays on the TV."""

import os
import queue
import time

from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Static

from .. import config, library
from ..backends.base import ACTIVE, PAUSED, STATE_TEXT
from ..library import SORT_TEXT, SORTS, clock, date_text, fold, size_text, sort_entries
from ..player import POLL, Controller, url_name

REFRESH_SECONDS = float(os.environ.get("TVSEND_REFRESH", 10))  # the list re-reads the folder this often
FOLLOW_PAUSE = 10.0 * POLL  # after you move the highlight yourself, it is not moved for you this long
MESSAGE_SECONDS = 15.0  # how long a message stays on the message line

HELP_KEYS = [
    ("Enter", "play from the highlighted clip on down the list (with marked clips: just those, in order)"),
    ("Space", "mark / unmark a clip - the number shows the playing order"),
    ("n / b", "next / previous clip"),
    ("p", "pause / resume"),
    ("r", "restart the current clip"),
    ("s", "stop playback on the TV"),
    ("l", "switch between loop and once"),
    ("o", "change the sort order (clicking a column header sorts by it too)"),
    ("/", "filter by name - Enter keeps the filter, Esc clears it"),
    ("R", "re-read the folder now"),
    ("↑ ↓  j k", "move the highlight (also PageUp / PageDown, Home / End, the mouse)"),
    ("?", "this help"),
    ("q", "quit"),
]


class HelpScreen(ModalScreen):
    """All keys on one page. Any key closes it."""

    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > Vertical {
        width: auto; max-width: 96%; height: auto; max-height: 90%;
        padding: 1 2; border: round $primary; background: $surface;
    }
    """

    def compose(self):
        text = Text()
        text.append("Keys\n\n", style="bold")
        for key, what in HELP_KEYS:
            text.append("  %-10s" % key, style="bold cyan")
            text.append(what + "\n")
        text.append("\nPress any key to close.", style="dim")
        with Vertical():
            yield Static(text, id="help")

    def on_key(self, event):
        event.stop()
        event.prevent_default()
        self.dismiss()

    def on_click(self, event):
        self.dismiss()


class ClipTable(DataTable):
    def action_scroll_home(self):  # Home/End move the highlighted row, not just the view
        if self.row_count:
            self.move_cursor(row=0)

    def action_scroll_end(self):
        if self.row_count:
            self.move_cursor(row=self.row_count - 1)


class TvApp(App):
    TITLE = "tvsend"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    #filter { display: none; height: 3; }
    #filter.on { display: block; }
    #clips { height: 1fr; }
    #status { height: 2; padding: 0 1; background: $panel; }
    #msg { height: 1; padding: 0 1; }
    """
    BINDINGS = [
        Binding("enter", "play", "Play from here"),
        Binding("space", "mark", "Mark"),
        Binding("l", "loop", "Loop/once"),
        Binding("n", "next", "Next"),
        Binding("b", "prev", "Back"),
        Binding("r", "restart", "Restart"),
        Binding("p", "pause", "Pause"),
        Binding("s", "stop", "Stop"),
        Binding("o", "sort", "Sort"),
        Binding("slash", "filter", "Filter", key_display="/"),
        Binding("R", "refresh", "Refresh"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("q", "quit", "Quit"),
        Binding("j", "down", "Down", show=False),
        Binding("k", "up", "Up", show=False),
        Binding("escape", "clear_filter", "Clear filter", show=False),
    ]
    COLUMNS = [
        ("mark", "", 3),
        ("name", "Clip", None),
        ("len", "Length", 8),
        ("size", "Size", 9),
        ("date", "Changed", 16),
    ]
    SORT_COLUMN = {"name": "name", "len": "length", "size": "size", "date": "newest"}  # clickable headers

    def __init__(self, cfg, folder, backend, server=None, ctrl=None):
        """`ctrl` is the player to drive: the background player's client, or (default) a
        player of its own that lives only as long as this window."""
        super().__init__()
        self.cfg, self.folder, self.backend, self.server = cfg, folder, backend, server
        self.entries, self.shown, self.notes, self.marks = [], [], [], []
        self.filter_text, self.playing_path = "", None
        self.loop = bool(cfg.loop)
        self.sort = cfg.sort if cfg.sort in SORT_TEXT else "name"
        self.ctrl = ctrl or Controller(backend, server)
        self.live = False  # True: the queue is the list itself and follows sort/filter/new clips
        self._closing = False
        self._expected = None  # row the highlight was last put on by the program
        self.user_moved = 0.0  # when the user last moved the highlight
        self._msg = ("", "info", 0.0)  # the message line: text, level, when

    # ---- layout
    def compose(self):
        yield Input(placeholder="type part of a name - Enter keeps the filter, Esc clears it", id="filter")
        yield ClipTable(id="clips", cursor_type="row", zebra_stripes=True)
        yield Static("", id="status")
        yield Static("", id="msg")
        yield Footer()

    def on_mount(self):
        self.table = self.query_one("#clips", DataTable)
        self.refresh_list(force=True)
        self.table.focus()
        if not self.ctrl.is_alive():
            self.ctrl.start()
        v = self.ctrl.view()
        if v["item"]:  # opened while the background player is busy: join in, change nothing
            note = getattr(self.ctrl, "note", None) or {}
            self.loop = bool(v["loop"])
            self.live = bool(note.get("live")) and note.get("folder") == self.folder
            self.sync_queue()
        else:
            self.ctrl.send("loop", self.loop)
        self.set_interval(0.5, self.update_status)
        self.set_interval(REFRESH_SECONDS, self.refresh_list)
        self.update_status()

    def on_unmount(self):
        self._closing = True

    def save_prefs(self):
        self.cfg.sort, self.cfg.loop = self.sort, self.loop
        try:
            config.save(self.cfg)
        except OSError:
            pass

    # ---- messages: one line above the key help (no pop-ups)
    def flash(self, text, level="info"):
        self._msg = (text, level, time.time())
        self.show_message()

    def show_message(self):
        text, level, when = self._msg
        if text and time.time() - when > MESSAGE_SECONDS:
            self._msg = ("", "info", 0.0)
            text = ""
        style = {"warning": "bold yellow", "error": "bold red"}.get(level, "")
        try:
            self.query_one("#msg", Static).update(Text(text, style=style, no_wrap=True, overflow="ellipsis"))
        except Exception:
            pass

    def texts(self):
        """Everything written below the list (used by the tests)."""
        tv, info, _ = self.status_lines()
        return "\n".join([tv, info, self._msg[0]])

    # ---- the list
    def cells(self, e):
        return {
            "mark": self.mark_text(e["path"]),
            "name": Text(e["name"]),
            "len": Text(clock(e["dur"]) if e["dur"] else ""),
            "size": Text(size_text(e["size"])),
            "date": Text(date_text(e["mtime"])),
        }

    def mark_text(self, path):
        if path == self.playing_path:
            return Text("▶", style="bold green")
        if path in self.marks:
            return Text(str(self.marks.index(path) + 1), style="bold cyan")
        return Text("")

    def cursor_path(self):
        if not self.table.row_count:
            return None
        try:
            return self.table.coordinate_to_cell_key(self.table.cursor_coordinate).row_key.value
        except Exception:
            return None

    def cursor_entry(self):
        p = self.cursor_path()
        return next((e for e in self.entries if e["path"] == p), None)

    def put_cursor(self, row):
        """Move the highlight from the program (not counted as the user moving it)."""
        if 0 <= row < len(self.shown):
            self._expected = self.shown[row]["path"]
            self.table.move_cursor(row=row)

    def on_data_table_row_highlighted(self, event):
        cur = self.cursor_path()
        if cur != self._expected:  # the user moved it (keys or mouse)
            self._expected = cur
            self.user_moved = time.time()

    def rebuild(self):
        """Redraw the list as filtered and sorted; the running queue follows it."""
        keep, row = self.cursor_path(), self.table.cursor_row
        f = fold(self.filter_text)
        self.shown = sort_entries([e for e in self.entries if f in fold(e["name"])], self.sort)
        self.table.clear(columns=True)
        for key, label, width in self.COLUMNS:
            if self.SORT_COLUMN.get(key) == self.sort.lstrip("-"):
                label += " ▼" if self.sort.startswith("-") else " ▲"
            self.table.add_column(label, key=key, width=width)
        for e in self.shown:
            self.table.add_row(*self.cells(e).values(), key=e["path"])
        paths = [e["path"] for e in self.shown]
        if paths:
            self.put_cursor(paths.index(keep) if keep in paths else min(max(row, 0), len(paths) - 1))
        else:
            self._expected = None
        self.sync_queue()

    def sync_queue(self):
        if self.live and self.ctrl.cur:
            self.ctrl.send("queue", list(self.shown))

    @staticmethod
    def _signature(entries):
        return [(e["path"], e["size"], e["mtime"], e["dur"]) for e in entries]

    def refresh_list(self, force=False):
        entries, self.notes = library.scan(self.folder)
        changed = self._signature(entries) != self._signature(self.entries)
        self.entries = entries
        paths = {e["path"] for e in entries}
        self.marks = [p for p in self.marks if p in paths]
        if changed or force:
            self.rebuild()

    def update_marks(self):
        for e in self.shown:
            try:
                self.table.update_cell(e["path"], "mark", self.mark_text(e["path"]))
            except Exception:
                pass

    # ---- status lines
    def status_lines(self):
        v = self.ctrl.view()
        st, it = v["st"], v["item"]
        mode = "loop" if self.loop else "once"
        name = self.backend.name
        if st is None:
            tv = "%s: checking…" % name
        elif st == "":
            tv = "%s: not answering (switched off, or not on this network?)" % name
        elif st in ACTIVE:
            if it:
                clip = it["name"]
                where = "%d/%d  " % (v["k"] + 1, v["n"]) if v["k"] >= 0 else ""
            else:
                clip, where = url_name(v["uri"]) or "(something)", ""
            tv = "%s: %s %s%s  %s / %s  %s" % (
                name,
                "⏸" if st == PAUSED else "▶",
                where,
                clip,
                clock(v["pos"]) if v["pos"] else "0:00",
                clock(v["dur"]),
                STATE_TEXT.get(st, st.lower()),
            )
            tv += "   [%s]" % mode if it else "   (not started from this window)"
        else:
            tv = "%s: idle" % name
        if self.entries:
            info = [
                "mode: " + mode,
                "sorted by " + SORT_TEXT.get(self.sort, self.sort),
                "%d clip%s" % (len(self.entries), "" if len(self.entries) == 1 else "s"),
            ]
        else:
            info = ["mode: " + mode, "no videos found in %s" % self.folder]
        if self.filter_text:
            info.append('filter "%s": %d shown' % (self.filter_text, len(self.shown)))
        if self.marks:
            info.append("%d marked - Enter plays just those, in order" % len(self.marks))
        if self.notes:
            info.append("note: " + self.notes[0])
        return tv, "  ·  ".join(info), (it["path"] if it else None)

    def update_status(self):
        while True:  # things the player wants the user to know
            try:
                level, text = self.ctrl.events.get_nowait()
            except queue.Empty:
                break
            self.flash(text, level)
        tv, info, playing = self.status_lines()
        try:
            text = Text(tv + "\n" + info, no_wrap=True, overflow="ellipsis")
            self.query_one("#status", Static).update(text)
        except Exception:  # the screen is closing
            return
        self.show_message()
        if playing != self.playing_path:
            self.playing_path = playing
            self.update_marks()
            self.follow()

    def follow(self):
        """Put the highlight on the clip that is on the TV - unless the user is busy in the list."""
        p = self.playing_path
        busy = time.time() - self.user_moved < FOLLOW_PAUSE or self.query_one("#filter", Input).has_focus
        if not p or busy:
            return
        paths = [e["path"] for e in self.shown]
        if p in paths:  # hidden by the filter: leave everything as it is
            self.put_cursor(paths.index(p))

    # ---- keys
    def on_data_table_row_selected(self, event):
        self.action_play()

    def on_data_table_header_selected(self, event):
        field = self.SORT_COLUMN.get(event.column_key.value)
        if field:  # first click: that order, click again: the other way round
            self.set_sort("-" + field if self.sort == field else field)

    def action_play(self):
        if self.marks:  # marked clips: exactly those, in the order they were marked
            by_path = {e["path"]: e for e in self.entries}
            picks = [by_path[p] for p in self.marks if p in by_path]
            start, self.live = 0, False
        else:  # otherwise: from the highlighted clip on down the list as shown
            e = self.cursor_entry()
            if not e or e not in self.shown:
                return
            picks, start, self.live = list(self.shown), self.shown.index(e), True
        if not picks:
            return
        self.marks = []
        self.user_moved = 0.0  # from now on the highlight follows the TV again
        self.ctrl.send("loop", self.loop)
        self.ctrl.send("play", picks, start)
        if hasattr(self.ctrl, "set_note"):  # so a window opened later knows the queue follows this list
            self.ctrl.set_note({"live": self.live, "folder": self.folder})
        self.update_marks()
        self.table.focus()

    def action_mark(self):
        p = self.cursor_path()
        if not p:
            return
        if p in self.marks:
            self.marks.remove(p)
        else:
            self.marks.append(p)
        self.update_marks()
        self.table.action_cursor_down()
        self.update_status()

    def action_loop(self):
        self.loop = not self.loop
        self.ctrl.send("loop", self.loop)
        self.save_prefs()
        self.update_status()

    def action_next(self):
        self.ctrl.send("next")

    def action_prev(self):
        self.ctrl.send("prev")

    def action_restart(self):
        self.ctrl.send("restart")

    def action_pause(self):
        self.ctrl.send("pause")

    def action_stop(self):
        self.ctrl.send("stop")

    def set_sort(self, spec):
        self.sort = spec
        self.save_prefs()
        self.rebuild()  # what plays next follows the new order; the current clip goes on
        self.update_status()

    def action_sort(self):
        self.set_sort(SORTS[(SORTS.index(self.sort) + 1) % len(SORTS)] if self.sort in SORTS else "name")

    def action_refresh(self):
        self.refresh_list(force=True)
        self.flash("List refreshed: %d clip%s" % (len(self.entries), "" if len(self.entries) == 1 else "s"))

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_down(self):
        self.table.action_cursor_down()

    def action_up(self):
        self.table.action_cursor_up()

    def action_filter(self):
        box = self.query_one("#filter", Input)
        box.add_class("on")
        box.focus()

    def action_clear_filter(self):
        box = self.query_one("#filter", Input)
        box.value = ""
        box.remove_class("on")
        self.table.focus()

    def on_input_changed(self, event):
        self.filter_text = event.value.strip()
        self.rebuild()
        self.update_status()

    def on_input_submitted(self, event):
        if not self.filter_text:
            self.query_one("#filter", Input).remove_class("on")
        self.table.focus()
