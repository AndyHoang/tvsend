import os
import pathlib
import time

from conftest import make_video

from tvsend import library


def names(entries):
    return [e["name"] for e in entries]


def test_scan_is_recursive_and_sorted_by_name(videos):
    entries, notes = library.scan(videos)
    assert names(entries) == ["a.mp4", "b.mkv", os.path.join("sub", "c.mp4")]
    assert notes == []
    e = entries[0]
    assert e["path"] == os.path.join(videos, "a.mp4")
    assert e["size"] == 300 and e["dur"] == 0.0 and e["mtime"] == os.path.getmtime(e["path"])


def test_scan_lists_all_common_types(tmp_path):
    for ext in ("mp4", "m4v", "mov", "mkv", "webm", "avi", "ts", "MP4", "MkV"):
        make_video(tmp_path / ("clip_%s.%s" % (ext, ext)))
    for other in ("notes.txt", "song.mp3", "picture.jpg", "mp4", "clip.mp4.part"):
        make_video(tmp_path / other)
    entries, _ = library.scan(str(tmp_path))
    assert len(entries) == 9
    assert all(library.is_video(e["name"]) for e in entries)


def test_scan_skips_hidden_files_and_folders(videos, tmp_path):
    make_video(tmp_path / "videos" / ".hidden.mp4")
    make_video(tmp_path / "videos" / ".trash" / "old.mp4")
    make_video(tmp_path / "videos" / "sub" / ".cache" / "deep.mp4")
    assert names(library.scan(videos)[0]) == ["a.mp4", "b.mkv", os.path.join("sub", "c.mp4")]


def test_scan_skips_files_still_being_written(videos, tmp_path):
    make_video(tmp_path / "videos" / "rendering.mp4", age=0)
    make_video(tmp_path / "videos" / "settled.mp4", age=library.FRESH_SECONDS + 5)
    got = names(library.scan(videos)[0])
    assert "rendering.mp4" not in got and "settled.mp4" in got


def test_scan_does_not_follow_linked_folders(videos, tmp_path):
    outside = tmp_path / "outside"
    make_video(outside / "elsewhere.mp4")
    os.symlink(str(outside), os.path.join(videos, "link"))
    os.symlink(videos, os.path.join(videos, "sub", "loop"))  # would never end if followed
    assert names(library.scan(videos)[0]) == ["a.mp4", "b.mkv", os.path.join("sub", "c.mp4")]


def test_scan_missing_folder(tmp_path):
    entries, notes = library.scan(str(tmp_path / "nope"))
    assert entries == [] and len(notes) == 1 and "nope" in notes[0]


def test_scan_empty_folder(tmp_path):
    assert library.scan(str(tmp_path)) == ([], [])


def entry(name, size=1, mtime=0.0, dur=0.0):
    return {"path": "/v/" + name, "name": name, "size": size, "mtime": mtime, "dur": dur}


def test_sort_specs():
    es = [entry("b.mp4", 30, 300, 5.0), entry("Á.mp4", 10, 100, 0.0), entry("c.mp4", 20, 200, 9.0)]
    order = lambda spec: names(library.sort_entries(es, spec))  # noqa: E731
    assert order("name") == ["Á.mp4", "b.mp4", "c.mp4"]  # accents and case do not matter
    assert order("-name") == ["c.mp4", "b.mp4", "Á.mp4"]
    assert order("newest") == ["b.mp4", "c.mp4", "Á.mp4"]
    assert order("-newest") == ["Á.mp4", "c.mp4", "b.mp4"]
    assert order("size") == ["Á.mp4", "c.mp4", "b.mp4"]
    assert order("-size") == ["b.mp4", "c.mp4", "Á.mp4"]
    assert order("length") == ["b.mp4", "c.mp4", "Á.mp4"]  # unknown length goes last
    assert order("-length") == ["c.mp4", "b.mp4", "Á.mp4"]  # ... in both directions
    assert order("nonsense") == ["Á.mp4", "b.mp4", "c.mp4"]
    assert names(es) == ["b.mp4", "Á.mp4", "c.mp4"]  # the input list is left alone


def test_every_cycled_sort_has_a_description():
    assert all(s in library.SORT_TEXT for s in library.SORTS)


def test_fold():
    assert library.fold("Đám CƯỚI") == "dam cuoi"
    assert library.fold("cuoi") in library.fold("Lễ cưới 2024.mp4")
    assert library.fold("Ärger Straße") == "arger strasse"


def test_clock():
    assert library.clock(0) == "?" and library.clock(-3) == "?" and library.clock(None) == "?"
    assert library.clock(5) == "0:05"
    assert library.clock(59.6) == "1:00"
    assert library.clock(754) == "12:34"
    assert library.clock(3600) == "1:00:00"
    assert library.clock(3 * 3600 + 5 * 60 + 9) == "3:05:09"


def test_size_and_date_text():
    assert library.size_text(1_500_000) == "2 MB"
    assert library.size_text(2_500_000_000) == "2.5 GB"
    assert library.date_text(time.mktime((2026, 1, 2, 3, 4, 0, 0, 0, -1))) == "2026-01-02 03:04"


def test_fit_and_wid():
    assert library.fit("abc", 6) == "abc   "
    assert library.fit("abcdefgh", 5) == "abcd…"
    assert library.wid("日本") == 4
    assert library.wid(library.fit("日本語の動画", 7)) == 7
    assert library.wid("é") == 1  # a combining accent takes no column


def test_is_url_and_url_entry():
    assert library.is_url("http://192.0.2.1/a.mp4") and library.is_url("https://example.org/x")
    assert not library.is_url("/home/x/http.mp4") and not library.is_url("ftp://example.org/a.mp4")
    e = library.url_entry("https://example.org/films/My%20Clip.mp4?token=1")
    assert e["name"] == "My Clip.mp4" and e["remote"] is True and e["path"].startswith("https://")
    assert library.url_entry("http://example.org")["name"] == "http://example.org"


def test_remembered_lengths(videos):
    entries, _ = library.scan(videos)
    a = entries[0]
    library.remember_length(a, 83.5)
    again = {e["name"]: e for e in library.scan(videos)[0]}
    assert again["a.mp4"]["dur"] == 83.5
    assert again["b.mkv"]["dur"] == 0.0


def test_remembered_length_is_dropped_when_the_file_changes(videos):
    a = library.scan(videos)[0][0]
    library.remember_length(a, 83.5)
    make_video(pathlib.Path(a["path"]), size=999, age=120)
    assert library.scan(videos)[0][0]["dur"] == 0.0


def test_remember_length_ignores_nonsense(videos):
    a = library.scan(videos)[0][0]
    library.remember_length(a, 0)
    library.remember_length(a, -1)
    library.remember_length(library.url_entry("http://192.0.2.1/a.mp4"), 50)
    assert library.load_lengths() == {}
