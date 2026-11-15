import os

import pytest

from tvsend import config, paths
from tvsend.config import TV, Config, ConfigError


def tv(n=1, name="Test TV"):
    return TV(
        id="uuid:tv-%d" % n,
        name=name,
        address="192.0.2.%d" % n,
        control_url="http://192.0.2.%d:9197/ctl" % n,
        location="http://192.0.2.%d:9197/desc.xml" % n,
    )


def test_missing_file_gives_defaults():
    cfg = config.load()
    assert cfg == Config()
    assert (cfg.folder, cfg.default_tv, cfg.port) == ("", "", 8765)
    assert (cfg.sort, cfg.loop, cfg.tvs) == ("name", True, [])
    assert cfg.tv() is None


def test_config_file_is_under_xdg_config_home(tmp_path):
    assert paths.config_file() == str(tmp_path / "config" / "tvsend" / "config.toml")


def test_round_trip():
    cfg = Config(folder="/home/someone/Videos", port=9000, sort="-size", loop=False, check_updates=False)
    cfg.add_tv(tv(1))
    cfg.add_tv(tv(2, 'Living "Room" TV — phòng khách \\ 50\'\tend'))
    config.save(cfg)
    assert os.path.isfile(paths.config_file())
    assert config.load() == cfg


def test_round_trip_keeps_odd_folder_names():
    cfg = Config(folder='/tmp/it\'s "my" clips/日本語 #1 = [x]')
    config.save(cfg)
    assert config.load().folder == cfg.folder


def test_broken_toml_raises():
    os.makedirs(paths.config_dir())
    with open(paths.config_file(), "w") as f:
        f.write("folder = [\n")
    with pytest.raises(ConfigError):
        config.load()


@pytest.mark.parametrize("port", ["80", "70000", '"8765"'])
def test_bad_port_raises(port):
    os.makedirs(paths.config_dir())
    with open(paths.config_file(), "w") as f:
        f.write("port = %s\n" % port)
    with pytest.raises(ConfigError):
        config.load()


def test_tv_without_required_fields_raises():
    os.makedirs(paths.config_dir())
    with open(paths.config_file(), "w") as f:
        f.write('[[tv]]\nname = "Half a TV"\n')
    with pytest.raises(ConfigError):
        config.load()


def test_unknown_settings_are_ignored():
    os.makedirs(paths.config_dir())
    with open(paths.config_file(), "w") as f:
        f.write(
            'folder = "/v"\nfrom_the_future = 1\n\n[[tv]]\nid = "x"\nname = "n"\naddress = "192.0.2.1"\n'
            'control_url = "http://192.0.2.1/c"\nshiny = true\n'
        )
    cfg = config.load()
    assert cfg.folder == "/v"
    assert cfg.tvs[0].id == "x" and cfg.tvs[0].backend == "dlna"


def test_add_tv_and_default():
    cfg = Config()
    cfg.add_tv(tv(1))
    assert cfg.default_tv == "uuid:tv-1"  # the first TV becomes the default
    cfg.add_tv(tv(2))
    assert cfg.default_tv == "uuid:tv-1"
    assert cfg.tv().id == "uuid:tv-1"
    assert cfg.tv("uuid:tv-2").id == "uuid:tv-2"
    assert cfg.tv("uuid:nope") is None
    cfg.add_tv(tv(2), make_default=True)
    assert cfg.default_tv == "uuid:tv-2"
    assert [t.id for t in cfg.tvs] == ["uuid:tv-1", "uuid:tv-2"]  # the same TV is replaced, not added twice


def test_add_tv_replaces_changed_address():
    cfg = Config()
    cfg.add_tv(tv(1))
    moved = tv(1)
    moved.address = "192.0.2.77"
    cfg.add_tv(moved)
    assert len(cfg.tvs) == 1 and cfg.tv().address == "192.0.2.77"


def test_default_falls_back_to_first_saved_tv():
    cfg = Config(default_tv="uuid:gone", tvs=[tv(3)])
    assert cfg.tv().id == "uuid:tv-3"


def test_default_video_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.default_video_folder() == ""
    (tmp_path / "Movies").mkdir()
    assert config.default_video_folder() == str(tmp_path / "Movies")
    (tmp_path / "Videos").mkdir()
    assert config.default_video_folder() == str(tmp_path / "Videos")
