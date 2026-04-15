"""
flush_cache.py — Delete all cached score JSON files from the db/ directory.

Usage:
    python flush_cache.py        Ask for confirmation, then delete all cached scores.
    python flush_cache.py -y     Skip confirmation (useful in scripts).

Run this after applying an update that changes ir.py, parser.py, or cache.py
so that all scores are re-fetched and re-parsed from CDN with the new code.
"""

import os
import sys

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db')


def main():
    skip_confirm = '-y' in sys.argv

    if not os.path.exists(DB_DIR):
        print("db/ directory does not exist — nothing to flush.")
        sys.exit(0)

    files = [f for f in os.listdir(DB_DIR) if f.endswith('.json')]

    if not files:
        print("Cache is already empty — nothing to flush.")
        sys.exit(0)

    print(f"Found {len(files)} cached score(s) in {DB_DIR}:")
    for f in sorted(files):
        path = os.path.join(DB_DIR, f)
        size = os.path.getsize(path)
        print(f"  {f:40s}  ({size:,} bytes)")

    print()

    if not skip_confirm:
        answer = input("Delete all cached scores? [y/N] ").strip().lower()
        if answer != 'y':
            print("Aborted. Cache unchanged.")
            sys.exit(0)

    for f in files:
        os.remove(os.path.join(DB_DIR, f))
        print(f"  Deleted: {f}")

    print()
    print(f"Done. {len(files)} file(s) removed. "
          "Scores will be re-fetched from CDN on next run.")


if __name__ == '__main__':
    main()
