"""Finding the video files in a folder, and sorting, filtering and describing them."""

import os
import time
import unicodedata

from . import paths

VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".ts")
FRESH_SECONDS = 15  # a file changed this recently is probably still being written

SORTS = ["name", "newest", "-size", "-length"]  # what the o key cycles through
SORT_TEXT = {
    "name": "name (A-Z)",
    "-name": "name (Z-A)",
    "newest": "newest first",
    "-newest": "oldest first",
    "size": "size, smallest first",
    "-size": "size, largest first",
    "length": "length, shortest first",
    "-length": "length, longest first",
}


# ---------------------------------------------------------------- text helpers
def wid(s: str) -> int:
    return sum(
        0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s
    )


def fit(s: str, w: int) -> str:
    """Cut or pad s to exactly w terminal columns."""
    if wid(s) > w:
        out = ""
        for c in s:
            if wid(out + c) > w - 1:
                break
            out += c
        s = out + "…"
    return s + " " * (w - wid(s))


def fold(s: str) -> str:
    """Lowercase and strip accents, so typing 'cuoi' finds 'cưới'."""
    s = unicodedata.normalize("NFD", s.casefold()).replace("đ", "d")
    return "".join(c for c in s if not unicodedata.combining(c))


def clock(sec: float) -> str:
    if not sec or sec < 0:
        return "?"
    sec = int(round(sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def size_text(n: int) -> str:
    return "%.1f GB" % (n / 1e9) if n >= 1e9 else "%.0f MB" % (n / 1e6)


def date_text(mtime: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))


def is_video(name: str) -> bool:
    return name.lower().endswith(VIDEO_EXTS)


def is_url(text: str) -> bool:
    return text.startswith(("http://", "https://"))


# ---------------------------------------------------------------- remembered clip lengths
# tvsend does not look inside files. A clip's length is learned from the TV the first
# time it plays and remembered here.
def _lengths_file() -> str:
    return os.path.join(paths.cache_dir(), "lengths.json")


def load_lengths() -> dict:
    return paths.read_json(_lengths_file())


def remember_length(entry: dict, seconds: float) -> None:
    if seconds <= 0 or not entry.get("size"):
        return
    data = load_lengths()
    data[entry["path"]] = [entry["size"], entry["mtime"], seconds]
    paths.write_json(_lengths_file(), data)


def _length(entry: dict, lengths: dict) -> float:
    hit = lengths.get(entry["path"])
    if isinstance(hit, list) and len(hit) == 3 and hit[0] == entry["size"] and hit[1] == entry["mtime"]:
        return float(hit[2])
    return 0.0


# ---------------------------------------------------------------- entries
def make_entry(path: str, name: str | None = None) -> dict:
    st = os.stat(path)
    return {
        "path": path,
        "name": name or os.path.basename(path),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "dur": 0.0,
    }


def url_entry(url: str) -> dict:
    import urllib.parse

    name = urllib.parse.unquote(os.path.basename(urllib.parse.urlsplit(url).path)) or url
    return {"path": url, "name": name, "size": 0, "mtime": 0.0, "dur": 0.0, "remote": True}


def being_written(path: str) -> bool:
    try:
        return time.time() - os.path.getmtime(path) < FRESH_SECONDS
    except OSError:
        return True


def scan(folder: str) -> tuple[list[dict], list[str]]:
    """All video files in the folder and its sub-folders, sorted by name. Returns (entries, notes).

    Hidden files and folders (dot names) are skipped, linked folders are not followed, and
    files still being written are left out until they settle."""
    notes: list[str] = []
    entries: list[dict] = []
    if not os.path.isdir(folder):
        return [], ["folder not found: %s" % folder]
    lengths = load_lengths()

    def failed(err):
        notes.append("cannot read %s" % err.filename)

    for root, dirs, files in os.walk(folder, onerror=failed, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for n in files:
            if n.startswith(".") or not is_video(n):
                continue
            p = os.path.join(root, n)
            if not os.path.isfile(p) or being_written(p):
                continue
            try:
                e = make_entry(p, os.path.relpath(p, folder))
            except OSError:
                continue
            e["dur"] = _length(e, lengths)
            entries.append(e)
    return sort_entries(entries, "name"), notes


def sort_entries(entries: list[dict], spec: str = "name") -> list[dict]:
    """Entries in the wanted order. Clips whose length is not known yet go last."""
    field, rev = spec.lstrip("-"), spec.startswith("-")
    by_name = sorted(entries, key=lambda e: (fold(e["name"]), e["path"]))
    if field == "name":
        return by_name[::-1] if rev else by_name
    if field == "newest":
        return sorted(by_name, key=lambda e: e["mtime"], reverse=not rev)
    key = {"length": "dur", "size": "size"}.get(field)
    if not key:
        return by_name
    known = sorted([e for e in by_name if e[key]], key=lambda e: e[key], reverse=rev)
    return known + [e for e in by_name if not e[key]]
