"""The player: owns the queue and all talking to the TV."""

import os
import queue
import threading
import time
import urllib.parse

from . import library
from .backends.base import HALTED, LOADING, PAUSED, PLAYING, Backend
from .server import FileServer, mime_for

POLL = float(os.environ.get("TVSEND_POLL", 1.0))  # seconds between TV status checks; all waits scale with it
END_SLACK = float(os.environ.get("TVSEND_END_SLACK", 4.0))  # this close to the end counts as "ended"

STOP_CONFIRM = 2.5 * POLL  # "stopped" must last this long before it counts as the viewer pressing Stop
SEEK_GRACE = 4.0 * POLL  # after a restart/seek, odd states from the TV are ignored this long
START_RETRY = 8.0 * POLL  # nothing happened after Play: send Play once more
START_GIVE_UP = 20.0 * POLL  # still nothing: the TV cannot play this clip
LOAD_GIVE_UP = 60.0 * POLL  # stuck on "loading" this long: give up
LOAD_MIN = 3.0 * POLL  # loading, then stopped without ever playing, after at least this long = cannot play
RESUME_MIN = 10.0  # a session is continued mid-clip only this far from the clip's start and end
LOST_AFTER = 8  # this many unanswered checks in a row: the TV is gone


def same_url(a: str, b: str) -> bool:
    return urllib.parse.unquote(a or "") == urllib.parse.unquote(b or "")


def url_name(uri: str) -> str:
    return urllib.parse.unquote(os.path.basename(urllib.parse.urlsplit(uri).path))


class Controller(threading.Thread):
    """Runs in the background so the screen never waits for the TV.

    It keeps a queue of clips and walks one clip at a time through these steps:

        loading  -> playing <-> paused -> ended            -> next clip (or first again when looping)
           |           |                -> stopped by the viewer -> queue cleared
           |           +-> something else is playing        -> queue cleared, TV left alone
           +-> never started (TV cannot play it)            -> said in plain words, next clip

    Pausing or seeking - from tvsend or from the TV remote - never ends the queue: only a
    "stopped" that lasts (STOP_CONFIRM) and is not at the end of the clip counts as the viewer
    pressing Stop. Front ends only send() commands and read view() / events.

    Queue items are plain dicts (path, name, size, mtime, dur; 'remote' for a link), so they
    can later travel over a socket unchanged.
    """

    def __init__(self, tv: Backend, server: FileServer | None, refill=None):
        super().__init__(daemon=True, name="tvsend-player")
        self.tv, self.server = tv, server
        self.cmds: queue.Queue = queue.Queue()
        self.events: queue.Queue = queue.Queue()
        self.refill = refill  # optional: called at each new round, returns the fresh clip list
        self.items: list[dict] = []
        self.k, self.loop, self.cur = 0, True, None
        self.st, self.pos, self.dur, self.uri = None, 0.0, 0.0, ""
        self.message, self.errors, self.ended = "", 0, None
        self.now = None  # the clip being played (stays valid while the queue is re-ordered)
        self._pending = 0  # "play" commands sent but not handled yet
        self._pending_lock = threading.Lock()
        self._resume = 0.0  # where the first clip of a continued session picks up (seconds)

    # -- used by the front ends
    def send(self, *cmd):
        if cmd[0] == "play":
            with self._pending_lock:
                self._pending += 1
        self.cmds.put(cmd)

    def view(self) -> dict:
        return {
            "st": self.st,
            "pos": self.pos,
            "dur": self.dur,
            "uri": self.uri,
            "item": self.now if self.cur else None,
            "k": self.k,
            "n": len(self.items),
            "loop": self.loop,
            "message": self.message,
            # a "play" that is still on its way must not be mistaken for the end of the one before
            "ended": None if self._pending else self.ended,
        }

    def say(self, text, level="info"):
        self.message = text
        self.events.put((level, text))

    # -- main loop
    def run(self):
        next_poll = 0.0
        while True:
            try:
                cmd = self.cmds.get(timeout=max(0.0, next_poll - time.time()))
            except queue.Empty:
                cmd = None
            if cmd:
                if cmd[0] == "close":
                    return
                try:
                    self._handle(cmd)
                except Exception as e:  # never let the watcher die
                    self.say("Problem: %s" % e, "error")
                if cmd[0] == "play":
                    with self._pending_lock:
                        self._pending -= 1
                next_poll = min(next_poll, time.time() + 0.15 * POLL)
                continue
            next_poll = time.time() + POLL
            try:
                self._poll()
            except Exception as e:
                self.say("Problem: %s" % e, "error")

    # -- commands
    def _handle(self, cmd):
        name = cmd[0]
        if name == "play":
            self._play(cmd[1], cmd[2] if len(cmd) > 2 else 0, cmd[3] if len(cmd) > 3 else 0.0)
        elif name == "say":
            self.say(cmd[1], cmd[2] if len(cmd) > 2 else "info")
        elif name == "queue":
            self._requeue(cmd[1])
        elif name == "loop":
            self.loop = cmd[1]
        elif name in ("next", "prev"):
            if self.cur:
                self._advance(name)
            else:
                self.say("Nothing is queued - pick a clip and press Enter.")
        elif name == "restart":
            ok, _ = self.tv.seek(0)
            if self.cur:
                self.cur.update(
                    last_pos=0.0, last_t=time.time(), grace=time.time() + SEEK_GRACE, stop_since=None
                )
            self.say("Restarted the clip." if ok else 'The TV did not accept "restart".')
        elif name == "pause":
            ok, _ = self.tv.play() if self.st == PAUSED else self.tv.pause()
            if not ok:
                self.say('The TV did not accept "pause/resume".')
        elif name == "stop":
            ok, _ = self.tv.stop()
            self._finish("stopped", "Stopped." if ok else 'The TV did not accept "stop" (nothing playing?).')

    def _finish(self, reason, message, level="info"):
        self.items, self.k, self.cur, self.now, self.ended = [], 0, None, None, reason
        self.say(message, level)

    @staticmethod
    def _prepare(picked, old=()):
        """Turn clips into queue items, keeping what is already known about them."""
        known = {it["path"]: it for it in old}
        items = []
        for e in picked:
            it, o = dict(e), known.get(e["path"], {})
            it["failed"] = o.get("failed")
            items.append(it)
        return items

    def _play(self, picked, start=0, position=0.0):
        """Play the clips from number `start` on. `position` (seconds) continues the first
        clip from where an interrupted session had got to."""
        self.ended = None
        items = self._prepare(picked)
        if not items:
            return self._finish("failed", "Nothing to play.")
        self.items, self.k, self.message = items, max(0, min(start, len(items) - 1)), ""
        self._resume = float(position or 0.0)
        self._start()

    def _requeue(self, picked):
        """The list changed (new clips, other sort or filter): what comes next follows it,
        the clip on the TV right now is not interrupted."""
        if not self.cur or not self.now:
            return
        self.items = self._prepare(picked, self.items)
        paths = [it["path"] for it in self.items]
        self.k = paths.index(self.now["path"]) if self.now["path"] in paths else -1

    def _start(self, attempt=1):
        it = self.now if attempt > 1 and self.now else self.items[self.k]
        self.now = it
        now = time.time()
        self.cur = {
            "url": "",
            "attempt": attempt,
            "t0": now,
            "started": False,
            "loading_seen": False,
            "replayed": False,
            "last_pos": 0.0,
            "last_t": now,
            "was_playing": False,
            "stop_since": None,
            "other": 0,
            "grace": 0.0,
            "dur": it.get("dur") or 0.0,
            "length_saved": False,
            "resume": self._resume if attempt == 1 else 0.0,
        }
        self._resume = 0.0
        self.st, self.pos, self.dur = LOADING, 0.0, it.get("dur") or 0.0
        if it.get("remote"):
            url = it["path"]
        else:
            try:
                url = self.server.add(it["path"])
            except (OSError, AttributeError) as err:
                return self._failed("this computer could not share it (%s)" % err, retry=False)
        self.cur["url"] = url
        title, mime = os.path.splitext(os.path.basename(it["name"]))[0], mime_for(it["name"])
        ok, reply = self.tv.load(url, title, mime)
        if not ok:  # the TV can refuse while it is busy: stop it and try once more
            self.tv.stop()
            time.sleep(min(1.0, POLL))
            ok, reply = self.tv.load(url, title, mime)
        if not ok:
            return self._failed("the TV refused it (%s)" % reply, retry=False)
        self.cur["t0"] = self.cur["last_t"] = time.time()
        self.tv.play()

    def _failed(self, what, retry=True):
        """The current clip did not start. Try once more when that makes sense, else explain and move on."""
        it, c = self.now, self.cur
        if retry and c["attempt"] == 1:
            return self._start(attempt=2)
        for x in [it] + [x for x in self.items if x["path"] == it["path"]]:
            x["failed"] = what
        self.say(
            "The TV could not play %s: %s. The TV may not support this kind of file, or it is "
            "showing another app." % (it["name"], what),
            "warning",
        )
        self._advance("skip")

    def _advance(self, res):
        """Move to the next (or previous) clip in list order, wrapping when looping;
        clips that failed are passed over."""
        items = self.items
        n, k = len(items), self.k
        if n and all(it.get("failed") for it in items):
            return self._finish("failed", "The TV could not play any of the picked clips.", "warning")
        for _ in range(n + 1):
            if not n:
                break
            if res == "prev":
                k = (k - 1) % n if k >= 0 else n - 1
            else:
                k += 1
                if k >= n:
                    if not self.loop:
                        if res == "next":
                            self.tv.stop()
                        return self._finish("finished", "Finished.")
                    k = 0
                    if self.refill:  # new files join at the start of each round
                        try:
                            fresh = self._prepare(self.refill(), items)
                        except Exception:
                            fresh = []
                        if fresh:
                            self.items = items = fresh
                            n = len(items)
            if items[k].get("failed"):
                continue
            self.k = k
            return self._start()
        if res == "next":
            self.tv.stop()
        self._finish("failed", "Nothing else in the list can be played.")

    # -- watching the TV (about once a second)
    def _poll(self):
        st, pos, d, uri = self.tv.state()
        self.st = st
        c = self.cur
        if st == "":
            self.errors += 1
            if c and self.errors >= LOST_AFTER:
                self._finish("lost", "The TV is not answering any more (is it off?).", "warning")
            return
        self.errors, self.pos, self.uri = 0, pos, uri
        self.dur = d or (c["dur"] if c else 0.0)
        if not c:
            return
        if d:
            c["dur"] = d
            if not c["length_saved"] and not self.now.get("remote") and same_url(uri, c["url"]):
                c["length_saved"] = True
                self.now["dur"] = d
                library.remember_length(self.now, d)
        now = time.time()
        # somebody started something else on the TV: leave it alone
        if c["started"] and uri and not same_url(uri, c["url"]):
            c["other"] += 1
            if c["other"] >= 2:
                self._finish("other", "Something else started playing on the TV - leaving it alone.")
            return
        c["other"] = 0
        if st == PLAYING:
            c["started"], c["stop_since"] = True, None
            if c["resume"] > RESUME_MIN and (not c["dur"] or c["resume"] < c["dur"] - RESUME_MIN):
                self.tv.seek(c["resume"])  # continue an interrupted session where it was
                c.update(last_pos=c["resume"], last_t=now, grace=now + SEEK_GRACE)
            c["resume"] = 0.0
            if now >= c["grace"]:
                c.update(last_pos=pos, last_t=now, was_playing=True)
        elif st == PAUSED:
            c["started"], c["stop_since"] = True, None
            if now >= c["grace"]:
                c.update(last_pos=pos, last_t=now, was_playing=False)
        elif st == LOADING:
            c["loading_seen"], c["stop_since"] = True, None
            if not c["started"] and now - c["t0"] > LOAD_GIVE_UP:
                self._failed('it stayed on "loading" for %d seconds' % (now - c["t0"]))
        elif st in HALTED:
            if c["started"]:
                if now < c["grace"]:
                    return  # our own restart/seek is still settling
                # where playback had got to: last seen position plus the time since (capped)
                reached = c["last_pos"] + (min(now - c["last_t"], 3 * POLL) if c["was_playing"] else 0.0)
                if c["dur"] and reached >= c["dur"] - END_SLACK:
                    return self._advance("ended")
                c["stop_since"] = c["stop_since"] or now
                if now - c["stop_since"] >= STOP_CONFIRM:
                    self._finish("viewer", "Playback was stopped on the TV.")
            else:
                waited = now - c["t0"]
                if c["loading_seen"] and waited > LOAD_MIN:
                    self._failed("it started loading and then gave up")
                elif waited > START_GIVE_UP:
                    self._failed("it never started")
                elif waited > START_RETRY and not c["replayed"]:
                    c["replayed"] = True
                    self.tv.play()
