# tvsend - specification

Status: agreed, 2026-11-15. All decisions below were made in the planning conversation.

## 1. What it is

`tvsend` is a terminal app that sends video files from a computer to a TV on the same
home network. You pick a clip from a full-screen list, press Enter, and it plays on
the TV; the next clips follow by themselves.

It is the public version of a personal script (`tv`, about 1,900 lines, one file,
Samsung TV address hard-coded). The public app keeps the list, the queue and the
keys, and replaces everything that was specific to one home.

Goal for a first-time user: download one file, run it, and have a clip playing on
the TV in under two minutes without reading documentation.

## 2. Decisions

| Topic | Decision |
|---|---|
| Name, command, repo | `tvsend`, `github.com/AndyHoang/tvsend` |
| Licence | MIT |
| Repo visibility | Private until the first release is tested, then public |
| Distribution | Standalone binary only (Python bundled). No PyPI package |
| Platforms | Linux and macOS. Windows: not supported, not tested |
| Binary targets | Linux x86_64, Linux arm64, macOS Apple Silicon, macOS Intel |
| Python (source) | 3.10 and newer |
| TV protocol | DLNA in version 1. Code is split so AirPlay and Chromecast can be added as back-ends later |
| ffmpeg / ffprobe | Not used at all. No "Will the TV play it?" check, no convert |
| File types listed | mp4, m4v, mov, mkv, webm, avi, ts. Played as requested; if the TV refuses a file, the app says so and moves on |
| Personal rules | Removed: raw-camera hiding (`TN_*`, above 60 Mbps), "risky" skipping, `tmp_` prefix. Kept: files still being written are not listed |
| TV selection | Found automatically on the network; several TVs can be saved and switched; typing an address is the fallback |
| Folder | Plain `tvsend` shows the saved folder. First run asks for it. Stored under `~/.config/tvsend/` |
| `tvsend <dir>` | Shows only that folder, for this run. Saves nothing |
| `tvsend <file>...` | Plays at once on the saved TV, no list. Several files form a queue |
| `tvsend <url>` | Plays a direct video link (plain http(s) video file; not YouTube or similar sites) |
| Persistence | Background player keeps the queue running after the app closes, plus a saved session |
| Reopen with a saved session, nothing playing | Continues the saved queue automatically, unless playback was stopped on purpose |
| Deliberate stop | `s`, `tvsend stop` or Stop on the remote clears the saved session |
| Saved folders | One |
| Sub-folders | Videos in sub-folders of the folder are listed too |
| macOS testing | Done by the author on their own Mac before each release |
| macOS signing | Unsigned (no Apple developer certificate) |
| Subtitles | Not planned |
| Onboarding | Full-screen 4-step wizard on first run; `tvsend setup` repeats it |
| Firewall | Tested during setup. If blocked: show the exact command and, in first-time setup, offer to run it |
| Install channels | GitHub Releases, install script, `tvsend update`, Homebrew tap, AUR `tvsend-bin` |
| Repo standards | README with demo and release automation first; CI, tests and community files in a later phase |

## 3. Commands

```
tvsend                    open the list (saved folder); first run starts setup
tvsend <dir>              open the list for that folder only, this run
tvsend <file>...          play the file(s) now
tvsend <url>              play a direct video link now
tvsend stop               stop playback and end the background player
tvsend status             what the TV is doing, what is next
tvsend setup              run the setup wizard again
tvsend tv                 list saved TVs, add one, choose the default
tvsend doctor             check TV reachability, file server, firewall; print a report
tvsend update             replace the binary with the newest release
tvsend --version / --help
```

An argument is treated as a folder, a file or a link by looking at it; there is no
`play` sub-command to learn.

## 4. First run: the setup wizard

Shown when no config exists. Each step has Back / Next; `q` leaves without saving.

1. **Choose your TV.** The network is searched (SSDP) and TVs are listed by name and
   address. `r` searches again, `m` types an address by hand. Nothing found: a short
   list of likely reasons (TV off, different Wi-Fi, guest network).
2. **Connection test.** tvsend starts its file server and asks the TV to fetch a tiny
   test file.
   - Works: shown as passed, continue.
   - Blocked: the firewall in use is detected (ufw, firewalld, macOS application
     firewall) and the exact command is shown, limited to the TV's address and the
     one port. "Apply now?" runs it with `sudo`; declining keeps the command on screen
     to copy. The test can be repeated.
3. **Choose your video folder.** A folder tree plus a path field with Tab completion.
   `~/Videos` (Linux) or `~/Movies` (macOS) is preselected when it exists.
4. **Keys.** Six lines: Enter play, `n`/`b` next/previous, `p` pause, `s` stop,
   `/` filter, `?` all keys. Then the list opens.

## 5. The main list

- Columns: name, size, date changed. Length is shown for a clip once the TV has
  reported it (remembered afterwards).
- Enter plays from the highlighted clip down the list; loop mode (default) starts
  again from the top, once mode stops at the bottom.
- Kept from the personal tool: sort (`o` and column headers), filter (`/`),
  next/previous, restart, pause, stop, loop/once, marking clips with Space, automatic
  refresh of the folder, highlight follows the TV.
- New: `t` switch TV, `f` change the saved folder, `?` key help, a status line that
  always names the TV in use.
- A clip the TV refuses: one plain message with the TV's answer, then the next clip.

## 6. Persistence

- **Background player.** A separate process started by the first play. It owns the
  queue, talks to the TV and runs the file server. The list (TUI) and the shell
  commands are clients of it over a local socket. Closing the app or the terminal
  does not stop the queue. It exits when playback is stopped or the queue ends in
  once mode.
- **Saved session.** Queue, current clip, position, loop mode, sort and TV are written
  to disk while playing. After an interruption (reboot, crash, TV switched off),
  opening `tvsend` with nothing playing continues from there automatically. A
  deliberate stop clears the saved session, so the TV never starts unasked after it.
- Opening the app while the background player runs shows exactly what is playing and
  what comes next.

## 7. Files on disk

| Path | Content |
|---|---|
| `~/.config/tvsend/config.toml` | saved TVs, default TV, folder, port, settings |
| `~/.local/state/tvsend/session.json` | saved session |
| `~/.local/state/tvsend/player.sock`, `player.log` | background player |
| `~/.cache/tvsend/` | remembered clip lengths, update check time |

`XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME` are honoured. The same paths
are used on macOS.

## 8. Technical design

- **Layout:** a package `src/tvsend/` instead of one file:
  `cli`, `config`, `discovery` (SSDP), `backends/base` + `backends/dlna`, `server`,
  `player` (background process and queue), `ipc`, `library` (folder scan, sort,
  filter), `firewall`, `update`, `ui/` (wizard, list, dialogs).
- **Back-end interface:** `discover()`, `load(url, title)`, `play()`, `pause()`,
  `stop()`, `seek()`, `state()`. DLNA implements it with AVTransport SOAP calls, as
  today. The TV's control address is read from its device description instead of
  being hard-coded, and a saved TV is recognised by its device ID, so a new IP
  address does not break it.
- **File server:** binds to this computer's single LAN address facing the TV, never to
  all interfaces. It serves only files that were queued, each under a random token;
  no folder listing. This replaces the symlink-into-share-folder approach, so any
  folder works and nothing is created next to the user's files. Range requests and
  DLNA headers as today; content type by file extension.
- **Dependencies:** Textual (UI) only; everything else is the standard library.
- **Build:** PyInstaller one-file binary per target, built by GitHub Actions on a
  version tag, with SHA-256 checksums.
- **Update:** `tvsend update` downloads the release for this platform, verifies the
  checksum and replaces the binary. The app checks for a new version at most once a
  day and shows one quiet line; `check_updates = false` turns it off. When installed
  by Homebrew or the AUR, `tvsend update` points to that package manager instead.
- **Privacy:** no telemetry. The only outside connection is the update check to
  GitHub.

- **Discovery behind a firewall.** Measured on the development machine: ufw drops the
  TV's answers to the network-wide search (SSDP), so the search alone finds nothing.
  Two measures: the search is sent from the tvsend port, so the one firewall rule can
  let the answers in; and when the search finds nothing, the description addresses
  used by known brands (Samsung confirmed; Sony and Panasonic listed, unconfirmed) are
  tried on the 254 neighbouring addresses of a private home network. Typing the TV's
  address tries the same list on that one address.
- **Development:** uv (`uv sync`, `uv run tvsend`, `uv run pytest`, `uv run ruff check`).

## 8a. Reference implementation

`reference/` holds a copy of the personal script this app was ported from (`tv.py`,
`tvserve.py`, its README). It is git-ignored and never published, because it contains
home addresses and names. What was taken from it:

| Reference | Here | Change |
|---|---|---|
| `Controller` (queue, end/stop detection, retries) | `player.py` | risky/raw/copy logic removed; learns clip lengths from the TV |
| `soap`, `tv_state`, `tv_set_uri` | `backends/dlna.py` | control address read from the TV's description, not hard-coded |
| `tvserve.py` | `server.py` | runs inside the app; random-token URLs instead of a share folder with symlinks |
| `scan`, `sort_entries`, text helpers | `library.py` | recursive; common video types; no ffprobe |
| `TvApp` (full-screen list) | `ui/app.py` | columns reduced to name, length, size, date; `?` help |
| `run_foreground`, `Keys` | `plain.py` | used by `tvsend <file>` |
| CONFIG block, `prefs.json` | `config.py` | `~/.config/tvsend/config.toml` |
| ffprobe cache, verdicts, convert, raw-file rules | - | dropped |

## 9. Phases

1. **Core.** Package layout, config, DLNA back-end with discovery, token file server,
   list UI without the personal rules, `tvsend <dir>` / `<file>` / `<url>`.
2. **Onboarding.** Setup wizard, connection test, firewall help, several TVs,
   `tvsend doctor`.
3. **Persistence.** Background player, local socket, saved session, automatic continue.
4. **Shipping.** PyInstaller builds, release workflow, install script, `tvsend update`,
   README with terminal recording, MIT licence, CHANGELOG. First private release,
   tested on Linux and macOS, then the repo goes public.
5. **Channels.** Homebrew tap and AUR `tvsend-bin`, updated by the release workflow.
6. **Project hygiene.** CI (ruff, pytest on Python 3.10-3.14, Linux and macOS, with a
   fake TV), CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue and PR templates.

## 10. Before the first commit

The personal script contains home IP addresses, the TV model and local folder paths.
None of these go into this repository: defaults come from discovery and the wizard,
and examples in the README use made-up names and addresses.

## 11. Notes on the later decisions

- **Sub-folders.** The scan is recursive. The list shows the path relative to the
  saved folder, hidden folders (names starting with a dot) are skipped, and symlinked
  folders are not followed, so a loop cannot occur.
- **Unsigned macOS binary.** A binary downloaded with a browser is blocked by
  Gatekeeper until the user allows it. The README recommends the install script or
  Homebrew, which do not trigger the block, and gives the one command that clears it
  for a manual download (`xattr -d com.apple.quarantine tvsend`).
- **Continue after an interruption only.** The saved session is kept when the
  background player ends without a stop request (reboot, crash, TV switched off or
  unreachable) and is cleared on any deliberate stop.

No open questions remain.
