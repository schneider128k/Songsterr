"""
apply_update.py — Apply a versioned update zip to the Songsterr project.

Usage:
    python apply_update.py update_v1.zip

The zip should contain only the files to be replaced (e.g. parser.py,
emitter.py). This script will:
  1. Show what files are in the zip and ask for confirmation
  2. Back up each file that will be replaced (filename.bak)
  3. Extract the new files into the project directory
  4. Print a summary of what changed

This script itself never needs to be updated.
"""

import sys
import os
import zipfile
import shutil


def main():
    if len(sys.argv) < 2:
        print("Usage: python apply_update.py <update_vN.zip>")
        sys.exit(1)

    zip_path = sys.argv[1]

    if not os.path.exists(zip_path):
        print(f"Error: '{zip_path}' not found.")
        sys.exit(1)

    if not zipfile.is_zipfile(zip_path):
        print(f"Error: '{zip_path}' is not a valid zip file.")
        sys.exit(1)

    project_dir = os.path.dirname(os.path.abspath(__file__))

    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = [n for n in zf.namelist() if not n.endswith('/')]

    if not names:
        print("The zip file is empty. Nothing to do.")
        sys.exit(0)

    print(f"\nUpdate: {zip_path}")
    print(f"Project directory: {project_dir}")
    print(f"\nFiles in this update:")
    for name in names:
        dest = os.path.join(project_dir, name)
        status = "(new file)" if not os.path.exists(dest) else "(will replace)"
        print(f"  {name:30s} {status}")

    print()
    answer = input("Apply this update? [y/N] ").strip().lower()
    if answer != 'y':
        print("Aborted. No files were changed.")
        sys.exit(0)

    print()
    backed_up = []
    replaced  = []
    created   = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in names:
            dest = os.path.join(project_dir, name)

            # Back up existing file
            if os.path.exists(dest):
                bak = dest + '.bak'
                shutil.copy2(dest, bak)
                backed_up.append(name)

            # Extract new file
            source = zf.read(name)
            with open(dest, 'wb') as f:
                f.write(source)

            if name in backed_up:
                replaced.append(name)
                print(f"  Replaced : {name}  (backup: {name}.bak)")
            else:
                created.append(name)
                print(f"  Created  : {name}")

    print()
    print(f"Done. {len(replaced)} file(s) replaced, {len(created)} file(s) created.")
    print()
    if backed_up:
        print("To undo this update, run:")
        for name in backed_up:
            if sys.platform == 'win32':
                print(f"  copy {name}.bak {name}")
            else:
                print(f"  cp {name}.bak {name}")
    print()


if __name__ == '__main__':
    main()
