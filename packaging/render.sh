#!/bin/sh
# Fill a packaging template with a release's version and checksums.
#
#   packaging/render.sh VERSION SHA256SUMS TEMPLATE [LICENSE] > OUTPUT
#
# SHA256SUMS is the checksum file of the release ("<hash>  <file name>" per line).
# LICENSE (optional) is the licence file whose checksum fills @SHA_LICENSE@.
set -eu

[ $# -ge 3 ] || { echo "usage: render.sh VERSION SHA256SUMS TEMPLATE [LICENSE]" >&2; exit 2; }
version="${1#v}"
sums="$2"
template="$3"
license="${4:-}"

sum_of() {
    hash="$(awk -v n="$1" '$2 == n || $2 == "*" n { print $1 }' "$sums")"
    [ -n "$hash" ] || { echo "render.sh: $sums has no checksum for $1" >&2; exit 1; }
    printf '%s' "$hash"
}

license_sum=""
if [ -n "$license" ]; then
    if command -v sha256sum >/dev/null 2>&1; then
        license_sum="$(sha256sum "$license" | cut -d ' ' -f 1)"
    else
        license_sum="$(shasum -a 256 "$license" | cut -d ' ' -f 1)"
    fi
fi

linux_x86_64="$(sum_of tvsend-linux-x86_64)"
linux_arm64="$(sum_of tvsend-linux-arm64)"
macos_x86_64="$(sum_of tvsend-macos-x86_64)"
macos_arm64="$(sum_of tvsend-macos-arm64)"

sed -e "s/@VERSION@/$version/g" \
    -e "s/@SHA_LINUX_X86_64@/$linux_x86_64/g" \
    -e "s/@SHA_LINUX_ARM64@/$linux_arm64/g" \
    -e "s/@SHA_MACOS_X86_64@/$macos_x86_64/g" \
    -e "s/@SHA_MACOS_ARM64@/$macos_arm64/g" \
    -e "s/@SHA_LICENSE@/$license_sum/g" \
    "$template"
