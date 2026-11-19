# tvsend - working notes

- `SPEC.md` is the agreed specification. Read it before changing behaviour.
- `reference/` (git-ignored) holds the personal script this app was ported from. Port
  behaviour from it; never copy its addresses, TV name or folder paths into the repo.
- Development uses **uv**: `uv sync`, `uv run tvsend`, `uv run pytest`, `uv run ruff check`.
- Python 3.10+. Do not add `from __future__ import annotations`.
- Runtime dependencies: Textual only (plus `tomli` on Python 3.10). No ffmpeg/ffprobe.
- The file server binds to one LAN address, never to all interfaces.
- Examples and tests use made-up names and documentation addresses (192.0.2.x, 127.0.0.1).

## Versions and releases (steps in `CONTRIBUTING.md`)

- Never edit the version, tag or date the changelog by hand: the Release workflow does it.
- A change a user would notice gets a line under `## [Unreleased]` in `CHANGELOG.md`, in
  the same commit. CI, tests and docs do not.
- Bump `patch` for fixes, `minor` for features, `major` for breaking changes to
  commands or config.
- Release only when the owner asks, after a green Package check run.
- Plans and open work are in `MILESTONES.md`; tick boxes there when work is merged.
