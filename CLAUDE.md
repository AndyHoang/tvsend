# tvsend - working notes

- `SPEC.md` is the agreed specification. Read it before changing behaviour.
- `reference/` (git-ignored) holds the personal script this app was ported from. Port
  behaviour from it; never copy its addresses, TV name or folder paths into the repo.
- Development uses **uv**: `uv sync`, `uv run tvsend`, `uv run pytest`, `uv run ruff check`.
- Python 3.10+. Do not add `from __future__ import annotations`.
- Runtime dependencies: Textual only (plus `tomli` on Python 3.10). No ffmpeg/ffprobe.
- The file server binds to one LAN address, never to all interfaces.
- Examples and tests use made-up names and documentation addresses (192.0.2.x, 127.0.0.1).
