import pytest
from conftest import wait_for

from tvsend import discovery
from tvsend.backends import open_tv
from tvsend.backends.base import HALTED, LOADING, PAUSED, PLAYING, STOPPED, State
from tvsend.backends.dlna import DlnaTV, clock_time, seconds
from tvsend.config import TV

URL = "http://192.0.2.10:8765/token/My%20Clip%20%26%20more.mp4"


@pytest.fixture
def tv(fake_tv):
    fake_tv.speed = 1.0  # real time: nothing ends during these tests
    return DlnaTV(discovery.describe(fake_tv.location))


def test_time_helpers():
    assert seconds("0:01:05") == 65 and seconds("1:00:00.5") == 3600.5
    assert seconds("") == 0 and seconds(None) == 0 and seconds("NOT_IMPLEMENTED") == 0
    assert clock_time(0) == "0:00:00" and clock_time(3725.9) == "1:02:05" and clock_time(-4) == "0:00:00"


def test_open_tv(fake_tv):
    described = discovery.describe(fake_tv.location)
    backend = open_tv(described)
    assert isinstance(backend, DlnaTV) and backend.name == "Test TV"
    described.backend = "smoke-signals"
    with pytest.raises(ValueError):
        open_tv(described)


def test_idle_tv(tv):
    st = tv.state()
    assert isinstance(st, State)
    assert st.state in HALTED and st.position == 0 and st.duration == 0 and st.uri == ""


def test_load_play_pause_seek_stop(tv, fake_tv):
    ok, _ = tv.load(URL, 'A "title" <with> & marks', "video/mp4")
    assert ok
    assert fake_tv.loaded == [URL]  # the URL arrives unchanged, '&' and all
    st = tv.state()
    assert (st.state, st.uri, st.duration) == (STOPPED, URL, 10.0)

    assert tv.play()[0]
    assert tv.state().state in (LOADING, PLAYING)
    assert wait_for(lambda: tv.state().state == PLAYING)
    assert wait_for(lambda: tv.state().position > 0)

    assert tv.pause()[0]
    paused = tv.state()
    assert paused.state == PAUSED
    assert tv.state().position == paused.position  # it really stands still

    assert tv.seek(7)[0]
    assert tv.state().position == 7.0
    assert tv.play()[0]  # resume
    assert wait_for(lambda: tv.state().state == PLAYING and tv.state().position > 7.0)

    assert tv.seek(0)[0]
    assert tv.state().position < 2.0

    assert tv.stop()[0]
    st = tv.state()
    assert (st.state, st.position, st.uri) == (STOPPED, 0.0, URL)
    assert fake_tv.actions[0] == "SetAVTransportURI" and "Seek" in fake_tv.actions


def test_refused_commands_report_failure(tv, fake_tv):
    assert tv.play()[0] is False  # nothing loaded
    assert tv.pause()[0] is False
    fake_tv.refuse.add("Clip")
    ok, why = tv.load(URL, "x", "video/mp4")
    assert ok is False and why
    assert fake_tv.loaded == [] and fake_tv.attempts == [URL]


def test_clip_runs_to_its_end(tv, fake_tv):
    fake_tv.speed = 50.0
    tv.load(URL, "x", "video/mp4")
    tv.play()
    assert wait_for(lambda: tv.state().state == PLAYING, timeout=1)
    assert wait_for(lambda: tv.state().state == STOPPED, timeout=2)


def test_tv_that_does_not_answer(fake_tv):
    described = discovery.describe(fake_tv.location)
    fake_tv.close()
    gone = DlnaTV(described)
    assert gone.state() == State("", 0.0, 0.0, "")
    assert gone.stop()[0] is False


def test_wrong_control_url_is_a_failure():
    nowhere = DlnaTV(TV(id="x", name="Nowhere", address="127.0.0.1", control_url="http://127.0.0.1:9/ctl"))
    assert nowhere.state().state == ""
    assert nowhere.load(URL, "x", "video/mp4")[0] is False
