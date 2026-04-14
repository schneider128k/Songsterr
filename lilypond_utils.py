"""
lilypond_utils.py — Auto-detect the LilyPond binary and retrieve its version.

Search order:
  1. LILYPOND_BIN environment variable (user override)
  2. Platform-specific known install paths
  3. 'lilypond' on PATH
"""

import os
import platform
import re
import subprocess


# Known install paths by platform
_CANDIDATES = {
    'Darwin': [
        '/Applications/LilyPond.app/Contents/Resources/bin/lilypond',
        '/usr/local/bin/lilypond',   # Homebrew
        '/opt/homebrew/bin/lilypond',  # Homebrew on Apple Silicon
    ],
    'Linux': [
        '/usr/bin/lilypond',
        '/usr/local/bin/lilypond',
    ],
    'Windows': [
        r'C:\Program Files (x86)\LilyPond\usr\bin\lilypond.exe',
        r'C:\Program Files\LilyPond\usr\bin\lilypond.exe',
    ],
}


def find_lilypond() -> str:
    """
    Return the path to the LilyPond binary.
    Raises FileNotFoundError if LilyPond cannot be found.
    """
    # 1. Environment variable override
    env = os.environ.get('LILYPOND_BIN')
    if env and os.path.isfile(env):
        return env

    # 2. Platform-specific candidates
    system = platform.system()
    for path in _CANDIDATES.get(system, []):
        if os.path.isfile(path):
            return path

    # 3. PATH fallback
    import shutil
    found = shutil.which('lilypond')
    if found:
        return found

    raise FileNotFoundError(
        'LilyPond not found. Install it from https://lilypond.org/download.html\n'
        'or set the LILYPOND_BIN environment variable to its full path.'
    )


def get_lilypond_version(lily_bin: str) -> str:
    """
    Return the major.minor version string (e.g. '2.24') for the given binary.
    Raises RuntimeError if the version cannot be parsed.
    """
    try:
        result = subprocess.run(
            [lily_bin, '--version'],
            capture_output=True, text=True, timeout=10
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ''
        m = re.search(r'(\d+\.\d+)\.\d+', first_line)
        if not m:
            raise RuntimeError(f'Cannot parse LilyPond version from: {first_line!r}')
        return m.group(1)
    except FileNotFoundError:
        raise FileNotFoundError(f'LilyPond binary not executable: {lily_bin}')
