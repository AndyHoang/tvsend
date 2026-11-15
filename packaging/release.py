"""Prepare a release:   uv run python packaging/release.py 1.2.3

Sets the version in the source, dates the CHANGELOG section, runs lint and tests,
commits and makes the tag v1.2.3. It does not push: it prints the push command, and
pushing the tag is what starts the Release workflow on GitHub.

Versions are MAJOR.MINOR.PATCH (semantic versioning), optionally followed by a1, b1 or
rc1 for a pre-release (1.2.3rc1). Add --dry-run to see what would change.
"""

import datetime
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "tvsend" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
VERSION = re.compile(r"\d+\.\d+\.\d+((a|b|rc)\d+)?")
REPO = "https://github.com/AndyHoang/tvsend"


def fail(text: str) -> None:
    sys.exit("release: " + text)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def key(version: str) -> tuple:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?", version)
    pre = (m[4], int(m[5])) if m[4] else ("z", 0)  # a final version sorts after its pre-releases
    return (int(m[1]), int(m[2]), int(m[3]), pre)


def new_changelog(text: str, version: str, today: str) -> str:
    """Give the version a dated section: an existing '## [version] ...' heading is dated,
    otherwise what is under '## [Unreleased]' becomes that version's section."""
    heading = re.compile(r"^## \[%s\].*$" % re.escape(version), re.M)
    dated = "## [%s] - %s" % (version, today)
    if heading.search(text):
        text = heading.sub(dated, text, count=1)
    else:
        m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## |^\[[^\]]+\]: |\Z)", text, re.M | re.S)
        if not m:
            fail("CHANGELOG.md has no '## [Unreleased]' section")
        if not m[1].strip():
            fail("nothing is written under '## [Unreleased]' in CHANGELOG.md - describe the changes first")
        text = text.replace("## [Unreleased]\n", "## [Unreleased]\n\n%s\n" % dated, 1)
    # the link list at the bottom
    text = re.sub(
        r"^\[Unreleased\]: .*$", "[Unreleased]: %s/compare/v%s...HEAD" % (REPO, version), text, flags=re.M
    )
    link = "[%s]: %s/releases/tag/v%s" % (version, REPO, version)
    if link not in text:
        text = re.sub(
            r"^(\[Unreleased\]: .*)$", r"\1\n" + link.replace("\\", r"\\"), text, count=1, flags=re.M
        )
    return text


def main(argv: list[str]) -> None:
    dry = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if len(args) != 1 or not VERSION.fullmatch(args[0]):
        fail("give one version like 1.2.3 or 1.2.3rc1 (see the top of this file)")
    version, tag = args[0], "v" + args[0]

    current = re.search(r'^__version__ = "(.*)"$', INIT.read_text(), re.M)[1]
    if git("branch", "--show-current") != "main":
        fail("releases are made from the main branch")
    if git("status", "--porcelain"):
        fail("there are uncommitted changes - commit or stash them first")
    if git("tag", "--list", tag):
        fail("the tag %s already exists" % tag)
    released = [t[1:] for t in git("tag", "--list", "v*").split() if VERSION.fullmatch(t[1:])]
    newest = max(released, key=key, default=None)
    if newest and key(version) <= key(newest):
        fail("%s is not newer than the last release %s" % (version, newest))

    today = datetime.date.today().isoformat()
    changelog = new_changelog(CHANGELOG.read_text(), version, today)
    print("version:   %s -> %s" % (current, version))
    print("changelog: section [%s] dated %s" % (version, today))
    if dry:
        print("dry run: nothing was changed")
        return

    INIT.write_text(INIT.read_text().replace('__version__ = "%s"' % current, '__version__ = "%s"' % version))
    CHANGELOG.write_text(changelog)
    try:
        for cmd in ("uv lock", "uv run ruff check", "uv run ruff format --check", "uv run pytest -q"):
            cmd = cmd.split()
            print("$ " + " ".join(cmd))
            subprocess.run(cmd, cwd=ROOT, check=True)
    except subprocess.CalledProcessError:
        git("checkout", "--", ".")
        fail("checks failed - the version and changelog edits were undone")
    git("commit", "-am", "Release %s" % version)
    git("tag", "-a", tag, "-m", "tvsend %s" % version)
    print("\nCommitted and tagged %s. To publish it, push the commit and the tag:" % tag)
    print("    git push origin main %s" % tag)
    print("To take it back instead:  git tag -d %s && git reset --hard HEAD~1" % tag)


if __name__ == "__main__":
    main(sys.argv[1:])
