# tvsend - working notes

- `SPEC.md` is the agreed specification. Read it before changing behaviour.
- `reference/` (git-ignored) holds the personal script this app was ported from. Port
  behaviour from it; never copy its addresses, TV name or folder paths into the repo.
- Development uses **uv**: `uv sync`, `uv run tvsend`, `uv run pytest`, `uv run ruff check`.
- Python 3.10+. Do not add `from __future__ import annotations`.
- Runtime dependencies: Textual only (plus `tomli` on Python 3.10). No ffmpeg/ffprobe.
- The file server binds to one LAN address, never to all interfaces.
- Examples and tests use made-up names and documentation addresses (192.0.2.x, 127.0.0.1).

## Versions and releases

- The version lives only in `src/tvsend/__init__.py`. Never edit it, tag, or date the
  changelog by hand: the Release workflow (`packaging/release.py`) does all of that.
- Every change a user would notice gets a line under `## [Unreleased]` in `CHANGELOG.md`,
  in the same commit. CI, tests and docs-only changes do not, and do not need a release.
  The release refuses to run while that section is empty.
- Bump: `patch` for fixes, `minor` for new features (Chromecast, subtitles), `major` for
  breaking changes to commands or config; `a1`/`b1`/`rc1` for a pre-release.
- Before a release, run the Package check workflow and try its binaries:
  `gh workflow run package.yml --ref main`.
- Release (only when the owner asks): `gh workflow run release.yml -f bump=patch`
  (or `minor` / `major`, or `-f version=0.2.0rc1`), then `git pull` for the release commit.
  Preview without changing anything: `uv run python packaging/release.py patch --dry-run`.
- Plans and open work are in `MILESTONES.md`; tick boxes there when work is merged.
