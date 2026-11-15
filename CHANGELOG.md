# Changelog

All notable changes to tvsend are written here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-15

First version.

### Added

- Full-screen list of the videos in a folder and its sub-folders: Enter plays from the
  highlighted clip on down the list, in loop or once mode.
- Sort, filter by name, next / previous, pause, restart, stop, and marking clips to
  play only those.
- `tvsend <dir>` to open another folder for one run, `tvsend <file>...` to play files
  at once, `tvsend <url>` to play a direct video link.
- TVs are found on the home network by themselves (DLNA). Several TVs can be saved; a
  saved TV is recognised by its device ID when its address changes.
- First-run setup in four steps: choose the TV, connection test with firewall help,
  choose the video folder, key overview. `tvsend setup` repeats it; `tvsend reset`
  forgets all settings.
- In the list: `f` chooses a folder, `Backspace` goes up one folder, `h` returns to the
  saved folder, `t` switches TV.
- `tvsend doctor` checks TV reachability, the file server and the firewall.
- File server bound to one network address, serving only queued files under random
  tokens.
- File types: mp4, m4v, mov, mkv, webm, avi, ts.
- Standalone binaries for Linux (x86_64, arm64) and macOS (Apple Silicon, Intel),
  install script, `tvsend update`.

[Unreleased]: https://github.com/AndyHoang/tvsend/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AndyHoang/tvsend/releases/tag/v0.1.0
