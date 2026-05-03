#!/usr/bin/env python3
"""
session_start.py — emit a self-contained session-start prompt for Claude.

Runs three git commands locally and reads two doc files; prints a single
block of text containing everything Claude needs to bootstrap a session.
No GitHub API calls, no waiting on a remote fetcher.

Usage (from project root):
    python session_start.py                 # print to stdout
    python session_start.py | clip          # Windows: copy to clipboard
    python session_start.py > prompt.txt    # save to file

The output begins with the phrase 'Start new session based on the
following local repo state.' so Claude can recognise the paste type.

This is a permanent utility script — like apply_update.py and
flush_cache.py, do not include it in update zips.
"""

import subprocess
import sys
from pathlib import Path


def run(cmd, *, allow_fail=False):
    """Run a command and return stdout. Abort on failure unless allow_fail."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        if allow_fail:
            return None
        sys.stderr.write(
            f"session_start.py: command failed: {' '.join(cmd)}\n"
            f"{result.stderr}"
        )
        sys.exit(1)
    return result.stdout


def main():
    # Refresh local-tracking refs from origin (quiet on success).
    run(["git", "fetch", "--quiet"])

    head = run(["git", "rev-parse", "HEAD"]).strip()
    tree = run(["git", "ls-tree", "-lr", "HEAD"]).rstrip("\n")

    # Compare HEAD vs origin/main so Claude knows whether what is described
    # has been pushed yet. Tolerate origin/main not existing.
    om_out = run(["git", "rev-parse", "origin/main"], allow_fail=True)
    if om_out is None:
        sync_line = "Sync vs origin/main: origin/main ref not found"
    else:
        origin_main = om_out.strip()
        if head == origin_main:
            sync_line = "Sync vs origin/main: in sync"
        else:
            sync_line = (
                f"Sync vs origin/main: HEAD={head[:7]}, "
                f"origin/main={origin_main[:7]} (likely unpushed commits)"
            )

    logbook = Path("LOGBOOK.md").read_text(encoding="utf-8").rstrip()
    readme = Path("README.md").read_text(encoding="utf-8").rstrip()

    parts = [
        "Start new session based on the following local repo state.",
        "",
        f"Commit SHA (git rev-parse HEAD): {head}",
        sync_line,
        "",
        "=== git ls-tree -lr HEAD ===",
        tree,
        "",
        "=== LOGBOOK.md ===",
        logbook,
        "",
        "=== README.md ===",
        readme,
    ]
    print("\n".join(parts))


if __name__ == "__main__":
    main()
