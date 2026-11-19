# tvsend - milestones

Updated 2026-11-19. `SPEC.md` holds the decisions; this file holds the work, milestone by
milestone, in planned order. Tick a box when the work is merged and checked, and add new
items at the bottom of the right section. When every box of a milestone is ticked, note
the release it shipped in under its heading.

## Milestone 1: version 1 (in progress)

### In progress

- [ ] Check on a real Mac: Local Network permission, the "accept incoming connections"
      window, the firewall apply step in setup, folder-access prompts

### To do: app

- [ ] Play a real clip on a real TV from the new app, on Linux and on macOS
      (so far only a fake TV has been played to)
- [ ] `doctor` says "everything tvsend needs is working" when the connection test was
      skipped because the port was busy; it should say the test did not run
- [ ] Firewall rule covers TCP only; discovery answers (UDP) stay blocked by ufw, so
      finding the TV relies on the address-by-address fallback. Decide: widen the
      rule to UDP from the TV, or keep the fallback only
- [ ] Confirm the description addresses for Sony and Panasonic TVs (only Samsung is
      confirmed); collect more brands from user reports (LG, Philips, TCL, Hisense)
- [ ] Closing the file server takes about half a second; shorten it
- [ ] Remove `tvsend`'s old neighbour from the port: the personal tool's server still
      holds port 8765 on the development machine

- [ ] Scanning a very large folder (for example after going up to the home folder)
      freezes the list once; scan in the background or cap it
- [ ] In the TV switcher, "no, leave it playing" cannot hold: the old TV stops when
      the list reopens for the new one. Remove the question or make it true

### To do: tests (postponed on purpose)

- [ ] Tests for `cli.py`, `plain.py`, the list, the wizard, `doctor`, `firewall`,
      `update` and the background player
- [ ] A test run on Python 3.13 locally before each push (a 3.13-only bug got through
      once: a method named `_handle` on a thread class)

### To do: release

- [ ] Try the released binaries on real machines: macOS Apple Silicon, macOS Intel,
      Linux arm64 (all four build and start on GitHub's machines; only Linux x86_64
      was also started locally)
- [ ] Record the terminal demo and put it at the top of the README
- [ ] Release 0.1.1 with the macOS update fix (`tvsend update` in 0.1.0 cannot reach
      GitHub on macOS, so 0.1.0 users there must reinstall with `install.sh`)
- [ ] Run the Package check workflow once on GitHub and fix what it finds (the Homebrew
      job has not run anywhere yet), then download its binaries and try them on real
      machines

## Milestone 2: Chromecast, subtitles, distribution

Each part ships on its own; tick in any order.

### Chromecast

- [ ] Decide how to speak the Cast protocol while keeping Textual the only runtime
      dependency: write the small part needed (TLS on port 8009, the CastMessage
      framing, the media channel) with the standard library, or accept a dependency
- [ ] Find Chromecasts with mDNS (`_googlecast._tcp`) next to the SSDP search; show both
      kinds in `tvsend tv` and the setup wizard
- [ ] `backends/chromecast.py` behind `backends/base`: load, play, pause, seek, stop,
      state, so the player and the list need no Cast-specific code
- [ ] `doctor` and the connection test cover a Chromecast
- [ ] Check on a real Chromecast (only a fake device can be used in tests)

### Subtitles

- [ ] Pick up a subtitle file next to the video with the same name (`.srt`, `.vtt`,
      also `name.<lang>.srt`) and serve it from the file server
- [ ] DLNA: hand it to the TV (`CaptionInfo.sec` header and the subtitle entry in the
      DIDL-Lite metadata); confirm on a real Samsung TV which form it reads
- [ ] Chromecast: send it as a WebVTT track, turning `.srt` into WebVTT in Python
      (no ffmpeg, so subtitles inside the video file stay out of scope)
- [ ] Show in the list which clips have subtitles

### Distribution

- [ ] Homebrew: create the tap repository, publish the formula from
      `packaging/homebrew` on each release (job in the release workflow), add the
      install line to the README
- [ ] AUR `tvsend-bin`: only once people use tvsend and ask for it, since it has to be
      submitted to and maintained on the AUR (the template in `packaging/aur` is ready)
- [ ] `tvsend update` points to the package manager when installed through one
- [ ] Decide on other channels (PyPI for `uv tool install` / `pipx`, Nix, Scoop is
      out while Windows is unsupported); `SPEC.md` currently says no PyPI package

## Milestone 3: background player (waiting for user feedback)

Parked on the branch `wip/background-player` (unfinished, untested).

- [ ] Queue keeps playing after the list closes; `stop` and `status` go through it
- [ ] Saved session: continue automatically after an interruption, never after a
      deliberate stop

## Not planned yet

- AirPlay back-end
- Windows

## Done


- [x] Specification agreed (`SPEC.md`)
- [x] Core: config, discovery, DLNA, file server with random-token links, player, commands
- [x] Full-screen list with sort, filter, marks, help
- [x] Setup wizard with connection test and firewall help; `tvsend doctor`
- [x] Build script, release workflow, install script, `tvsend update` (written;
      see "To do: release" for what has not run yet)
- [x] README, licence, changelog, community files, CI workflow
- [x] 92 tests against a fake TV (71 since the timing-based player tests were removed:
      they were flaky on CI and without a real TV they proved little)
- [x] Private repository `AndyHoang/tvsend` with the first test version
- [x] List keys: `f` choose folder, `Backspace` up, `h` saved folder, `t` switch TV
- [x] First release `v0.1.0` (private): four binaries and checksums published by the
      Release workflow
- [x] `tvsend reset`
- [x] Release flow: version script, tag-driven release workflow, build-only run by hand
- [x] Fix: player failed on Python 3.13 (`_thread._ThreadHandle object is not callable`)
- [x] README checked against the code for going public; contact address filled in
- [x] Repository public, private vulnerability reporting on; `install.sh` checked
      without a login
