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

## Versions and releases

Versions follow [semantic versioning](https://semver.org): `MAJOR.MINOR.PATCH`, with
`a1`, `b1` or `rc1` added for a pre-release (`0.2.0rc1`). The version lives in one
place, `src/tvsend/__init__.py`, and every release is a git tag `v<version>`.

- **Every push and pull request** runs the CI workflow: lint, and the tests on Python
  3.10 to 3.14 on Linux (on macOS only the oldest and newest). No binaries are built there.
- **Before a release**, start the Package check workflow by hand (Actions -> Package
  check -> Run workflow, or `gh workflow run package.yml --ref <branch>`). It builds the
  four binaries without releasing anything, runs each one end to end against the fake
  TV (`packaging/smoke.py`), scans them for malware (ClamAV), checks the bundled
  dependencies for known vulnerabilities (pip-audit) and the workflows for security
  problems (zizmor), and installs the Homebrew formula from `packaging/homebrew`
  from a local tap. The binaries stay downloadable from the run for a week, to try on real
  machines. It also runs on pull requests that change packaging or dependencies.
- **A release** (maintainer) is made by starting the Release workflow by hand; that is
  the only place binaries are published.
  1. Make sure `CHANGELOG.md` describes the changes under "Unreleased".
  2. On GitHub: Actions -> Release -> Run workflow, and choose `patch`, `minor` or
     `major` (or `current` to release the version already in the source, or type an
     exact version such as `0.2.0rc1` for a pre-release). From a terminal:
     `gh workflow run release.yml -f bump=patch`.
  3. The workflow sets the version, dates the changelog section, runs lint and tests,
     commits and tags `v<version>` on `main`, builds the four binaries from that tag
     and publishes the GitHub Release with checksums and the changelog section as
     notes. Run `git pull` afterwards to get the release commit.
- To see what a release would do without doing it:
  `uv run python packaging/release.py patch --dry-run`. To build the binary for your
  own machine: `sh packaging/build.sh` (output in `dist/`).

## Adding support for another kind of TV

TV protocols live in `src/tvsend/backends/`. A back-end implements the small interface
in `backends/base.py` (load, play, pause, stop, seek, state). DLNA is the reference
implementation. Please open an issue before starting on AirPlay or Chromecast so the
work is not done twice.

## Licence

By contributing you agree that your contribution is released under the MIT licence of
this project.
