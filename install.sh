#!/bin/sh
# Install tvsend: downloads the newest release for this computer, checks it, and puts
# it in ~/.local/bin (no sudo).
#
#   curl -fsSL https://raw.githubusercontent.com/AndyHoang/tvsend/main/install.sh | sh
#
# Settings (environment variables):
#   TVSEND_INSTALL_DIR   where to put the binary     (default: ~/.local/bin)
#   TVSEND_VERSION       a version such as 1.2.3     (default: the newest release)
set -eu

repo="AndyHoang/tvsend"
dir="${TVSEND_INSTALL_DIR:-$HOME/.local/bin}"
version="${TVSEND_VERSION:-}"

fail() {
    echo "install.sh: $*" >&2
    exit 1
}

case "$(uname -s)" in
    Linux) os=linux ;;
    Darwin) os=macos ;;
    *) fail "tvsend supports Linux and macOS, not $(uname -s)" ;;
esac
case "$(uname -m)" in
    x86_64 | amd64) arch=x86_64 ;;
    arm64 | aarch64) arch=arm64 ;;
    *) fail "there is no tvsend download for this processor ($(uname -m))" ;;
esac
name="tvsend-$os-$arch"

if command -v curl >/dev/null 2>&1; then
    fetch() { curl -fsSL --proto '=https' --tlsv1.2 -o "$2" "$1"; }
elif command -v wget >/dev/null 2>&1; then
    fetch() { wget -q --https-only -O "$2" "$1"; }
else
    fail "curl or wget is needed"
fi

if command -v sha256sum >/dev/null 2>&1; then
    sha256() { sha256sum "$1" | cut -d ' ' -f 1; }
elif command -v shasum >/dev/null 2>&1; then
    sha256() { shasum -a 256 "$1" | cut -d ' ' -f 1; }
else
    fail "sha256sum or shasum is needed to check the download"
fi

if [ -n "$version" ]; then
    base="https://github.com/$repo/releases/download/v${version#v}"
else
    base="https://github.com/$repo/releases/latest/download"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM

echo "Downloading $name..."
fetch "$base/$name" "$tmp/$name" || fail "could not download $base/$name"
fetch "$base/SHA256SUMS" "$tmp/SHA256SUMS" || fail "could not download the checksums"

wanted="$(awk -v n="$name" '$2 == n || $2 == "*" n { print $1 }' "$tmp/SHA256SUMS")"
got="$(sha256 "$tmp/$name")"
[ -n "$wanted" ] || fail "the checksum list does not mention $name"
[ "$wanted" = "$got" ] || fail "the download does not match its checksum - nothing was installed"

mkdir -p "$dir"
chmod 755 "$tmp/$name"
mv "$tmp/$name" "$dir/tvsend.new.$$"
mv "$dir/tvsend.new.$$" "$dir/tvsend"

echo "Installed $("$dir/tvsend" --version 2>/dev/null || echo tvsend) to $dir/tvsend"

case ":$PATH:" in
    *":$dir:"*) echo "Start it with: tvsend" ;;
    *)
        echo
        echo "Note: $dir is not on your PATH, so typing 'tvsend' will not find it yet."
        echo "Add this line to your shell's start file (~/.zshrc, ~/.bashrc, ...):"
        echo "    export PATH=\"$dir:\$PATH\""
        echo "Until then, start it with: $dir/tvsend"
        ;;
esac
