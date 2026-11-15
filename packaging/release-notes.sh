#!/bin/sh
# Print the CHANGELOG.md section of one version (the text under "## [1.2.3] ..." or
# "## 1.2.3 ...", up to the next "## " heading).
#
#   packaging/release-notes.sh VERSION [CHANGELOG.md]
set -eu

[ $# -ge 1 ] || { echo "usage: release-notes.sh VERSION [CHANGELOG.md]" >&2; exit 2; }
version="${1#v}"
file="${2:-CHANGELOG.md}"

notes="$(awk -v v="$version" '
    /^## / {
        if (found) exit
        head = $2
        gsub(/^\[|\]$/, "", head)
        sub(/^v/, "", head)
        if (head == v) { found = 1; next }
    }
    found && /^\[[^]]+\]: / { exit }
    found { print }
' "$file" 2>/dev/null || true)"

if [ -n "$(printf '%s' "$notes" | tr -d '[:space:]')" ]; then
    printf '%s\n' "$notes"
else
    echo "Release $version."
fi
