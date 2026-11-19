# tvsend

[![CI](https://github.com/AndyHoang/tvsend/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AndyHoang/tvsend/actions/workflows/ci.yml)
[![Package check](https://github.com/AndyHoang/tvsend/actions/workflows/package.yml/badge.svg)](https://github.com/AndyHoang/tvsend/actions/workflows/package.yml)
[![Latest release](https://img.shields.io/github/v/release/AndyHoang/tvsend?include_prereleases&sort=semver)](https://github.com/AndyHoang/tvsend/releases/latest)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS-lightgrey)](#install)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Send video files from your terminal to a TV on your home network: pick a clip from a
list, press Enter, and it plays on the TV.

## Install

tvsend is a single file with everything inside; no Python needed. It runs on Linux
(x86_64, arm64) and macOS (Apple Silicon, Intel).

**Install script** - puts `tvsend` in `~/.local/bin` and checks the download against
the release's `SHA256SUMS`:

```sh
curl -fsSL https://raw.githubusercontent.com/AndyHoang/tvsend/main/install.sh | sh
```

To read the script before running it:

```sh
curl -fsSLO https://raw.githubusercontent.com/AndyHoang/tvsend/main/install.sh
less install.sh
sh install.sh
```

`TVSEND_INSTALL_DIR` picks another folder and `TVSEND_VERSION` a given version
(for example `TVSEND_VERSION=0.1.0 sh install.sh`). If the folder is not on your
`PATH`, the script says how to add it.

**By hand** - take the file for your system and `SHA256SUMS` from the
[Releases page](https://github.com/AndyHoang/tvsend/releases), check it, make it
executable and move it to a folder on your `PATH`:

```sh
shasum -a 256 -c SHA256SUMS --ignore-missing    # Linux: sha256sum -c --ignore-missing SHA256SUMS
xattr -d com.apple.quarantine tvsend-macos-arm64  # macOS only, see below
chmod +x tvsend-macos-arm64 && mv tvsend-macos-arm64 ~/.local/bin/tvsend
```

The checksum shows the file arrived intact; the binaries are not signed. That is why
macOS blocks a file downloaded with a browser until the `xattr` line above clears the
block (or allow it under System Settings -> Privacy & Security -> "Open Anyway"). The
install script does not trigger this block.

If macOS asks whether tvsend may find devices on your local network, allow it, or the
TV is not found.

To update later: `tvsend update`.

**From source** (needs [uv](https://docs.astral.sh/uv/)): see [Development](#development).

**Uninstall:** `tvsend reset --yes` forgets the settings, then remove the binary
(`rm ~/.local/bin/tvsend`).

## Quick start

1. Switch the TV on. It must be on the same home network as your computer.
2. Run `tvsend`.
3. The first run walks you through four steps:
   1. **Choose your TV.** TVs found on the network are listed by name.
   2. **Connection test.** tvsend checks that the TV can fetch a file from your
      computer. If a firewall blocks it, the exact command to allow it is shown and
      tvsend offers to run it.
   3. **Choose your video folder.**
   4. **Keys.** A short list of the keys you need.
4. Move to a clip with the arrow keys and press **Enter**. It plays on the TV, and the
   next clips follow by themselves.

To play one file without the list: `tvsend holiday.mp4`.

## Commands

| Command | What it does |
|---|---|
| `tvsend` | open the list (saved folder); the first run starts setup |
| `tvsend <dir>` | open the list for that folder only, for this run |
| `tvsend <file>...` | play the file(s) now |
| `tvsend <url>` | play a direct video link now |
| `tvsend stop` | stop playback on the TV |
| `tvsend status` | what the TV is playing, and where |
| `tvsend setup` | run the setup steps again |
| `tvsend reset` | forget all settings and start fresh (your videos are not touched); `--yes` skips the question |
| `tvsend tv` | list saved TVs, add one, choose the default |
| `tvsend doctor` | check TV reachability, file server and firewall; print a report |
| `tvsend update` | replace the binary with the newest release (binary installs only) |
| `tvsend --version`, `tvsend --help` | version, short help |

An argument is treated as a folder, a file or a link by looking at it. `tvsend <dir>`
saves nothing: plain `tvsend` always shows the saved folder. To open a folder that has
the same name as a command, write it as a path (`tvsend ./stop`).

## Keys in the list

| Key | What it does |
|---|---|
| Enter | play from the highlighted clip on down the list (with marked clips: play just those, in the order you marked them) |
| `n` / `b` | next / previous clip |
| `p` | pause / resume |
| `r` | restart the current clip |
| `s` | stop playback |
| `l` | switch between loop (default) and once |
| `o` | change the sort order; clicking a column header sorts by it too |
| `/` | filter by name (accents not needed); Enter keeps the filter, Esc clears it |
| Space | mark / unmark clips to play only those |
| `t` | switch to another saved TV |
| `f` | change the saved folder |
| Backspace | up one folder |
| `h` | back to the saved folder |
| `R` | refresh the list now |
| `j` / `k` | down / up |
| `?` | show all keys |
| `q` | quit the list |

Good to know:

- The list shows name, size and date changed. A clip's length appears once the TV has
  played it, and is remembered.
- Videos in sub-folders are listed too. Hidden folders are skipped.
- The list refreshes by itself; files still being written are left out until they settle.
- The highlight follows the clip that is on the TV.
- Playback needs tvsend open: closing the list stops the TV.
- If the TV refuses a file, tvsend says so and moves on to the next clip.

## How it works

- tvsend talks to the TV with DLNA, which most smart TVs support out of the box.
- It runs a small file server on your computer, bound to the single network address
  that faces the TV, never to all interfaces.
- The server hands out only the clips you queued, each under a random token. There is
  no folder listing.
- It does not use ffmpeg and does not look inside or convert files: the TV plays the
  file as it is.
- No telemetry. The only connection outside your home network is the update check to
  GitHub, at most once a day and only in the standalone binary; `check_updates = false`
  in the config file turns it off.

Settings are kept in `~/.config/tvsend/config.toml` (or under `$XDG_CONFIG_HOME`), on
macOS too. tvsend also keeps a little state in `~/.local/state/tvsend` and a cache in
`~/.cache/tvsend`.

## Supported

- **Systems:** Linux and macOS.
- **TVs:** TVs that accept video over DLNA, which most smart TVs do. Tested on Samsung;
  reports from other brands are welcome.
- **Files:** mp4, m4v, mov, mkv, webm, avi, ts. Whether a given file plays depends on
  the TV.
- **Links:** direct links to a video file (`http://` or `https://`).

Not supported:

- Windows.
- YouTube and other streaming-site links.
- Subtitles.
- Chromecast (planned) and AirPlay.
- Keeping the queue playing after tvsend closes (planned).

## Troubleshooting

Start with `tvsend doctor`: it checks each step and prints a report.

**The TV is not found.**
The TV must be switched on and on the same network as the computer; a guest Wi-Fi
network usually keeps devices apart. In the first setup step, press `r` to search
again or `m` to type the TV's address (for example `192.0.2.20`). Some TVs need
"allow connections from other devices" (or a similar setting) turned on.

**The connection test fails or the clip never starts.**
A firewall on your computer is probably blocking the TV. `tvsend setup` and
`tvsend doctor` show the exact command for your firewall, limited to the TV's address
and the one port tvsend uses (8765 by default). The macOS firewall works per program
rather than per address, so there the command allows tvsend itself. Example for ufw, with a computer at
`192.0.2.10` and a TV at `192.0.2.20`:

```sh
sudo ufw allow from 192.0.2.20 to 192.0.2.10 port 8765 proto tcp
```

**The TV refuses a file.**
tvsend sends the file as it is, and TVs differ in what they can play. mp4 files with
H.264 video and AAC audio play on nearly every TV. If a file is refused, convert it
with a tool of your choice, or try another file to confirm the connection works.

**The picture freezes or stutters.**
The file is too heavy for the TV's network connection, which is common on Wi-Fi with
large files. Use a network cable for the TV, or a smaller version of the file.

**The TV got a new address.**
tvsend recognises a saved TV by its device ID and finds it again by itself. If the
computer's address changed and you added a firewall rule, update the rule.

## Development

The project uses [uv](https://docs.astral.sh/uv/) and Python 3.10 or newer.

```sh
git clone https://github.com/AndyHoang/tvsend
cd tvsend
uv sync               # create the environment
uv run tvsend         # run from source
uv run pytest         # tests (they use a fake TV, no device needed)
uv run ruff check     # lint
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more, [SPEC.md](SPEC.md) for what the app is
meant to do, and [MILESTONES.md](MILESTONES.md) for what comes next. Report security
problems as described in [SECURITY.md](SECURITY.md); everyone taking part follows the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Licence

MIT. See [LICENSE](LICENSE).
