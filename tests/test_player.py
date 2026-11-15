import queue
import urllib.request

import pytest
from conftest import wait_for

from tvsend import discovery, library
from tvsend.backends.base import PAUSED, PLAYING
from tvsend.backends.dlna import DlnaTV
from tvsend.player import Controller, same_url, url_name


@pytest.fixture
def clips(videos):
    return library.scan(videos)[0]  # a.mp4, b.mkv, sub/c.mp4


@pytest.fixture
def ctrl(fake_tv, server):
    c = Controller(DlnaTV(discovery.describe(fake_tv.location)), server)
    c.start()
    yield c
    c.send("close")
    c.join(5)
    assert not c.is_alive()


def messages(ctrl):
    out = []
    while True:
        try:
            out.append(ctrl.events.get_nowait())
        except queue.Empty:
            return out


def ended(ctrl, timeout=8.0):
    return wait_for(lambda: ctrl.view()["ended"], timeout)


def test_url_helpers():
    assert same_url("http://h/a%20b.mp4", "http://h/a b.mp4")
    assert not same_url("http://h/a.mp4", "http://h/b.mp4") and same_url("", None)
    assert url_name("http://192.0.2.1:8765/tok/My%20Clip.mp4") == "My Clip.mp4"


def test_two_clips_once(ctrl, fake_tv, server, clips):
    ctrl.send("loop", False)
    ctrl.send("play", clips[:2], 0)
    assert ended(ctrl) == "finished"
    assert ctrl.ended == "finished"
    assert fake_tv.loaded == [server.add(clips[0]["path"]), server.add(clips[1]["path"])]
    assert fake_tv.loaded[0].endswith("/a.mp4") and fake_tv.loaded[1].endswith("/b.mkv")
    # what the TV was told to fetch really is the file
    with urllib.request.urlopen(fake_tv.loaded[0], timeout=5) as r:
        assert r.read() == open(clips[0]["path"], "rb").read()
    v = ctrl.view()
    assert v["item"] is None and v["n"] == 0
    assert ("info", "Finished.") in messages(ctrl)


def test_view_while_playing(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("loop", False)
    ctrl.send("play", clips, 1)  # start from the second clip
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING and ctrl.view()["pos"] > 0)
    v = ctrl.view()
    assert v["item"]["path"] == clips[1]["path"]
    assert (v["k"], v["n"], v["loop"], v["ended"], v["dur"]) == (1, 3, False, None, 10.0)
    assert same_url(v["uri"], fake_tv.loaded[0])


def test_loop_wraps_around(ctrl, fake_tv, clips):
    ctrl.send("loop", True)
    ctrl.send("play", clips[:2], 0)
    assert wait_for(lambda: len(fake_tv.loaded) >= 5, timeout=10)
    assert ctrl.view()["ended"] is None
    first, second = fake_tv.loaded[0], fake_tv.loaded[1]
    assert fake_tv.loaded[:5] == [first, second, first, second, first]
    ctrl.send("stop")
    assert ended(ctrl) == "stopped"


def test_stop(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("play", clips, 0)
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING)
    ctrl.send("stop")
    assert ended(ctrl) == "stopped"
    assert fake_tv.snapshot()[0] == "STOPPED"
    assert len(fake_tv.loaded) == 1  # the queue did not move on
    assert ("info", "Stopped.") in messages(ctrl)


def test_viewer_presses_stop_on_the_tv(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("play", clips, 0)
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING and ctrl.view()["pos"] > 0)
    fake_tv.press_stop()
    assert ended(ctrl) == "viewer"
    assert len(fake_tv.loaded) == 1


def test_something_else_starts_on_the_tv(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("play", clips, 0)
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING and ctrl.view()["pos"] > 0)
    fake_tv.play_other()
    assert ended(ctrl) == "other"
    assert fake_tv.snapshot()[0] == "PLAYING"  # the other video is left alone
    assert "Stop" not in fake_tv.actions


def test_pause_and_resume_keep_the_queue(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("play", clips, 0)
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING)
    ctrl.send("pause")
    assert wait_for(lambda: ctrl.view()["st"] == PAUSED)
    assert wait_for(lambda: False, timeout=0.5) is False  # stay paused well past STOP_CONFIRM
    assert ctrl.view()["ended"] is None and ctrl.view()["item"]["path"] == clips[0]["path"]
    ctrl.send("pause")
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING)
    assert ctrl.view()["ended"] is None


def test_next_and_prev(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("loop", True)
    ctrl.send("play", clips, 0)
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING)
    ctrl.send("next")
    assert wait_for(lambda: len(fake_tv.loaded) == 2 and ctrl.view()["k"] == 1)
    assert fake_tv.loaded[1].endswith("/b.mkv")
    ctrl.send("prev")
    assert wait_for(lambda: len(fake_tv.loaded) == 3 and ctrl.view()["k"] == 0)
    ctrl.send("prev")  # wraps to the last clip
    assert wait_for(lambda: len(fake_tv.loaded) == 4 and ctrl.view()["k"] == 2)
    assert fake_tv.loaded[3].endswith("/c.mp4")
    assert ctrl.view()["ended"] is None


def test_next_at_the_end_in_once_mode_finishes(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("loop", False)
    ctrl.send("play", clips[:1], 0)
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING)
    ctrl.send("next")
    assert ended(ctrl) == "finished"
    assert fake_tv.snapshot()[0] == "STOPPED"


def test_restart(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("play", clips, 0)
    assert wait_for(lambda: ctrl.view()["pos"] >= 1.0, timeout=4)
    ctrl.send("restart")
    assert wait_for(lambda: "Seek" in fake_tv.actions)
    assert wait_for(lambda: ctrl.view()["pos"] < 1.0)
    assert ctrl.view()["ended"] is None and len(fake_tv.loaded) == 1


def test_refused_clip_is_reported_and_skipped(ctrl, fake_tv, clips):
    fake_tv.refuse.add("a.mp4")
    ctrl.send("loop", False)
    ctrl.send("play", clips[:2], 0)
    assert ended(ctrl) == "finished"
    assert len(fake_tv.loaded) == 1 and fake_tv.loaded[0].endswith("/b.mkv")
    assert fake_tv.attempts[0].endswith("/a.mp4")
    warnings = [text for level, text in messages(ctrl) if level == "warning"]
    assert len(warnings) == 1 and "could not play a.mp4" in warnings[0]


def test_nothing_playable(ctrl, fake_tv, clips):
    fake_tv.refuse.update(["a.mp4", "b.mkv"])
    ctrl.send("loop", True)  # must not spin forever
    ctrl.send("play", clips[:2], 0)
    assert ended(ctrl) == "failed"
    assert fake_tv.loaded == []


def test_clip_that_never_starts_is_given_up(ctrl, fake_tv, clips):
    fake_tv.never_start.add("a.mp4")
    ctrl.send("loop", False)
    ctrl.send("play", clips[:2], 0)
    assert ended(ctrl, timeout=12) == "finished"
    assert fake_tv.loaded[-1].endswith("/b.mkv")
    assert any("could not play a.mp4" in text for _, text in messages(ctrl))


def test_missing_file_is_skipped(ctrl, fake_tv, clips):
    gone = dict(clips[0], path=clips[0]["path"] + ".gone", name="gone.mp4")
    ctrl.send("loop", False)
    ctrl.send("play", [gone, clips[1]], 0)
    assert ended(ctrl) == "finished"
    assert len(fake_tv.loaded) == 1 and fake_tv.loaded[0].endswith("/b.mkv")
    assert any("could not play gone.mp4" in text for _, text in messages(ctrl))


def test_empty_queue(ctrl):
    ctrl.send("play", [], 0)
    assert ended(ctrl) == "failed"
    ctrl.send("next")
    assert wait_for(lambda: any("Nothing is queued" in t for _, t in messages(ctrl)))


def test_link_is_handed_to_the_tv_unchanged(ctrl, fake_tv):
    link = "http://192.0.2.50/films/Some%20Clip.mp4"
    ctrl.send("loop", False)
    ctrl.send("play", [library.url_entry(link)], 0)
    assert ended(ctrl) == "finished"
    assert fake_tv.loaded == [link]
    assert library.load_lengths() == {}  # nothing is remembered for links


def test_learned_length_is_remembered(ctrl, fake_tv, clips, videos):
    assert clips[0]["dur"] == 0.0
    ctrl.send("loop", False)
    ctrl.send("play", clips[:1], 0)
    assert ended(ctrl) == "finished"
    assert library.load_lengths()[clips[0]["path"]][2] == 10.0
    again = library.scan(videos)[0]
    assert again[0]["dur"] == 10.0 and again[1]["dur"] == 0.0


def test_queue_follows_a_reordered_list(ctrl, fake_tv, clips):
    fake_tv.speed = 1.0
    ctrl.send("loop", False)
    ctrl.send("play", clips, 0)  # a, b, c - playing a
    assert wait_for(lambda: ctrl.view()["st"] == PLAYING)
    ctrl.send("queue", [clips[2], clips[0], clips[1]])  # now c, a, b
    assert wait_for(lambda: ctrl.view()["k"] == 1)
    assert len(fake_tv.loaded) == 1  # the clip on the TV was not interrupted
    ctrl.send("next")
    assert wait_for(lambda: len(fake_tv.loaded) == 2)
    assert fake_tv.loaded[1].endswith("/b.mkv")


def test_refill_brings_new_clips_each_round(fake_tv, server, clips):
    rounds = []

    def refill():
        rounds.append(1)
        return clips[:1] if len(rounds) == 1 else clips[1:2]

    c = Controller(DlnaTV(discovery.describe(fake_tv.location)), server, refill=refill)
    c.start()
    try:
        c.send("play", clips[:1], 0)
        assert wait_for(lambda: len(fake_tv.loaded) >= 3, timeout=10)
        assert [u.rsplit("/", 1)[1] for u in fake_tv.loaded[:3]] == ["a.mp4", "a.mp4", "b.mkv"]
    finally:
        c.send("stop")
        c.send("close")
        c.join(5)


def test_tv_switched_off(fake_tv, server, clips):
    c = Controller(DlnaTV(discovery.describe(fake_tv.location)), server)
    c.start()
    try:
        fake_tv.speed = 1.0
        c.send("play", clips, 0)
        assert wait_for(lambda: c.view()["st"] == PLAYING)
        fake_tv.close()
        assert wait_for(lambda: c.view()["ended"], timeout=10) == "lost"
        assert c.view()["st"] == ""
    finally:
        c.send("close")
        c.join(5)
