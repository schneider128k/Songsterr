#!/usr/bin/env python3
"""
session_start.py — emit a self-contained session-start prompt for Claude.

Runs three git commands locally and reads two doc files; writes a single
file in the session/ subfolder containing everything Claude needs to
bootstrap a session. No GitHub API calls, no waiting on a remote fetcher.

Usage (from project root):
    python session_start.py

Output:
    Writes session/session_upload_<YYYY-MM-DD_HHMMSS>.txt and prints the
    path. Upload that file as the first message of a new Claude chat —
    Windows PowerShell mangles a few characters when pasting (e.g. it
    decorates `parser.py` as `[parser.py](http://parser.py)`), so
    file-upload is more reliable than stdout-and-paste.

The file contents begin with the phrase 'Start new session based on the
following local repo state.' so Claude can recognise the upload type.

This is a permanent utility script — like apply_update.py and
flush_cache.py, do not include it in update zips. The session/ folder
should be gitignored.
"""

import datetime
import subprocess
import sys
from pathlib import Path


SESSION_DIR = Path("session")


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
    content = "\n".join(parts) + "\n"

    SESSION_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = SESSION_DIR / f"session_upload_{timestamp}.txt"
    out_path.write_text(content, encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"  ({len(content):,} chars, {out_path.stat().st_size:,} bytes)")
    print("Upload that file as the first message of a new Claude chat.")


if __name__ == "__main__":
    main()