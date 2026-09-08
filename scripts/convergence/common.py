from __future__ import annotations

import re
from pathlib import Path


TOTEN_PATTERN = re.compile(r"free\s+energy\s+TOTEN\s+=\s+([-0-9.]+)")
# Existing submission timeout, shared with the legacy convergence submitter.
EXTERNAL_COMMAND_TIMEOUT_SECONDS = 300


def last_matching_float(path: Path, pattern: re.Pattern[str]) -> float | None:
    if not path.exists():
        return None
    value = None
    for line in path.read_text(errors="ignore").splitlines():
        match = pattern.search(line)
        if match:
            value = float(match.group(1))
    return value


def extract_toten(outcar: Path) -> float | None:
    """Return the last VASP TOTEN value, or None when no value exists."""
    return last_matching_float(outcar, TOTEN_PATTERN)
