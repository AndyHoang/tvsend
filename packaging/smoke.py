"""Check a built tvsend binary end to end against the fake TV from the tests.

    uv run python packaging/smoke.py dist/tvsend-<os>-<arch> [VERSION]

The binary gets a throw-away config that points at a fake TV on 127.0.0.1, then must:
report the version, show help, read the TV's state, play a clip to the end (the TV is
handed a link, and that link serves the very file), and stop the TV. Exits 1 on the
first failure.
"""

import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

from fake_tv import FakeTV  # noqa: E402

from tvsend import config, discovery  # noqa: E402


def fail(text):
    print("FAILED: %s" % text)
    sys.exit(1)


def main():
    binary = os.path.abspath(sys.argv[1])
    version = sys.argv[2].lstrip("v") if len(sys.argv) > 2 else ""
    home = tempfile.mkdtemp(prefix="tvsend-smoke-")
    dirs = {"XDG_%s_HOME" % n: os.path.join(home, n.lower()) for n in ("CONFIG", "STATE", "CACHE")}
    env = dict(os.environ, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost", **dirs)
    os.environ.update(env)  # config.save() below writes into the same throw-away folders

    tv = FakeTV(duration=6.0, speed=1.0)  # real time, as a real TV plays
    found = discovery.describe(tv.location)
    if not found:
        fail("the fake TV did not answer")
    cfg = config.Config(check_updates=False)
    cfg.add_tv(
        config.TV(
            id=found.id,
            name=found.name,
            address="127.0.0.1",
            control_url=found.control_url,
            location=tv.location,
        ),
        make_default=True,
    )
    config.save(cfg)
    clip = os.path.join(home, "Sample Clip.mp4")
    content = os.urandom(64 * 1024)
    with open(clip, "wb") as f:
        f.write(content)

    def run(*args, expect=""):
        r = subprocess.run([binary, *args], env=env, capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        print("$ tvsend %s  (exit %d)\n%s\n" % (" ".join(args), r.returncode, out))
        if r.returncode != 0:
            fail("tvsend %s exited with %d" % (" ".join(args), r.returncode))
        if expect not in out:
            fail("tvsend %s did not print %r" % (" ".join(args), expect))
        return out

    run("--version", expect=version)
    run("--help", expect="tvsend status")
    run("status", expect="Test TV")

    # Play: while the binary runs, fetch the link the TV was handed, as the TV would.
    p = subprocess.Popen([binary, clip], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 30
    while not tv.loaded and time.time() < end and p.poll() is None:
        time.sleep(0.05)
    if not tv.loaded:
        p.kill()
        fail("the TV was never handed a link:\n%s" % p.communicate()[0])
    link = tv.loaded[0]
    with urllib.request.urlopen(link, timeout=10) as r:
        served = r.read()
    try:
        out = p.communicate(timeout=60)[0].strip()
    except subprocess.TimeoutExpired:
        p.kill()
        fail("playing did not finish within a minute")
    print("$ tvsend '%s'  (exit %d)\n%s\n" % (clip, p.returncode, out))
    if served != content:
        fail(
            "the link %s did not serve the clip (%d bytes instead of %d)" % (link, len(served), len(content))
        )
    if p.returncode != 0 or "Finished." not in out:
        fail("playing the clip did not end with 'Finished.'")

    run("stop", expect="stop")
    tv.close()
    print("OK: %s works end to end" % os.path.basename(binary))


if __name__ == "__main__":
    main()
