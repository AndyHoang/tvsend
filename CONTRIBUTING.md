# Contributing to tvsend

Thank you for helping. Bug reports, reports about which TVs work, and code are all
welcome.

## Reporting a problem

Open an issue with the "Bug report" form. The most useful things to include are the
TV's brand and model, and the output of `tvsend doctor`.

If you only want to say "my TV works" or "my TV does not work", use the "TV report"
form. These reports build the list of supported TVs.

For security problems, see [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Setting up

You need [uv](https://docs.astral.sh/uv/). It fetches Python (3.10 or newer) and the
dependencies for you.

```sh
git clone https://github.com/AndyHoang/tvsend
cd tvsend
uv sync
uv run tvsend
```

## Before you open a pull request

```sh
uv run ruff check
uv run ruff format --check
uv run pytest
```

The tests use a fake TV, so no real device is needed. If you changed how tvsend talks
to a TV, please also say in the pull request which real TV you tried it on.

## Ground rules

- Read [SPEC.md](SPEC.md) first. It records what the app does and what it leaves out
  on purpose (no ffmpeg, no telemetry, no Windows support for now). Open an issue
  before working on something the spec excludes.
- Python 3.10 or newer. Do not add `from __future__ import annotations`.
- Runtime dependencies stay minimal: Textual, and the standard library for the rest.
- The file server must bind to one network address, never to all interfaces, and must
  serve only queued files.
- Examples, tests and documentation use made-up TV names and documentation addresses
  (`192.0.2.x`, `127.0.0.1`), never real ones from your home.
- Messages shown to the user are plain sentences that say what happened and what to do.
- Keep pull requests small and about one thing. Add a line to `CHANGELOG.md` under
  "Unreleased" for anything a user would notice.

## Adding support for another kind of TV

TV protocols live in `src/tvsend/backends/`. A back-end implements the small interface
in `backends/base.py` (load, play, pause, stop, seek, state). DLNA is the reference
implementation. Please open an issue before starting on AirPlay or Chromecast so the
work is not done twice.

## Licence

By contributing you agree that your contribution is released under the MIT licence of
this project.
