# tvsend

Send video files from your terminal to a TV on your home network: pick a clip from a
list, press Enter, and it plays on the TV.

<!-- TODO(owner): replace this line with the terminal recording (GIF) once it is recorded. -->
_Terminal recording: to be added._

## Install

tvsend is at an early test stage: there is no public release yet.

**From source** (works today; needs [uv](https://docs.astral.sh/uv/) and access to the
repository):

```sh
git clone git@github.com:AndyHoang/tvsend.git && cd tvsend
uv run tvsend
```

In the rest of this page, `tvsend` stands for `uv run tvsend` when you run from source.

**Standalone binary** (from the first public release on): one file with everything
inside, no Python needed, for Linux (x86_64, arm64) and macOS (Apple Silicon, Intel).

- Install script, which puts `tvsend` in `~/.local/bin`:

  ```sh
  curl -fsSL https://raw.githubusercontent.com/AndyHoang/tvsend/main/install.sh | sh
  ```

- Or take the file for your system from the
  [Releases page](https://github.com/AndyHoang/tvsend/releases), make it executable
  (`chmod +x tvsend`) and move it to a folder on your `PATH`. Each release lists
  SHA-256 checksums.

On macOS the binary is not signed. A file downloaded with a browser is blocked until
you clear the block once (the install script does not trigger this block):

```sh
xattr -d com.apple.quarantine tvsend
```

To update a binary later: `tvsend update`.

**Not in this version:** the background player. Closing tvsend stops the TV, and an
interrupted session is not continued; parts of this page that say otherwise describe
the plan. It comes in a later version, after first user feedback.

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
| `tvsend stop` | stop playback and end the background player |
| `tvsend status` | what the TV is doing, what is next |
| `tvsend setup` | run the setup steps again |
| `tvsend reset` | forget all settings and start fresh (your videos are not touched) |
| `tvsend tv` | list saved TVs, add one, choose the default |
| `tvsend doctor` | check TV reachability, file server and firewall; print a report |
| `tvsend update` | replace the binary with the newest release |
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
| `?` | show all keys |
| `q` | quit the list |

Good to know:

- The list shows name, size and date changed. A clip's length appears once the TV has
  played it, and is remembered.
- Videos in sub-folders are listed too. Hidden folders are skipped.
- The list refreshes by itself; files still being written are left out until they settle.
- The highlight follows the clip that is on the TV.
- Closing the list or the terminal does not stop the TV: a background player keeps the
  queue going. Open `tvsend` again to see what is playing and what is next.
  `s` or `tvsend stop` ends it.
- After an interruption (reboot, crash, TV switched off), opening `tvsend` continues the
  queue where it was. After a deliberate stop it does not.
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
  GitHub, at most once a day; `check_updates = false` in the config file turns it off.

Settings are kept in `~/.config/tvsend/config.toml`.

## Supported

- **Systems:** Linux and macOS.
- **TVs:** TVs that accept video over DLNA (most Samsung, LG, Sony and Philips smart TVs).
- **Files:** mp4, m4v, mov, mkv, webm, avi, ts. Whether a given file plays depends on
  the TV.
- **Links:** direct links to a video file (`http://` or `https://`).

Not supported:

- Windows.
- YouTube and other streaming-site links.
- Subtitles.
- AirPlay and Chromecast (not yet; the code is laid out so they can be added).

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
and the one port tvsend uses (8765 by default). Example for ufw, with a computer at
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

See [CONTRIBUTING.md](CONTRIBUTING.md) for more, and [SPEC.md](SPEC.md) for what the app
is meant to do.

## Licence

MIT. See [LICENSE](LICENSE).
