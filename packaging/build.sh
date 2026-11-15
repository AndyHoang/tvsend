#!/bin/sh
# Build the standalone tvsend binary for the machine this runs on.
#
#   packaging/build.sh
#
# Result: dist/tvsend-<os>-<arch> and dist/tvsend-<os>-<arch>.sha256
#   <os>   linux | macos
#   <arch> x86_64 | arm64
#
# Needs uv. The build runs in a throw-away environment (--isolated), so the
# project's own .venv is left alone. TVSEND_BUILD_PYTHON picks the Python that
# gets bundled (default 3.13).
set -eu

cd "$(dirname "$0")/.."

case "$(uname -s)" in
    Linux) os=linux ;;
    Darwin) os=macos ;;
    *) echo "build.sh: unsupported system: $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64 | amd64) arch=x86_64 ;;
    arm64 | aarch64) arch=arm64 ;;
    *) echo "build.sh: unsupported processor: $(uname -m)" >&2; exit 1 ;;
esac

name="tvsend-$os-$arch"
python="${TVSEND_BUILD_PYTHON:-3.13}"
work="build/pyinstaller"

rm -rf "$work"
mkdir -p dist

# --collect-submodules textual: Textual loads its widgets by name at run time,
#   so PyInstaller cannot see them by following imports.
# --collect-data textual: its bundled data files (syntax-highlight queries).
# --strip is left out on macOS, where it would break the code signature.
strip=""
[ "$os" = linux ] && strip="--strip"

# shellcheck disable=SC2086  # $strip is empty or one flag, on purpose
uv run --isolated --python "$python" --with "pyinstaller>=6.11" \
    pyinstaller --onefile --name tvsend --clean --noconfirm --log-level WARN $strip \
    --paths src \
    --collect-submodules textual \
    --collect-data textual \
    --distpath "$work/dist" --workpath "$work/work" --specpath "$work" \
    packaging/entry.py

mv "$work/dist/tvsend" "dist/$name"
chmod 755 "dist/$name"

if command -v sha256sum >/dev/null 2>&1; then
    (cd dist && sha256sum "$name" >"$name.sha256")
else
    (cd dist && shasum -a 256 "$name" >"$name.sha256")
fi

echo "built dist/$name ($(wc -c <"dist/$name" | tr -d ' ') bytes)"
