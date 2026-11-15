# tvsend - task list

Updated 2026-11-15. `SPEC.md` holds the decisions; this file holds what is left to do.
Tick a box when the work is merged and checked, and add new items at the bottom of
the right section.

## In progress

- [ ] Check on a real Mac: Local Network permission, the "accept incoming connections"
      window, the firewall apply step in setup, folder-access prompts

## To do: app

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

## Later milestone: background player (waiting for user feedback)

Parked on the branch `wip/background-player` (unfinished, untested).

- [ ] Queue keeps playing after the list closes; `stop` and `status` go through it
- [ ] Saved session: continue automatically after an interruption, never after a
      deliberate stop

## To do: tests (postponed on purpose)

- [ ] Tests for `cli.py`, `plain.py`, the list, the wizard, `doctor`, `firewall`,
      `update` and the background player
- [ ] A test run on Python 3.13 locally before each push (a 3.13-only bug got through
      once: a method named `_handle` on a thread class)

## To do: release

- [ ] Build and try the macOS binaries (Apple Silicon and Intel) and Linux arm64;
      only Linux x86_64 has been built
- [ ] First run of the release workflow with a `v0.1.0` tag
- [ ] Create the Homebrew tap repository and its token secret
- [ ] Create the AUR package `tvsend-bin` and its SSH key secret
- [ ] Record the terminal demo and put it at the top of the README
- [ ] Rewrite the README parts that describe the background player as available, and
      remove the "first test version" note
- [ ] Fill in the contact address in `CODE_OF_CONDUCT.md`
- [ ] Set the `0.1.0` date in `CHANGELOG.md`
- [ ] Switch the repository to public; then turn on private vulnerability reporting
      (needed by `SECURITY.md`) and check that `install.sh` and `tvsend update` work
      without a login

## Later, not planned for version 1

- AirPlay and Chromecast back-ends
- Windows
- Subtitles

## Done

- [x] Specification agreed (`SPEC.md`)
- [x] Core: config, discovery, DLNA, file server with random-token links, player, commands
- [x] Full-screen list with sort, filter, marks, help
- [x] Setup wizard with connection test and firewall help; `tvsend doctor`
- [x] Build script, release workflow, install script, `tvsend update` (written;
      see "To do: release" for what has not run yet)
- [x] README, licence, changelog, community files, CI workflow
- [x] 92 tests against a fake TV
- [x] Private repository `AndyHoang/tvsend` with the first test version
- [x] List keys: `f` choose folder, `Backspace` up, `h` saved folder, `t` switch TV
- [x] Fix: player failed on Python 3.13 (`_thread._ThreadHandle object is not callable`)
